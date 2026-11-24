"""Gemini 연동 및 한국관광공사 데이터 기반 블로그 HTML 포스트 생성기."""

from __future__ import annotations

import html
import json
import logging
import re
from typing import Any
from urllib.parse import quote

import config

logger = logging.getLogger(__name__)

# 상세소개(detailIntro2) 타입별 한글 라벨 매핑 (KorService2 Ver 4.4 기준)
INTRO_FIELD_LABELS: list[tuple[str, str]] = [
    ("eventstartdate", "행사 시작일"),
    ("eventenddate", "행사 종료일"),
    ("eventplace", "행사 장소"),
    ("placeinfo", "행사장 위치 안내"),
    ("playtime", "공연 시간"),
    ("usetimefestival", "행사 이용요금"),
    ("spendtimefestival", "관람 소요시간"),
    ("program", "행사 프로그램"),
    ("subevent", "부대 행사"),
    ("bookingplace", "예매처"),
    ("festivalgrade", "축제 등급"),
    ("sponsor1", "주최"),
    ("sponsor1tel", "주최 연락처"),
    ("sponsor2", "주관"),
    ("sponsor2tel", "주관 연락처"),
    ("firstmenu", "대표 메뉴"),
    ("treatmenu", "취급 메뉴"),
    ("opentimefood", "영업시간"),
    ("restdatefood", "쉬는날"),
    ("infocenterfood", "문의 및 안내"),
    ("parkingfood", "주차 시설"),
    ("reservationfood", "예약 안내"),
    ("packing", "포장 가능"),
    ("seat", "좌석 수"),
    ("kidsfacility", "어린이 놀이방"),
    ("checkintime", "체크인(입실)"),
    ("checkouttime", "체크아웃(퇴실)"),
    ("roomcount", "객실 수"),
    ("roomtype", "객실 유형"),
    ("infocenterlodging", "문의 및 안내"),
    ("parkinglodging", "주차 시설"),
    ("chkcooking", "객실 내 취사"),
    ("foodplace", "식음료장"),
    ("reservationlodging", "예약 안내"),
    ("subfacility", "부대시설"),
    ("refundregulation", "환불 규정"),
    ("infocenter", "문의 및 안내"),
    ("infocenterculture", "문의 및 안내"),
    ("infocenterleports", "문의 및 안내"),
    ("infocentershopping", "문의 및 안내"),
    ("infocentertourcourse", "문의 및 안내"),
    ("usetime", "이용시간"),
    ("usetimeculture", "이용시간"),
    ("usetimeleports", "이용시간"),
    ("opentime", "영업시간"),
    ("openperiod", "개장 기간"),
    ("opendate", "개장일"),
    ("opendateshopping", "개장일"),
    ("restdate", "쉬는날"),
    ("restdateculture", "쉬는날"),
    ("restdateleports", "쉬는날"),
    ("restdateshopping", "쉬는날"),
    ("fairday", "장서는 날"),
    ("useseason", "이용 시기"),
    ("usefee", "이용요금"),
    ("usefeeleports", "입장료"),
    ("discountinfo", "할인 정보"),
    ("discountinfofestival", "할인 정보"),
    ("discountinfofood", "할인 정보"),
    ("parking", "주차 시설"),
    ("parkingculture", "주차 시설"),
    ("parkingfee", "주차 요금"),
    ("parkingleports", "주차 시설"),
    ("parkingfeeleports", "주차 요금"),
    ("parkingshopping", "주차 시설"),
    ("distance", "코스 총거리"),
    ("taketime", "코스 총 소요시간"),
    ("theme", "코스 테마"),
    ("schedule", "코스 일정"),
    ("spendtime", "관람 소요시간"),
    ("scale", "규모"),
    ("scaleleports", "규모"),
    ("scaleshopping", "규모"),
    ("scalelodging", "규모"),
    ("saleitem", "판매 품목"),
    ("saleitemcost", "품목별 가격"),
    ("shopguide", "매장 안내"),
    ("expguide", "체험 안내"),
    ("expagerange", "체험 가능 연령"),
    ("expagerangeleports", "체험 가능 연령"),
    ("agelimit", "관람 가능 연령"),
    ("reservation", "예약 안내"),
    ("chkbabycarriage", "유모차 대여"),
    ("chkbabycarriageculture", "유모차 대여"),
    ("chkbabycarriageleports", "유모차 대여"),
    ("chkbabycarriageshopping", "유모차 대여"),
    ("chkpet", "반려동물 동반"),
    ("chkpetculture", "반려동물 동반"),
    ("chkpetleports", "반려동물 동반"),
    ("chkpetshopping", "반려동물 동반"),
    ("chkcreditcard", "신용카드 가능"),
    ("chkcreditcardculture", "신용카드 가능"),
    ("chkcreditcardleports", "신용카드 가능"),
    ("chkcreditcardshopping", "신용카드 가능"),
    ("chkcreditcardfood", "신용카드 가능"),
]

_TAG_RE = re.compile(r"</?(?:[a-zA-Z][a-zA-Z0-9]*|!--)[^>]*>")
_BR_RE = re.compile(r"<\s*br\s*/?\s*>", re.IGNORECASE)
_HREF_RE = re.compile(r'href\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)
_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)


def _clean_text(value: Any) -> str:
    """API 문자열의 <br>과 HTML 태그를 정리해 순수 텍스트로 반환한다."""
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    text = _BR_RE.sub("\n", text)
    text = _TAG_RE.sub("", text)
    text = html.unescape(text)
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _format_html_text(value: Any) -> str:
    """정제된 텍스트를 안전한 HTML(<br /> 포함) 문자열로 변환한다."""
    cleaned = _clean_text(value)
    if not cleaned:
        return ""
    return html.escape(cleaned).replace("\n", "<br />")


def _extract_url(raw: Any) -> str:
    """<a> 태그나 텍스트에서 실제 http/https URL을 추출한다."""
    if not raw:
        return ""
    text = str(raw).strip()
    href_match = _HREF_RE.search(text)
    if href_match:
        return href_match.group(1).strip()
    url_match = _URL_RE.search(text)
    if url_match:
        return url_match.group(0).strip()
    return ""


def _to_https(url: str) -> str:
    """공공데이터 이미지 URL의 http 스킴을 https로 통일한다."""
    cleaned = (url or "").strip()
    if cleaned.startswith("http://"):
        return "https://" + cleaned[len("http://") :]
    return cleaned


def _format_yyyymmdd(value: str) -> str:
    """YYYYMMDD 날짜 문자열을 YYYY.MM.DD 형식으로 바꾼다."""
    digits = re.sub(r"\D", "", value or "")
    if len(digits) == 8:
        return f"{digits[:4]}.{digits[4:6]}.{digits[6:]}"
    return value


def _extract_region_label(addr1: str, ldong_regn_cd: str | None) -> str:
    """주소 또는 법정동 코드에서 짧은 지역명(예: 강원, 서울)을 뽑아낸다."""
    if ldong_regn_cd and str(ldong_regn_cd) in config.LDONG_REGN_NAME_MAP:
        return config.LDONG_REGN_NAME_MAP[str(ldong_regn_cd)]
    if addr1:
        first_token = addr1.strip().split()[0]
        for short_name in ("서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주"):
            if first_token.startswith(short_name):
                return short_name
        return first_token
    return "국내"


def _extract_json_block(text: str) -> dict[str, Any] | None:
    """모델 응답 문자열에서 JSON 객체를 파싱한다."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        parsed = json.loads(stripped[start : end + 1])
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def _build_gemini_prompt(
    title: str,
    blog_category: str,
    category_name: str,
    region_name: str,
    addr: str,
    overview: str,
    info_rows: list[tuple[str, str]],
    pet_rows: list[tuple[str, str]],
    photo_keywords: list[str] | None = None,
) -> str:
    """20대 여성 에디터 어투의 사실 기반 여행 블로그 원고 생성용 Gemini 프롬프트를 만든다."""
    facts_lines = [f"- {label}: {val}" for label, val in info_rows[:12]]
    if pet_rows:
        facts_lines.append(
            "- 반려동물 동반: " + ", ".join(f"{k}={v}" for k, v in pet_rows[:4])
        )
    facts_text = "\n".join(facts_lines) if facts_lines else "- 추가 운영 정보 없음"

    category_focus = {
        "그날의 장소": "공간의 분위기와 볼거리, 산책하거나 천천히 머물기 좋은 포인트 중심으로 써 주세요.",
        "그날의 미식": "대표 메뉴, 가게 분위기, 식사나 커피 한 잔 즐기기 좋은 포인트를 담아 주세요.",
        "그날의 여정": "코스 동선, 전체 소요시간, 구간별 풍경과 이동 포인트를 흐름 있게 정리해 주세요.",
    }.get(blog_category, "여행지 매력과 방문 포인트 중심으로 작성해 주세요.")

    kw_hint = ""
    if photo_keywords:
        kw_hint = f"[사진 분위기 참고 키워드] {', '.join(photo_keywords[:8])}\n"

    return (
        "당신은 감성적이고 담백한 국내 여행 블로그 '그날의 온도(OndoTrip)'를 운영하는 20대 여성 에디터입니다.\n"
        f"이번 글은 [{blog_category}] 카테고리에 올라갑니다. {category_focus}\n\n"
        "[어투 및 작성 원칙]\n"
        "1. 친한 친구나 구독자에게 차분하고 다정하게 추천하듯 자연스러운 해요체(~해요, ~더라고요, ~좋아요, ~추천드려요)로 쓰세요.\n"
        "2. 과한 이모지, 오글거리는 유행어(대박, 찐맛집, 레전드, 감성 폭발 등), 어색한 AI 번역투, 제목 앞 딱딱한 대괄호([카테고리]) 남발은 피하세요.\n"
        "3. 오직 아래 한국관광공사 공공데이터(사실 정보)만 바탕으로 작성하세요. 데이터에 없는 요금, 시간, 메뉴, 개인적인 방문 경험담('어제 직접 다녀왔는데' 등)을 절대 지어내지 마세요.\n\n"
        f"[장소/코스명] {title}\n"
        f"[블로그 카테고리] {blog_category}\n"
        f"[지역/유형] {region_name} / {category_name}\n"
        f"[주소] {addr}\n"
        f"{kw_hint}"
        f"[개요] {overview[:1500]}\n"
        f"[상세정보]\n{facts_text}\n\n"
        "반드시 아래 JSON 형식으로만 응답하세요:\n"
        "{\n"
        '  "post_title": "검색에 잘 노출되면서도 자연스러운 20대 여성 블로그 스타일 제목 (35자 내외)",\n'
        '  "subtitle": "제목 아래에 놓일 담백한 한 줄 요약 (20~40자)",\n'
        '  "lead_paragraph": "부드럽게 이야기를 여는 도입 문단 (2~3문장, 자연스러운 해요체)",\n'
        '  "story_paragraphs": [\n'
        '    "공공데이터 개요를 자연스러운 해요체로 풀어쓴 본문 첫 번째 문단 (2~4문장)",\n'
        '    "분위기와 볼거리, 함께 즐길 수 있는 포인트를 이어가는 두 번째 문단 (2~4문장)"\n'
        "  ],\n"
        '  "highlights": ["이곳이 좋았던 매력 포인트 1 (해요체)", "매력 포인트 2 (해요체)", "매력 포인트 3 (해요체)"],\n'
        '  "visit_tips": ["실제 운영정보 기반 방문 팁 1 (해요체)", "방문 팁 2 (해요체)", "방문 팁 3 (해요체)"],\n'
        '  "closing_note": "잔잔한 여운을 남기며 일정을 권하는 마무리 1~2문장 (해요체)"\n'
        "}"
    )


def _split_story_paragraphs(overview: str) -> list[str]:
    """개요 텍스트를 자연스러운 2개 내외 문단으로 나눈다."""
    sentences = [
        s.strip()
        for s in re.split(r"(?<=[.!?다요])\s+", overview.replace("\n", " "))
        if len(s.strip()) > 10
    ]
    if not sentences:
        return [overview.strip()] if overview.strip() else []
    if len(sentences) <= 3:
        return [" ".join(sentences)]
    mid = (len(sentences) + 1) // 2
    return [" ".join(sentences[:mid]), " ".join(sentences[mid:])]


def _generate_fallback_copy(
    title: str,
    blog_category: str,
    category_name: str,
    region_name: str,
    addr: str,
    overview: str,
    info_rows: list[tuple[str, str]],
    pet_rows: list[tuple[str, str]],
) -> dict[str, Any]:
    """Gemini 호출이 실패했을 때 공공데이터로 자연스러운 해요체 원고를 구성한다."""
    story_paragraphs = _split_story_paragraphs(overview)
    sentences = [
        s.strip()
        for s in re.split(r"(?<=[.!?다요])\s+", overview.replace("\n", " "))
        if len(s.strip()) > 10
    ]
    lead = (
        f"{region_name} 나들이를 계획 중이라면 '{title}'에 한 번 들러보시는 건 어떨까요? "
        + (" ".join(sentences[:2]) if sentences else f"{category_name} 특유의 분위기를 여유롭게 느끼기 좋아요.")
    )

    highlights = [
        f"{region_name}에서 가볍게 들러 분위기를 즐기기 좋은 {category_name}이에요.",
        (
            f"{addr}에 자리하고 있어 주변 동선과 함께 묶어 다녀오기 좋아요."
            if addr
            else f"{title}만의 차분한 매력과 볼거리를 천천히 둘러보기 좋아요."
        ),
        (
            sentences[2]
            if len(sentences) > 2
            else "사계절 언제 찾아도 계절마다 다른 풍경을 마주할 수 있어요."
        ),
    ]

    info_dict = dict(info_rows)
    tips: list[str] = []
    for key in (
        "대표 메뉴",
        "영업시간",
        "이용시간",
        "코스 총 소요시간",
        "코스 총거리",
        "쉬는날",
        "주차 시설",
        "주차 요금",
        "이용요금",
        "입장료",
    ):
        if key in info_dict:
            tips.append(f"{key}은(는) {info_dict[key].splitlines()[0]} 기준이라 방문 전 참고하시면 좋아요.")
    if pet_rows:
        tips.append(f"반려동물 동반 정보({pet_rows[0][1]})도 함께 확인해 두시면 편리해요.")
    if not tips:
        tips.append("방문 전 공식 안내 연락처나 홈페이지로 당일 운영 여부를 가볍게 확인해 보시는 걸 추천드려요.")

    return {
        "post_title": f"{region_name} {title}, 천천히 머물기 좋은 {category_name}",
        "subtitle": f"{region_name}에서 만난 {title}의 소소한 매력과 방문 정보를 정리했어요",
        "lead_paragraph": lead,
        "story_paragraphs": story_paragraphs,
        "highlights": highlights[:3],
        "visit_tips": tips[:3],
        "closing_note": "일정에 작은 쉼표가 필요한 날, 오늘 소개해 드린 공간에서 기분 좋은 시간 보내시길 바라요.",
        "ai_model": "rule-based-fallback",
    }


def _call_gemini_editorial(prompt: str) -> dict[str, Any] | None:
    """설정된 Gemini 모델 우선순위대로 호출해 JSON 원고를 받아온다."""
    if not config.GEMINI_API_KEY:
        return None

    candidate_models = list(
        dict.fromkeys(
            [
                config.GEMINI_MODEL,
                "gemini-3.1-flash-lite",
                "gemini-flash-lite-latest",
                "gemini-3.8-flash",
                "gemini-3.7-flash",
                "gemini-3.6-flash",
                "gemini-3.5-flash",
            ]
        )
    )

    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.75},
    }

    with config.create_http_session() as session:
        for model in candidate_models:
            if not model:
                continue
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{model}:generateContent?key={config.GEMINI_API_KEY}"
            )
            try:
                resp = session.post(url, json=payload, timeout=15)
                if resp.status_code != 200:
                    logger.warning(
                        "Gemini 모델(%s) 응답 오류 %s: %s",
                        model,
                        resp.status_code,
                        resp.text[:160],
                    )
                    continue
                data = resp.json()
                candidates = data.get("candidates") or []
                if not candidates:
                    continue
                parts = candidates[0].get("content", {}).get("parts") or []
                raw_text = "".join(part.get("text", "") for part in parts)
                parsed = _extract_json_block(raw_text)
                if parsed and parsed.get("post_title") and parsed.get("lead_paragraph"):
                    parsed["ai_model"] = model
                    return parsed
            except Exception as exc:
                logger.warning("Gemini 모델(%s) 호출 실패: %s", model, exc)

    return None


def _collect_info_rows(
    common: dict[str, Any], intro: dict[str, Any]
) -> list[tuple[str, str]]:
    """common과 intro에서 비어 있지 않은 방문 정보 항목을 순서대로 정리한다."""
    rows: list[tuple[str, str]] = []
    seen_labels: set[str] = set()

    addr = " ".join(
        part for part in (_clean_text(common.get("addr1")), _clean_text(common.get("addr2"))) if part
    )
    zipcode = _clean_text(common.get("zipcode"))
    if addr:
        rows.append(("주소", f"{addr} (우편번호 {zipcode})" if zipcode else addr))
        seen_labels.add("주소")

    tel = _clean_text(common.get("tel"))
    telname = _clean_text(common.get("telname"))
    if tel:
        rows.append(("대표 전화", f"{tel} ({telname})" if telname else tel))
        seen_labels.add("대표 전화")

    homepage_url = _extract_url(common.get("homepage"))
    if homepage_url:
        rows.append(("홈페이지", homepage_url))
        seen_labels.add("홈페이지")

    for field, label in INTRO_FIELD_LABELS:
        raw_val = intro.get(field)
        cleaned = _clean_text(raw_val)
        if not cleaned or cleaned in ("0", "선택안함"):
            continue
        if field in ("eventstartdate", "eventenddate"):
            cleaned = _format_yyyymmdd(cleaned)
        if label in seen_labels:
            continue
        seen_labels.add(label)
        rows.append((label, cleaned))

    return rows


def _collect_pet_rows(pet_info: dict[str, Any]) -> list[tuple[str, str]]:
    """반려동물 동반여행(detailPetTour2) 정보를 한글 항목 목록으로 정리한다."""
    if not pet_info:
        return []
    mapping = [
        ("acmpyTypeCd", "동반 가능 구분"),
        ("acmpyPsblCpam", "동반 가능 견종"),
        ("acmpyPsblCp", "동반 가능 견종"),
        ("acmpyNeedMtr", "필수 준비사항"),
        ("relaPosesFclty", "구비 시설"),
        ("relaRntlPrdlst", "대여 품목"),
        ("relaPurcPrdlst", "구매 가능 품목"),
        ("relaFrnshPrdlst", "비치 품목"),
        ("relaAcdntRiskMtr", "안전 유의사항"),
        ("etcAcmpyInfo", "기타 동반 안내"),
        ("petTursmInfo", "반려동물 관광정보"),
    ]
    rows: list[tuple[str, str]] = []
    seen_labels: set[str] = set()
    for field, label in mapping:
        cleaned = _clean_text(pet_info.get(field))
        if cleaned and label not in seen_labels:
            seen_labels.add(label)
            rows.append((label, cleaned))
    return rows


def _collect_gallery_urls(
    common: dict[str, Any],
    images: list[dict[str, Any]],
    photo_gallery: list[dict[str, Any]] | None = None,
) -> tuple[
    str,
    str,
    list[dict[str, str]],
    list[dict[str, Any]],
    list[str],
]:
    """대표 이미지, KorService2 갤러리, 관광사진(PhotoGalleryService1) 보강 카드, 저작권 코드를 수집한다."""
    hero_url = _to_https(str(common.get("firstimage") or ""))
    hero_credit = "출처 · 한국관광공사 국문 관광정보 서비스" if hero_url else ""
    copyright_codes: list[str] = []
    if common.get("cpyrhtDivCd"):
        copyright_codes.append(str(common["cpyrhtDivCd"]).strip())

    kor_gallery: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    if hero_url:
        seen_urls.add(hero_url)

    for img in images:
        orig_url = _to_https(str(img.get("originimgurl") or ""))
        if not orig_url:
            continue
        if img.get("cpyrhtDivCd"):
            copyright_codes.append(str(img["cpyrhtDivCd"]).strip())
        if not hero_url:
            hero_url = orig_url
            hero_credit = "출처 · 한국관광공사 국문 관광정보 서비스"
            seen_urls.add(orig_url)
            continue
        if orig_url in seen_urls:
            continue
        seen_urls.add(orig_url)
        kor_gallery.append(
            {
                "url": orig_url,
                "name": _clean_text(img.get("imgname")) or "관광지 사진",
            }
        )
        if len(kor_gallery) >= 4:
            break

    photo_cards: list[dict[str, Any]] = []
    for item in photo_gallery or []:
        p_url = _to_https(str(item.get("url") or ""))
        if not p_url or p_url in seen_urls:
            continue
        seen_urls.add(p_url)
        photographer = _clean_text(item.get("photographer")) or "한국관광공사"
        p_title = _clean_text(item.get("title")) or "국내 여행 풍경"
        p_date = _clean_text(item.get("photo_date"))
        if not hero_url:
            hero_url = p_url
            hero_credit = (
                f"출처 · 한국관광공사 관광사진갤러리 ({photographer})"
            )
            continue
        photo_cards.append(
            {
                "url": p_url,
                "title": p_title,
                "photo_date": p_date,
                "location": _clean_text(item.get("location")),
                "photographer": photographer,
                "keywords": [
                    _clean_text(k) for k in (item.get("keywords") or []) if _clean_text(k)
                ][:3],
                "matched_spot": _clean_text(item.get("matched_spot")),
            }
        )
        if len(photo_cards) >= config.PHOTO_GALLERY_MAX_IMAGES:
            break

    return hero_url, hero_credit, kor_gallery, photo_cards, copyright_codes


def _resolve_copyright_notice(
    copyright_codes: list[str],
    photo_photographers: list[str] | None = None,
) -> str:
    """공공누리 유형 및 관광사진갤러리 촬영자 출처 문구를 생성한다."""
    normalized = {c.upper() for c in copyright_codes if c}
    if "TYPE3" in normalized:
        kogl_text = "공공누리 제3유형(출처표시 + 변경금지)"
        rule_note = "본 포스트에 포함된 한국관광공사 제공 이미지는 원본 그대로 사용되었으며 무단 변경·가공을 하지 않았어요."
    elif "TYPE1" in normalized:
        kogl_text = "공공누리 제1유형(출처표시)"
        rule_note = "한국관광공사 공공데이터(TourAPI) 기준 출처를 표기하여 제공해요."
    else:
        kogl_text = "공공누리(한국관광공사 관광정보 서비스 기준)"
        rule_note = "제공된 공공데이터 및 이미지의 저작권은 한국관광공사에 있어요."

    extra_photo_source = ""
    unique_photographers = [
        p for p in dict.fromkeys(photo_photographers or []) if p
    ]
    if unique_photographers:
        joined_credits = ", ".join(unique_photographers)
        extra_photo_source = (
            f" · <strong>추가 사진</strong>: 한국관광공사 관광사진갤러리"
            f"(PhotoGalleryService1 · 촬영 {html.escape(joined_credits)})"
        )

    return (
        f"<strong>데이터 및 사진 출처</strong>: 한국관광공사 국문 관광정보 서비스(TourAPI 4.4) "
        f"| <strong>저작권</strong>: {html.escape(kogl_text)}{extra_photo_source}<br />"
        f'<span style="color:#8c8378;font-size:12px;">{html.escape(rule_note)}</span>'
    )


def _render_extra_info_html(
    content_type_id: str, info_list: list[dict[str, Any]]
) -> str:
    """반복정보(detailInfo2)를 미니멀 에디토리얼 톤 카드로 렌더링한다."""
    if not info_list:
        return ""

    blocks: list[str] = []
    if content_type_id == "25":
        for idx, item in enumerate(info_list, start=1):
            subname = _clean_text(item.get("subname"))
            suboverview = _format_html_text(item.get("subdetailoverview"))
            subimg = _to_https(str(item.get("subdetailimg") or ""))
            if not (subname or suboverview):
                continue
            img_html = (
                f'<img src="{html.escape(subimg)}" alt="{html.escape(subname or "코스 사진")}" '
                'style="width:100%;max-height:340px;object-fit:cover;border-radius:10px;margin-top:12px;display:block;" />'
                if subimg
                else ""
            )
            blocks.append(
                '<div style="padding:18px 20px;background:#faf8f5;border:1px solid #eae4db;'
                'border-radius:12px;margin-bottom:12px;">'
                f'<div style="font-size:12px;font-weight:700;letter-spacing:0.04em;color:#3d5a4c;margin-bottom:4px;">COURSE {idx:02d}</div>'
                f'<div style="font-size:16px;font-weight:700;color:#262626;margin-bottom:8px;">{html.escape(subname)}</div>'
                f'<div style="font-size:14.5px;line-height:1.8;color:#4a453f;">{suboverview}</div>'
                f"{img_html}</div>"
            )
    else:
        for item in info_list:
            infoname = _clean_text(item.get("infoname"))
            infotext = _format_html_text(item.get("infotext"))
            if not (infoname or infotext):
                continue
            blocks.append(
                '<div style="padding:14px 18px;background:#faf8f5;border-left:3px solid #3d5a4c;'
                'border-radius:0 10px 10px 0;margin-bottom:10px;">'
                f'<div style="font-weight:700;font-size:14.5px;color:#262626;margin-bottom:4px;">{html.escape(infoname)}</div>'
                f'<div style="font-size:14px;line-height:1.75;color:#4a453f;">{infotext}</div>'
                "</div>"
            )

    if not blocks:
        return ""
    heading = "코스 따라 둘러보기" if content_type_id == "25" else "조금 더 알아두면 좋은 정보"
    return (
        '<section style="margin:34px 0;">'
        f'<h2 style="font-size:18px;font-weight:700;color:#262626;margin:0 0 16px;padding-bottom:10px;border-bottom:1px solid #eae4db;letter-spacing:-0.01em;">{heading}</h2>'
        + "".join(blocks)
        + "</section>"
    )


def _render_map_html(title: str, addr1: str, mapx: Any, mapy: Any) -> str:
    """OpenStreetMap 무료 iframe 약도와 정돈된 톤의 길찾기 버튼을 만든다."""
    try:
        lon = float(str(mapx).strip())
        lat = float(str(mapy).strip())
    except (TypeError, ValueError):
        return ""

    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return ""

    bbox = f"{lon - 0.007:.6f},{lat - 0.005:.6f},{lon + 0.007:.6f},{lat + 0.005:.6f}"
    osm_embed_url = (
        f"https://www.openstreetmap.org/export/embed.html?bbox={quote(bbox, safe=',')}"
        f"&layer=mapnik&marker={lat:.6f},{lon:.6f}"
    )
    naver_query = quote(f"{title} {addr1}".strip())
    naver_url = f"https://map.naver.com/p/search/{naver_query}"
    kakao_url = f"https://map.kakao.com/link/map/{quote(title)},{lat:.6f},{lon:.6f}"
    google_url = f"https://www.google.com/maps/search/?api=1&query={lat:.6f},{lon:.6f}"

    btn_style = (
        "display:inline-block;padding:9px 15px;border-radius:8px;text-decoration:none;"
        "font-size:13.5px;font-weight:600;margin:4px 8px 4px 0;"
    )
    return (
        '<section style="margin:34px 0;">'
        '<h2 style="font-size:18px;font-weight:700;color:#262626;margin:0 0 16px;padding-bottom:10px;border-bottom:1px solid #eae4db;letter-spacing:-0.01em;">위치 및 길찾기</h2>'
        '<div style="border-radius:14px;overflow:hidden;border:1px solid #eae4db;background:#faf8f5;">'
        f'<iframe title="{html.escape(title)} 위치 지도" src="{osm_embed_url}" '
        'style="width:100%;height:320px;border:0;display:block;" loading="lazy"></iframe>'
        "</div>"
        '<div style="margin-top:14px;">'
        f'<a href="{naver_url}" target="_blank" rel="noopener noreferrer" style="{btn_style}background:#3d5a4c;color:#ffffff;">네이버 지도로 보기</a>'
        f'<a href="{kakao_url}" target="_blank" rel="noopener noreferrer" style="{btn_style}background:#f3ede2;color:#262626;border:1px solid #e2d9cb;">카카오맵으로 보기</a>'
        f'<a href="{google_url}" target="_blank" rel="noopener noreferrer" style="{btn_style}background:#ffffff;color:#4a453f;border:1px solid #dcd5ca;">구글 지도로 보기</a>'
        "</div>"
        f'<p style="margin:10px 0 0;font-size:12px;color:#8c8378;">위치 좌표 · 위도 {lat:.6f}, 경도 {lon:.6f}</p>'
        "</section>"
    )


def generate_blog_post(
    bundle: dict[str, Any], category_override: str | None = None
) -> dict[str, Any]:
    """수집된 관광정보와 보강 사진을 바탕으로 20대 여성 어투의 미니멀 에디토리얼 포스트를 생성한다."""
    content_id = str(bundle.get("content_id", ""))
    ctype = str(bundle.get("content_type_id", "12"))
    common = bundle.get("common") or {}
    intro = bundle.get("intro") or {}
    info_list = bundle.get("info_list") or []
    images = bundle.get("images") or []
    photo_gallery = bundle.get("photo_gallery") or []
    pet_info = bundle.get("pet_info") or {}

    title = _clean_text(common.get("title")) or f"국내 여행지 ({content_id})"
    blog_category = config.resolve_blog_category(category_override, ctype, title=title)
    category_name = config.CONTENT_TYPE_NAME_MAP.get(ctype, "여행지")
    addr1 = _clean_text(common.get("addr1"))
    region_name = _extract_region_label(addr1, common.get("lDongRegnCd"))
    overview = _clean_text(common.get("overview"))

    info_rows = _collect_info_rows(common, intro)
    pet_rows = _collect_pet_rows(pet_info)
    hero_url, hero_credit, kor_gallery, photo_cards, copyright_codes = (
        _collect_gallery_urls(common, images, photo_gallery)
    )

    photo_kw_hints: list[str] = []
    for p_item in photo_gallery:
        for kw in p_item.get("keywords") or []:
            if kw and kw not in photo_kw_hints:
                photo_kw_hints.append(kw)

    prompt = _build_gemini_prompt(
        title=title,
        blog_category=blog_category,
        category_name=category_name,
        region_name=region_name,
        addr=addr1,
        overview=overview,
        info_rows=info_rows,
        pet_rows=pet_rows,
        photo_keywords=photo_kw_hints,
    )
    editorial = _call_gemini_editorial(prompt)
    if editorial is None:
        editorial = _generate_fallback_copy(
            title=title,
            blog_category=blog_category,
            category_name=category_name,
            region_name=region_name,
            addr=addr1,
            overview=overview,
            info_rows=info_rows,
            pet_rows=pet_rows,
        )

    post_title = str(editorial.get("post_title") or title).strip()
    subtitle = str(editorial.get("subtitle") or "").strip()
    lead_paragraph = str(editorial.get("lead_paragraph") or "").strip()
    raw_stories = editorial.get("story_paragraphs") or []
    story_paragraphs = [
        str(p).strip() for p in raw_stories if str(p).strip()
    ]
    if not story_paragraphs and overview:
        story_paragraphs = _split_story_paragraphs(overview)

    highlights = [
        str(x).strip()
        for x in (editorial.get("highlights") or [])
        if str(x).strip()
    ]
    visit_tips = [
        str(x).strip()
        for x in (editorial.get("visit_tips") or [])
        if str(x).strip()
    ]
    closing_note = str(editorial.get("closing_note") or "").strip()

    # Blogger 공식 3대 카테고리 + '카테고리-지역' 서브 라벨 부여
    labels = [blog_category]
    if region_name and region_name != "국내":
        labels.append(f"{blog_category}-{region_name}")

    # 1. Warm Editorial Minimal 헤더
    pet_meta_pill = (
        '<span style="display:inline-block;margin-left:8px;padding:2px 9px;border-radius:999px;'
        'background:#eef3f0;color:#3d5a4c;font-size:11.5px;font-weight:600;">반려동물 동반</span>'
        if pet_rows
        else ""
    )
    subtitle_html = (
        f'<p style="margin:0 0 10px;font-size:15px;line-height:1.6;color:#736c63;">{html.escape(subtitle)}</p>'
        if subtitle
        else ""
    )
    addr_html = (
        f'<p style="margin:0;font-size:13px;color:#8c8378;">{html.escape(addr1)}</p>'
        if addr1
        else ""
    )
    header_html = (
        '<header style="padding:4px 0 22px;border-bottom:1px solid #eae4db;margin-bottom:26px;">'
        '<div style="margin-bottom:10px;font-size:12px;font-weight:600;letter-spacing:0.04em;color:#3d5a4c;">'
        f'{html.escape(blog_category)} · {html.escape(region_name)} · {html.escape(category_name)}{pet_meta_pill}'
        "</div>"
        f'<h1 style="font-size:26px;line-height:1.38;font-weight:700;color:#262626;letter-spacing:-0.02em;margin:0 0 10px;">{html.escape(title)}</h1>'
        f"{subtitle_html}{addr_html}"
        "</header>"
    )

    # 2. 와이드 대표 이미지
    hero_html = ""
    if hero_url:
        hero_caption = f"{title} ({hero_credit})" if hero_credit else title
        hero_html = (
            '<figure style="margin:0 0 28px;text-align:center;">'
            f'<img src="{html.escape(hero_url)}" alt="{html.escape(title)} 대표 사진" '
            'style="width:100%;max-width:760px;height:auto;border-radius:14px;display:block;margin:0 auto;box-shadow:0 8px 28px rgba(38,38,38,0.06);" />'
            f'<figcaption style="margin-top:10px;font-size:12px;color:#8c8378;">{html.escape(hero_caption)}</figcaption>'
            "</figure>"
        )

    # 3. 도입 에세이 카드 + 본문 스토리 + 매력 포인트 & 방문 팁 2단 카드
    story_heading = {
        "그날의 미식": "공간과 맛 이야기",
        "그날의 여정": "길 위에서 만나는 풍경",
    }.get(blog_category, "천천히 둘러보는 이야기")

    story_body_html = "".join(
        f'<p style="margin:0 0 16px;font-size:15.5px;line-height:1.95;color:#333333;">{html.escape(p)}</p>'
        for p in story_paragraphs
    )
    story_section = (
        '<div style="margin:26px 0 8px;">'
        f'<h2 style="font-size:18px;font-weight:700;color:#262626;margin:0 0 14px;padding-bottom:10px;border-bottom:1px solid #eae4db;letter-spacing:-0.01em;">{story_heading}</h2>'
        f"{story_body_html}</div>"
        if story_body_html
        else ""
    )

    highlights_items = "".join(
        '<li style="list-style:none;margin-bottom:10px;line-height:1.75;font-size:14px;color:#333333;">'
        f'<span style="color:#3d5a4c;font-weight:700;margin-right:8px;">{idx:02d}</span>{html.escape(item)}'
        "</li>"
        for idx, item in enumerate(highlights, start=1)
    )
    tips_items = "".join(
        '<li style="list-style:none;margin-bottom:10px;line-height:1.75;font-size:14px;color:#333333;">'
        f'<span style="color:#3d5a4c;font-weight:700;margin-right:8px;">{idx:02d}</span>{html.escape(item)}'
        "</li>"
        for idx, item in enumerate(visit_tips, start=1)
    )

    two_col_cards = (
        '<div style="display:flex;flex-wrap:wrap;gap:14px;margin:24px 0 6px;">'
        '<div style="flex:1 1 280px;background:#ffffff;border:1px solid #eae4db;border-radius:14px;padding:20px;">'
        '<h3 style="margin:0 0 14px;font-size:15px;font-weight:700;color:#262626;letter-spacing:-0.01em;">이곳이 좋았던 이유</h3>'
        f'<ul style="margin:0;padding:0;">{highlights_items}</ul>'
        "</div>"
        '<div style="flex:1 1 280px;background:#faf8f5;border:1px solid #eae4db;border-radius:14px;padding:20px;">'
        '<h3 style="margin:0 0 14px;font-size:15px;font-weight:700;color:#3d5a4c;letter-spacing:-0.01em;">다녀오기 전 작은 팁</h3>'
        f'<ul style="margin:0;padding:0;">{tips_items}</ul>'
        "</div>"
        "</div>"
        if (highlights_items or tips_items)
        else ""
    )

    intro_section_html = (
        '<section style="margin:26px 0;">'
        '<div style="background:#faf8f5;border-left:3px solid #3d5a4c;padding:18px 20px;border-radius:0 12px 12px 0;margin:0 0 24px;">'
        f'<p style="margin:0;font-size:15.5px;line-height:1.9;color:#262626;">{html.escape(lead_paragraph)}</p>'
        "</div>"
        f"{story_section}{two_col_cards}"
        "</section>"
    )

    # 4. 한눈에 보는 방문 정보 표
    table_rows_html = ""
    for label, val in info_rows:
        if label == "홈페이지":
            safe_url = html.escape(val)
            cell_html = f'<a href="{safe_url}" target="_blank" rel="noopener noreferrer" style="color:#3d5a4c;text-decoration:underline;word-break:break-all;">{safe_url}</a>'
        else:
            cell_html = _format_html_text(val)
        table_rows_html += (
            "<tr>"
            f'<th style="width:28%;min-width:105px;text-align:left;padding:12px 10px;border-bottom:1px solid #ece7df;color:#736c63;font-size:13.5px;font-weight:600;vertical-align:top;">{html.escape(label)}</th>'
            f'<td style="padding:12px 10px;border-bottom:1px solid #ece7df;color:#262626;font-size:14px;line-height:1.7;">{cell_html}</td>'
            "</tr>"
        )

    info_table_html = (
        '<section style="margin:34px 0;">'
        '<h2 style="font-size:18px;font-weight:700;color:#262626;margin:0 0 12px;padding-bottom:10px;border-bottom:1px solid #eae4db;letter-spacing:-0.01em;">방문 전에 참고할 정보</h2>'
        '<table style="width:100%;border-collapse:collapse;border-top:1px solid #262626;">'
        f"<tbody>{table_rows_html}</tbody>"
        "</table></section>"
        if table_rows_html
        else ""
    )

    # 5. 추가 상세 안내 및 반려동물 안내
    extra_info_html = _render_extra_info_html(ctype, info_list)
    pet_html = ""
    if pet_rows:
        pet_items_html = "".join(
            f'<li style="margin-bottom:6px;line-height:1.7;"><strong>{html.escape(k)}</strong> · {_format_html_text(v)}</li>'
            for k, v in pet_rows
        )
        pet_html = (
            '<section style="margin:28px 0;background:#eef3f0;border:1px solid #d5e0da;border-radius:14px;padding:18px 20px;">'
            '<h2 style="font-size:16px;font-weight:700;color:#3d5a4c;margin:0 0 10px;">반려동물과 함께 가신다면</h2>'
            f'<ul style="margin:0;padding-left:18px;font-size:14px;color:#262626;">{pet_items_html}</ul>'
            "</section>"
        )

    # 6. 기본 포토 갤러리 + 한국관광공사 관광사진갤러리 보강 섹션
    kor_gallery_html = ""
    if kor_gallery:
        kor_cards = "".join(
            '<div style="flex:1 1 240px;max-width:calc(50% - 6px);min-width:210px;">'
            f'<img src="{html.escape(g["url"])}" alt="{html.escape(g["name"])}" '
            'style="width:100%;height:auto;border-radius:12px;display:block;border:1px solid #eae4db;" />'
            "</div>"
            for g in kor_gallery
        )
        kor_gallery_html = (
            '<section style="margin:34px 0;">'
            '<h2 style="font-size:18px;font-weight:700;color:#262626;margin:0 0 16px;padding-bottom:10px;border-bottom:1px solid #eae4db;letter-spacing:-0.01em;">조금 더 담아본 사진들</h2>'
            f'<div style="display:flex;flex-wrap:wrap;gap:12px;">{kor_cards}</div>'
            "</section>"
        )

    photo_cards_html = ""
    photo_photographers: list[str] = []
    if photo_cards:
        rendered_photo_cards = ""
        for p_card in photo_cards:
            photo_photographers.append(p_card["photographer"])
            meta_parts = [p_card["title"]]
            if p_card["photo_date"]:
                meta_parts.append(f"촬영 {p_card['photo_date']}")
            meta_parts.append(p_card["photographer"])
            tag_chips = "".join(
                f'<span style="display:inline-block;margin:4px 4px 0 0;padding:2px 8px;border-radius:999px;background:#ffffff;border:1px solid #e6dfd5;font-size:11px;color:#736c63;">#{html.escape(t)}</span>'
                for t in p_card["keywords"]
            )
            rendered_photo_cards += (
                '<div style="flex:1 1 260px;max-width:calc(50% - 7px);min-width:220px;background:#faf8f5;border:1px solid #eae4db;border-radius:12px;overflow:hidden;">'
                f'<img src="{html.escape(p_card["url"])}" alt="{html.escape(p_card["title"])}" '
                'style="width:100%;height:auto;display:block;" />'
                '<div style="padding:11px 13px;">'
                f'<div style="font-size:12.5px;font-weight:600;color:#262626;line-height:1.5;">{html.escape(" · ".join(meta_parts))}</div>'
                f'{f"<div>{tag_chips}</div>" if tag_chips else ""}'
                "</div></div>"
            )
        photo_cards_html = (
            '<section style="margin:34px 0;">'
            '<h2 style="font-size:18px;font-weight:700;color:#262626;margin:0 0 6px;letter-spacing:-0.01em;">함께 담아본 풍경</h2>'
            '<p style="margin:0 0 16px;font-size:13px;color:#736c63;padding-bottom:10px;border-bottom:1px solid #eae4db;">한국관광공사 관광사진갤러리에서 전하는 이곳의 또 다른 시선이에요.</p>'
            f'<div style="display:flex;flex-wrap:wrap;gap:14px;">{rendered_photo_cards}</div>'
            "</section>"
        )

    # 대표 이미지가 관광사진갤러리에서 승격된 경우에도 푸터 촬영자 목록에 포함
    if hero_credit.startswith("출처 · 한국관광공사 관광사진갤러리"):
        for p_item in photo_gallery:
            cred = _clean_text(p_item.get("photographer"))
            if cred:
                photo_photographers.insert(0, cred)
                break

    # 7. 무료 지도 및 길찾기
    map_html = _render_map_html(
        title=title,
        addr1=addr1,
        mapx=common.get("mapx"),
        mapy=common.get("mapy"),
    )

    # 8. 마무리 문장 + 공공누리/촬영자 출처 푸터
    closing_html = (
        '<div style="margin:30px 0 22px;padding:18px 20px;background:#faf8f5;border-radius:12px;border:1px solid #eae4db;text-align:center;">'
        f'<p style="margin:0;font-size:14.5px;line-height:1.8;color:#4a453f;">{html.escape(closing_note)}</p>'
        "</div>"
        if closing_note
        else ""
    )
    copyright_notice = _resolve_copyright_notice(copyright_codes, photo_photographers)
    footer_html = (
        '<footer style="margin-top:24px;padding:16px 18px;background:#faf8f5;border:1px solid #eae4db;'
        'border-radius:10px;font-size:12.5px;line-height:1.7;color:#736c63;">'
        f"{copyright_notice}"
        "</footer>"
    )

    full_html = (
        '<div style="max-width:760px;margin:0 auto;padding:8px 4px;background:#ffffff;font-family:-apple-system,BlinkMacSystemFont,\'Apple SD Gothic Neo\',\'Pretendard\',\'Malgun Gothic\',sans-serif;color:#262626;">'
        f"{header_html}{hero_html}{intro_section_html}{kor_gallery_html}{photo_cards_html}{info_table_html}{extra_info_html}{pet_html}{map_html}{closing_html}{footer_html}"
        "</div>"
    )

    return {
        "content_id": content_id,
        "blog_category": blog_category,
        "spot_title": title,
        "title": post_title,
        "html": full_html,
        "labels": labels,
        "ai_model": editorial.get("ai_model", "unknown"),
        "photo_gallery_count": len(photo_cards)
        + (1 if hero_credit.startswith("출처 · 한국관광공사 관광사진갤러리") else 0),
    }
