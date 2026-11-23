"""OndoTrip CLI 진입점: 공공데이터 수집 -> 원고 생성 -> 미리보기/블로그 발행."""

from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path
from typing import Any

import config
from blogger_client import BloggerClient
from history_store import (
    choose_next_auto_category,
    get_category_stats,
    is_posted,
    record_post,
)
from tour_api import TourAPIClient
from writer import _clean_text, generate_blog_post

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("ondotrip")


def _sanitize_filename(name: str) -> str:
    """파일 이름에 사용할 수 없는 문자를 안전한 언더스코어로 치환한다."""
    return re.sub(r'[\\/:*?"<>|\s]+', "_", name).strip("_")[:60] or "post"


def _save_preview_html(post: dict[str, Any]) -> Path:
    """로컬 output 폴더에 브라우저로 바로 열어볼 수 있는 미리보기 HTML을 저장한다."""
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = _sanitize_filename(post["spot_title"])
    filename = f"{post['content_id']}_{safe_name}.html"
    output_path = config.OUTPUT_DIR / filename
    preview_doc = (
        "<!DOCTYPE html>\n"
        '<html lang="ko">\n<head>\n'
        '<meta charset="utf-8" />\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0" />\n'
        f"<title>{post['title']}</title>\n"
        "</head>\n"
        '<body style="margin:24px;background:#ffffff;">\n'
        f"{post['html']}\n"
        "</body>\n</html>\n"
    )
    output_path.write_text(preview_doc, encoding="utf-8")
    return output_path


def _fetch_candidates_page(
    tour_client: TourAPIClient,
    *,
    mode: str,
    area: str | None,
    category: str | None,
    type_name: str | None,
    keyword: str | None,
    content_id: str | None,
    count: int,
    page_no: int,
) -> list[dict[str, Any]]:
    """지정된 페이지에서 포스팅 후보 관광정보 목록을 조회한다."""
    effective_mode = "keyword" if (keyword and mode == "area") else mode
    if content_id:
        effective_mode = "content-id"

    if effective_mode == "content-id":
        return [{"contentid": str(content_id)}] if page_no == 1 else []

    ldong_code = config.resolve_ldong_regn(area)
    fetch_rows = max(count * 5, 20)

    if effective_mode == "keyword":
        if not keyword:
            raise ValueError("--mode keyword 사용 시 --keyword 값을 입력해야 합니다.")
        return tour_client.search_keyword(
            keyword=keyword,
            ldong_regn_cd=ldong_code,
            num_of_rows=fetch_rows,
            page_no=page_no,
        )

    resolved_type = type_name
    if not resolved_type:
        blog_cat = config.resolve_blog_category(category)
        resolved_type = config.CATEGORY_DEFAULT_TYPE.get(blog_cat, "관광지")

    content_type_id = config.resolve_content_type(resolved_type)
    items = tour_client.get_area_based_list(
        content_type_id=content_type_id,
        ldong_regn_cd=ldong_code,
        arrange="Q",
        num_of_rows=fetch_rows,
        page_no=page_no,
    )
    if not items and page_no == 1:
        items = tour_client.get_area_based_list(
            content_type_id=content_type_id,
            ldong_regn_cd=ldong_code,
            arrange="C",
            num_of_rows=fetch_rows,
            page_no=page_no,
        )
    return items


def _is_candidate_eligible(item: dict[str, Any], category: str | None) -> bool:
    """축제/행사 제외 및 카테고리 일치 여부를 검사한다."""
    ctype = str(item.get("contenttypeid", "")).strip()
    if ctype in config.EXCLUDED_CONTENT_TYPES:
        logger.info(
            "축제/행사 제외 정책으로 건너뜀: %s (%s)",
            item.get("contentid"),
            item.get("title", ""),
        )
        return False
    if category and ctype:
        target_cat = config.resolve_blog_category(category)
        item_cat = config.resolve_blog_category(
            None, ctype, title=str(item.get("title", ""))
        )
        if item_cat != target_cat:
            return False
    return True


def _select_candidates(
    tour_client: TourAPIClient,
    *,
    mode: str,
    area: str | None,
    category: str | None,
    type_name: str | None,
    keyword: str | None,
    content_id: str | None,
    count: int,
    force: bool,
    preview_only: bool,
    exclude_cids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """페이지를 순회하며 조건에 맞는 미발행 후보를 count개까지 선택한다."""
    selected: list[dict[str, Any]] = []
    seen_cids: set[str] = set(exclude_cids or set())
    max_pages = 1 if content_id else 5

    for page_no in range(1, max_pages + 1):
        candidates = _fetch_candidates_page(
            tour_client,
            mode=mode,
            area=area,
            category=category,
            type_name=type_name,
            keyword=keyword,
            content_id=content_id,
            count=count,
            page_no=page_no,
        )
        if not candidates:
            break
        for item in candidates:
            cid = str(item.get("contentid", "")).strip()
            if not cid or cid in seen_cids:
                continue
            seen_cids.add(cid)
            if not _is_candidate_eligible(item, category):
                continue
            if not force and not preview_only and is_posted(cid):
                logger.info("이미 처리된 콘텐츠 건너뜀: %s (%s)", cid, item.get("title", ""))
                continue
            selected.append(item)
            if len(selected) >= count:
                break
        if len(selected) >= count:
            break

    return selected


def _passes_quality_check(bundle: dict[str, Any], category: str) -> tuple[bool, str]:
    """수집된 상세 데이터가 블로그 원고 품질 기준을 충족하는지 검사한다."""
    common = bundle.get("common") or {}
    images = bundle.get("images") or []
    info_list = bundle.get("info_list") or []

    overview = _clean_text(common.get("overview"))
    min_len = config.MIN_OVERVIEW_BY_CATEGORY.get(category, 40)
    if len(overview) < min_len:
        return False, f"개요 길이 부족 ({len(overview)}자 < {min_len}자)"

    has_hero = bool(str(common.get("firstimage") or "").strip())
    has_gallery = any(str(img.get("originimgurl") or "").strip() for img in images)
    has_course_img = any(
        str(info.get("subdetailimg") or "").strip() for info in info_list
    )
    if not (has_hero or has_gallery or has_course_img):
        return False, "대표 및 추가 이미지 없음"

    return True, "OK"


def _process_single_item(
    tour_client: TourAPIClient,
    blogger: BloggerClient | None,
    item: dict[str, Any],
    *,
    idx: int,
    total: int,
    category_override: str | None,
    preview_only: bool,
    is_draft: bool,
    preloaded_bundle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """단일 후보의 상세정보를 수집해 HTML을 생성하고 필요 시 Blogger에 업로드한다."""
    cid = str(item["contentid"])
    ctype = item.get("contenttypeid")
    if preloaded_bundle is not None:
        bundle = preloaded_bundle
    else:
        logger.info(
            "[%d/%d] 상세정보 수집 중: contentId=%s (%s)",
            idx,
            total,
            cid,
            item.get("title", ""),
        )
        bundle = tour_client.get_full_spot_bundle(
            content_id=cid,
            content_type_id=str(ctype) if ctype else None,
            summary_item=item,
        )
    post = generate_blog_post(bundle, category_override=category_override)
    preview_path = _save_preview_html(post)

    print(f"\n[{idx}/{total}] 원고 생성 완료 (생성 엔진: {post['ai_model']})")
    print(f"- 카테고리: {post['blog_category']}")
    print(f"- 제목: {post['title']}")
    print(f"- 태그: {', '.join(post['labels'])}")
    print(f"- 미리보기 HTML: {preview_path}")

    if preview_only:
        return post

    assert blogger is not None
    result = blogger.insert_post(
        title=post["title"],
        html_content=post["html"],
        labels=post["labels"],
        is_draft=is_draft,
    )
    post_id = str(result.get("id", ""))
    post_url = str(result.get("url", ""))
    record_post(
        content_id=cid,
        title=post["title"],
        post_id=post_id,
        post_url=post_url,
        is_draft=is_draft,
        category=post["blog_category"],
    )
    status_label = "임시저장(Draft)" if is_draft else "공개 발행(Published)"
    print(f"- Blogger 업로드 완료 [{status_label}] -> ID: {post_id}")
    if post_url:
        print(f"- URL: {post_url}")
    return post


def _print_status() -> None:
    """현재까지 기록된 카테고리별 누적 건수와 다음 여정까지 남은 개수를 출력한다."""
    stats = get_category_stats()
    counts = stats["counts"]
    print("=== OndoTrip 발행 현황 ===")
    print(f"- 총 처리 콘텐츠: {stats['total']}개")
    for cat in config.BLOG_CATEGORIES:
        print(f"  · {cat}: {counts.get(cat, 0)}개")
    print(
        f"- 마지막 여정 이후 장소/미식 누적: "
        f"{stats['since_last_journey']} / {stats['journey_interval']}개"
    )
    if stats["journey_due"]:
        print("- 다음 자동 실행 시 [그날의 여정] 차례입니다!")
    else:
        print(
            f"- 다음 [그날의 여정] 업로드까지 장소·미식 {stats['remaining_for_journey']}개 남음"
        )


def _pick_quality_bundle(
    tour_client: TourAPIClient,
    candidates: list[dict[str, Any]],
    *,
    target_cat: str,
    force: bool,
    exclude_cids: set[str],
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """후보 목록에서 품질 기준(개요 길이·이미지)을 통과하는 첫 항목과 번들을 반환한다."""
    for item in candidates:
        cid = str(item.get("contentid", "")).strip()
        if not cid or cid in exclude_cids:
            continue
        exclude_cids.add(cid)
        ctype = item.get("contenttypeid")
        bundle = tour_client.get_full_spot_bundle(
            content_id=cid,
            content_type_id=str(ctype) if ctype else None,
            summary_item=item,
        )
        if not force:
            ok, reason = _passes_quality_check(bundle, target_cat)
            if not ok:
                logger.info(
                    "품질 기준 미달로 건너뜀: %s (%s) - %s",
                    cid,
                    item.get("title", ""),
                    reason,
                )
                continue
        return item, bundle
    return None


def _run_auto_mode(
    tour_client: TourAPIClient,
    blogger: BloggerClient | None,
    args: argparse.Namespace,
) -> int:
    """장소/미식 10개당 여정 1개 비율, 인기 테마 키워드, 지역 균형, 품질 필터를 맞춰 자동 작성한다."""
    stats = get_category_stats()
    counts = dict(stats["counts"])
    since_last_journey = int(stats["since_last_journey"])
    total_processed = int(stats["total"])
    processed_cids: set[str] = set()
    is_draft = not args.publish

    for idx in range(1, args.count + 1):
        target_cat = choose_next_auto_category(counts, since_last_journey)
        if args.area:
            target_area: str | None = args.area
        elif target_cat == "그날의 여정":
            # 여행코스는 시도코드가 없는 전국 코스가 많아 전국 조회 사용
            target_area = None
        else:
            target_area = config.AUTO_ROTATION_AREAS[
                total_processed % len(config.AUTO_ROTATION_AREAS)
            ]

        theme_pool = config.AUTO_THEME_KEYWORDS.get(target_cat, ())
        theme_keyword: str | None = (
            theme_pool[total_processed % len(theme_pool)]
            if (theme_pool and not args.keyword)
            else args.keyword
        )

        logger.info(
            "[자동 배분 %d/%d] 목표=%s, 지역=%s, 테마=%s (여정 누적 %d/%d)",
            idx,
            args.count,
            target_cat,
            target_area or "전국",
            theme_keyword or "전체",
            since_last_journey,
            config.JOURNEY_EVERY_N_POSTS,
        )

        query_plans: list[tuple[str, str | None, str | None]] = []
        if theme_keyword:
            query_plans.append(("keyword", target_area, theme_keyword))
        query_plans.append(("area", target_area, None))
        if target_area is not None:
            query_plans.append(("area", None, None))

        picked: tuple[dict[str, Any], dict[str, Any]] | None = None
        checked_in_turn: set[str] = set(processed_cids)
        for q_mode, q_area, q_keyword in query_plans:
            candidates = _select_candidates(
                tour_client,
                mode=q_mode,
                area=q_area,
                category=target_cat,
                type_name=None,
                keyword=q_keyword,
                content_id=None,
                count=5,
                force=args.force,
                preview_only=args.preview_only,
                exclude_cids=checked_in_turn,
            )
            picked = _pick_quality_bundle(
                tour_client,
                candidates,
                target_cat=target_cat,
                force=args.force,
                exclude_cids=checked_in_turn,
            )
            if picked is not None:
                break

        if picked is None:
            print(f"[{idx}/{args.count}] '{target_cat}'에서 조건을 충족하는 새 후보를 찾지 못했습니다.")
            continue

        item, bundle = picked
        processed_cids.add(str(item["contentid"]))
        _process_single_item(
            tour_client,
            blogger,
            item,
            idx=idx,
            total=args.count,
            category_override=target_cat,
            preview_only=args.preview_only,
            is_draft=is_draft,
            preloaded_bundle=bundle,
        )

        counts[target_cat] = counts.get(target_cat, 0) + 1
        total_processed += 1
        if target_cat == "그날의 여정":
            since_last_journey = 0
        else:
            since_last_journey += 1

    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """커맨드라인 인자를 파싱한다."""
    parser = argparse.ArgumentParser(
        description="한국관광공사 국문 관광정보 API 기반 구글 블로그(OndoTrip) 자동 작성기"
    )
    parser.add_argument(
        "--category",
        default=None,
        help="블로그 카테고리 (그날의 장소 / 그날의 미식 / 그날의 쉼터 / 그날의 여정, 줄여서 장소/미식/쉼터/여정)",
    )
    parser.add_argument(
        "--mode",
        choices=("auto", "area", "keyword", "content-id"),
        default="area",
        help="조회 방식 (auto: 장소·미식·쉼터 10개당 여정 1개 자동 배분, 기본값: area)",
    )
    parser.add_argument(
        "--area",
        default=None,
        help="지역명 또는 법정동 시도코드 (예: 서울, 부산, 강원, 제주, 전국 / 미지정 시 전국)",
    )
    parser.add_argument(
        "--type",
        default=None,
        help="관광타입 이름 또는 코드 (미지정 시 --category에 따라 자동 선택: 장소=관광지, 미식=음식점, 쉼터=숙박, 여정=여행코스)",
    )
    parser.add_argument("--keyword", default=None, help="검색 키워드")
    parser.add_argument("--content-id", default=None, help="특정 콘텐츠 ID 직접 지정")
    parser.add_argument("--count", type=int, default=1, help="작성할 글 개수 (기본값: 1)")
    parser.add_argument(
        "--publish",
        action="store_true",
        help="지정 시 블로그에 즉시 공개 발행 (미지정 시 안전하게 임시저장)",
    )
    parser.add_argument(
        "--preview-only",
        action="store_true",
        help="Blogger 업로드 없이 로컬 output/ 폴더에 HTML 미리보기 파일만 생성",
    )
    parser.add_argument(
        "--auth-only",
        action="store_true",
        help="Google Blogger OAuth 2.0 인증 및 연결된 블로그 정보 확인만 수행",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="현재 카테고리별 누적 현황 및 다음 여정 업로드까지 남은 개수를 확인",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="posted_history.json에 이미 기록된 콘텐츠도 건너뛰지 않고 재작성",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """메인 파이프라인을 실행한다."""
    args = parse_args(argv)

    if args.status:
        _print_status()
        return 0

    if args.auth_only:
        blogger = BloggerClient()
        info = blogger.get_blog_info()
        print("Google Blogger 연결 확인 완료:")
        print(f"- 블로그 이름: {info.get('name')}")
        print(f"- 블로그 URL: {info.get('url')}")
        print(f"- 총 게시물 수: {info.get('posts', {}).get('totalItems', 0)}")
        return 0

    tour_client = TourAPIClient()
    blogger = None if args.preview_only else BloggerClient()

    if args.mode == "auto":
        return _run_auto_mode(tour_client, blogger, args)

    selected = _select_candidates(
        tour_client,
        mode=args.mode,
        area=args.area,
        category=args.category,
        type_name=args.type,
        keyword=args.keyword,
        content_id=args.content_id,
        count=args.count,
        force=args.force,
        preview_only=args.preview_only,
    )
    if not selected:
        print("조건에 해당하는 새 관광정보가 없습니다. (--force 옵션으로 재작성 가능)")
        return 0

    is_draft = not args.publish
    for idx, item in enumerate(selected, start=1):
        _process_single_item(
            tour_client,
            blogger,
            item,
            idx=idx,
            total=len(selected),
            category_override=args.category,
            preview_only=args.preview_only,
            is_draft=is_draft,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
