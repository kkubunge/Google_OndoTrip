"""발행 및 임시저장 완료된 콘텐츠 이력 관리 (중복 방지 및 여정 10:1 비율 제어)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import config


def load_history(history_file: Path | None = None) -> dict[str, dict[str, Any]]:
    """저장된 포스팅 이력 JSON을 불러온다."""
    target = history_file or config.HISTORY_FILE
    if not target.exists():
        return {}
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def is_posted(content_id: str, history_file: Path | None = None) -> bool:
    """해당 contentid가 이미 처리되었는지 확인한다."""
    history = load_history(history_file)
    return str(content_id) in history


def record_post(
    content_id: str,
    title: str,
    post_id: str,
    post_url: str,
    is_draft: bool,
    category: str | None = None,
    history_file: Path | None = None,
) -> None:
    """블로그 업로드 결과를 이력 파일에 저장한다."""
    target = history_file or config.HISTORY_FILE
    history = load_history(target)
    history[str(content_id)] = {
        "content_id": str(content_id),
        "category": category or "그날의 장소",
        "title": title,
        "post_id": post_id,
        "post_url": post_url,
        "is_draft": is_draft,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    target.write_text(
        json.dumps(history, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_category_stats(history_file: Path | None = None) -> dict[str, Any]:
    """카테고리별 누적 건수와 마지막 여정 이후 장소/미식 누적 건수를 계산한다."""
    history = load_history(history_file)
    entries = sorted(
        history.values(),
        key=lambda item: str(item.get("created_at", "")),
    )

    counts: dict[str, int] = {cat: 0 for cat in config.BLOG_CATEGORIES}
    since_last_journey = 0

    for item in entries:
        cat = str(item.get("category") or "그날의 장소")
        if cat not in counts:
            cat = "그날의 장소"
        counts[cat] += 1
        if cat == "그날의 여정":
            since_last_journey = 0
        else:
            since_last_journey += 1

    interval = config.JOURNEY_EVERY_N_POSTS
    return {
        "total": len(entries),
        "counts": counts,
        "since_last_journey": since_last_journey,
        "journey_interval": interval,
        "journey_due": since_last_journey >= interval,
        "remaining_for_journey": max(0, interval - since_last_journey),
    }


def choose_next_auto_category(
    counts: dict[str, int],
    since_last_journey: int,
    interval: int | None = None,
) -> str:
    """여정 10:1 규칙과 장소/미식/쉼터 균형을 기준으로 다음 업로드 카테고리를 결정한다."""
    limit = interval or config.JOURNEY_EVERY_N_POSTS
    if since_last_journey >= limit:
        return "그날의 여정"
    regular_categories = ("그날의 장소", "그날의 미식", "그날의 쉼터")
    return min(regular_categories, key=lambda cat: counts.get(cat, 0))
