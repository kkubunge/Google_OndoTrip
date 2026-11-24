"""Gemini 연동 및 한국관광공사 데이터 기반 블로그 HTML 포스트 생성기."""

from __future__ import annotations

import html
import json
import logging
import re
from typing import Any
from urllib.parse import quote

import config
from tour_api import is_valid_image_url

logger = logging.getLogger(__name__)


def _check_image_url(
    url: str,
    session: Any | None = None,
    cache: dict[str, bool] | None = None,
) -> bool:
    """이미지 URL 유효성을 캐시를 활용해 중복 요청 없이 검사한다."""
    if not url:
        return False
    if cache is not None and url in cache:
        return cache[url]
    ok = is_valid_image_url(url, session=session)
    if cache is not None:
        cache[url] = ok
    return ok


def _clean_image_caption(raw_name: str, fallback_title: str) -> str:
    """이미지 파일명 확장자(.jpg 등), 언더스코어, 끝 번호 괄호를 제거해 깔끔한 캡션으로 다듬는다."""
    text = _clean_text(raw_name)
    text = re.sub(r"\.(?:jpe?g|png|gif|bmp|webp)$", "", text, flags=re.IGNORECASE)
    text = text.replace("_", " ")
    text = re.sub(r"\s*\(\d+\)\s*$", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text or text == "관광지 사진":
        return fallback_title
    return text

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


def _summarize_course_text(raw_text: Any, max_chars: int = 210) -> str:
    """긴 경유지 안내문을 5줄 이내(최대 3문장·max_chars자 이내)로 간결하게 축약한다."""
    cleaned = _clean_text(raw_text)
    if not cleaned:
        return ""
    flat = re.sub(r"\s+", " ", cleaned).strip()
    if len(flat) <= max_chars:
        return flat

    sentences = [
        s.strip()
        for s in re.split(r"(?<=[.!?다요])\s+", flat)
        if s.strip()
    ]
    picked: list[str] = []
    total_len = 0
    for sent in sentences[:3]:
        next_len = total_len + (1 if picked else 0) + len(sent)
        if next_len > max_chars:
            break
        picked.append(sent)
        total_len = next_len

    if picked:
        return " ".join(picked)

    cut = flat[: max_chars - 1].rsplit(" ", 1)[0].strip()
    if len(cut) < max_chars // 2:
        cut = flat[: max_chars - 1].strip()
    return f"{cut}…"


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
    course_stops: list[tuple[str, str]] | None = None,
) -> str:
    """20대 여성 에디터 어투의 포토 에세이형 블로그 원고 생성용 Gemini 프롬프트를 만든다."""
    facts_lines = [f"- {label}: {val}" for label, val in info_rows[:12]]
    if pet_rows:
        facts_lines.append(
            "- 반려동물 동반: " + ", ".join(f"{k}={v}" for k, v in pet_rows[:4])
        )
    facts_text = "\n".join(facts_lines) if facts_lines else "- 추가 운영 정보 없음"

    category_focus = {
        "그날의 장소": "공간의 첫인상과 산책하며 마주치는 매력, 그리고 방문 전 챙길 실용 정보를 자연스럽게 이어 주세요.",
        "그날의 미식": "가게 분위기, 대표 메뉴의 매력, 그리고 영업시간·위치·주차 팁을 수다 떨듯 편하게 풀어 주세요.",
        "그날의 여정": "코스 흐름과 길 위에서 만나는 풍경의 매력, 이동 소요시간·동선 팁을 흐름 있게 담아 주세요.",
    }.get(blog_category, "공간의 매력과 방문 시 알아두면 좋은 점을 자연스럽게 이어 주세요.")

    kw_hint = ""
    if photo_keywords:
        kw_hint = f"[사진 분위기 참고 키워드] {', '.join(photo_keywords[:8])}\n"

    course_block = ""
    course_schema_field = ""
    if blog_category == "그날의 여정" and course_stops:
        stop_lines = [
            f"{idx}. {stop_name}: {stop_desc[:400] or '(상세 설명 없음)'}"
            for idx, (stop_name, stop_desc) in enumerate(course_stops, start=1)
        ]
        course_block = "[코스 경유지 정보]\n" + "\n".join(stop_lines) + "\n\n"
        course_schema_field = (
            ',\n  "course_summaries": ['
            f'"[코스 경유지 정보] 순서대로 총 {len(course_stops)}개 경유지를 각각 2~3문장(180자 이내, 5줄 이내, 자연스러운 해요체)으로 핵심만 축약한 소개글 배열"'
            "]"
        )

    return (
        "당신은 감성적이고 담백한 국내 여행 블로그 '그날의 온도(OndoTrip)'를 운영하는 20대 여성 에디터입니다.\n"
        f"이번 글은 [{blog_category}] 카테고리에 올라갑니다. {category_focus}\n\n"
        "[어투 및 구성 원칙]\n"
        "1. 친한 친구나 구독자에게 차분하고 다정하게 추천하듯 자연스러운 해요체(~해요, ~더라고요, ~좋아요, ~추천드려요)로 쓰세요.\n"
        "2. '좋았던 이유'와 '방문 팁'을 딱딱한 번호 목록으로 따로 쪼개지 말고, 3개의 이야기 문단(sections) 안에 매력과 운영 팁이 함께 녹아 자연스럽게 이어지게 작성하세요.\n"
        "3. 과한 이모지, 오글거리는 유행어(대박, 찐맛집, 레전드, 감성 폭발 등), 어색한 AI 번역투, 제목 앞 딱딱한 대괄호([카테고리]) 남발은 피하세요.\n"
        "4. 오직 아래 한국관광공사 공공데이터(사실 정보)만 바탕으로 작성하세요. 데이터에 없는 요금, 시간, 메뉴, 개인적인 방문 경험담('어제 직접 다녀왔는데' 등)을 절대 지어내지 마세요.\n\n"
        f"[장소/코스명] {title}\n"
        f"[블로그 카테고리] {blog_category}\n"
        f"[지역/유형] {region_name} / {category_name}\n"
        f"[주소] {addr}\n"
        f"{kw_hint}"
        f"[개요] {overview[:1500]}\n"
        f"[상세정보]\n{facts_text}\n\n"
        f"{course_block}"
        "반드시 아래 JSON 형식으로만 응답하세요:\n"
        "{\n"
        '  "post_title": "검색에 잘 노출되면서도 자연스러운 20대 여성 블로그 스타일 제목 (35자 내외)",\n'
        '  "subtitle": "제목 아래에 놓일 담백한 한 줄 요약 (20~40자)",\n'
        '  "lead_paragraph": "부드럽게 이야기를 여는 도입 문단 (2~3문장, 자연스러운 해요체)",\n'
        '  "sections": [\n'
        "    {\n"
        '      "heading": "첫 번째 이야기 소제목 (공간/코스의 첫인상과 분위기, 12~26자)",\n'
        '      "body": "공간이 좋았던 이유와 분위기를 20대 여성 에디터 말투로 풀어쓴 문단 (3~4문장, 해요체)"\n'
        "    },\n"
        "    {\n"
        '      "heading": "두 번째 이야기 소제목 (매력 포인트와 함께 즐기는 법)",\n'
        '      "body": "구체적인 매력 포인트, 메뉴나 볼거리, 소소한 즐김 팁을 자연스럽게 섞어 쓴 문단 (3~4문장, 해요체)"\n'
        "    },\n"
        "    {\n"
        '      "heading": "세 번째 이야기 소제목 (다녀오기 전 가볍게 챙길 이야기)",\n'
        '      "body": "영업시간·위치·주차·휴무일·동선 등 실제 운영정보 기반 방문 팁을 딱딱하지 않게 녹여 쓴 문단 (3~4문장, 해요체)"\n'
        "    }\n"
        "  ],\n"
        '  "closing_note": "잔잔한 여운을 남기며 일정을 권하는 마무리 1~2문장 (해요체)"'
        f"{course_schema_field}\n"
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
    """Gemini 호출이 실패했을 때 이유와 팁이 통합된 자연스러운 해요체 섹션을 구성한다."""
    story_parts = _split_story_paragraphs(overview)
    sentences = [
        s.strip()
        for s in re.split(r"(?<=[.!?다요])\s+", overview.replace("\n", " "))
        if len(s.strip()) > 10
    ]
    lead = (
        f"{region_name} 나들이를 계획 중이라면 '{title}'에 한 번 들러보시는 건 어떨까요? "
        + (
            " ".join(sentences[:2])
            if sentences
            else f"{category_name} 특유의 분위기를 여유롭게 느끼기 좋아요."
        )
    )

    body_1 = (
        story_parts[0]
        if story_parts
        else f"{region_name}에서 가볍게 들러 분위기를 즐기기 좋은 {category_name}이에요."
    )
    info_dict = dict(info_rows)
    highlight_extra = ""
    if "대표 메뉴" in info_dict:
        highlight_extra = f" 대표 메뉴인 {info_dict['대표 메뉴'].splitlines()[0]}도 함께 살펴보면 더 좋아요."
    elif "코스 테마" in info_dict:
        highlight_extra = f" {info_dict['코스 테마'].splitlines()[0]} 테마로 천천히 둘러보기 좋아요."
    body_2 = (
        (story_parts[1] if len(story_parts) > 1 else f"{title}만의 차분한 매력과 볼거리를 천천히 즐겨보기 좋아요.")
        + highlight_extra
    ).strip()

    tip_sentences: list[str] = []
    if addr:
        tip_sentences.append(f"위치는 {addr} 쪽이라 주변 일정과 함께 묶어 다녀오기 편해요.")
    for key in (
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
            tip_sentences.append(f"{key}은(는) {info_dict[key].splitlines()[0]} 기준이니 출발 전에 확인해 두시면 좋아요.")
    if pet_rows:
        tip_sentences.append(f"반려동물 동반 정보({pet_rows[0][1]})도 미리 살펴보시면 더 여유롭게 다녀오실 수 있어요.")
    if not tip_sentences:
        tip_sentences.append("방문 전 공식 안내 연락처나 홈페이지로 당일 운영 여부를 가볍게 확인해 보시는 걸 추천드려요.")

    return {
        "post_title": f"{region_name} {title}, 천천히 머물기 좋은 {category_name}",
        "subtitle": f"{region_name}에서 만난 {title}의 소소한 매력과 방문 이야기를 정리했어요",
        "lead_paragraph": lead,
        "sections": [
            {
                "heading": f"차분하게 마주한 {title}의 첫인상",
                "body": body_1,
            },
            {
                "heading": "천천히 둘러볼수록 느껴지는 매력",
                "body": body_2,
            },
            {
                "heading": "다녀오기 전 가볍게 챙길 이야기",
                "body": " ".join(tip_sentences[:3]),
            },
        ],
        "closing_note": "일정에 작은 쉼표가 필요한 날, 오늘 소개해 드린 공간에서 기분 좋은 시간 보내시길 바라요.",
        "ai_model": "rule-based-fallback",
    }


def _normalize_editorial_sections(
    editorial: dict[str, Any], overview: str, title: str
) -> list[dict[str, str]]:
    """Gemini 또는 폴백 응답에서 통합 포토 에세이 섹션 목록을 정규화한다."""
    normalized: list[dict[str, str]] = []
    raw_sections = editorial.get("sections")
    if isinstance(raw_sections, list):
        for idx, item in enumerate(raw_sections, start=1):
            if not isinstance(item, dict):
                continue
            heading = str(
                item.get("heading") or item.get("title") or f"{title} 이야기 {idx}"
            ).strip()
            body = str(
                item.get("body") or item.get("content") or item.get("text") or ""
            ).strip()
            if body:
                normalized.append({"heading": heading, "body": body})

    if normalized:
        return normalized

    # 구버전 필드나 비어 있는 응답 방어용 폴백
    paragraphs = _split_story_paragraphs(overview)
    fallback_headings = [
        f"차분하게 둘러본 {title}",
        "함께 기억해 둘 매력 포인트",
        "방문 전 소소한 참고 사항",
    ]
    for idx, para in enumerate(paragraphs[:3]):
        normalized.append(
            {
                "heading": fallback_headings[idx] if idx < len(fallback_headings) else title,
                "body": para,
            }
        )
    return normalized


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
    image_session: Any | None = None,
    image_cache: dict[str, bool] | None = None,
) -> tuple[
    str,
    str,
    list[dict[str, str]],
    list[dict[str, Any]],
    list[str],
]:
    """실제 HTTP 유효성을 통과한 대표 이미지, 추가 사진 목록, 대표 승격 시 촬영자 정보, 저작권 코드를 수집한다."""
    raw_hero = _to_https(str(common.get("firstimage") or ""))
    hero_url = ""
    seen_urls: set[str] = set()
    if raw_hero:
        seen_urls.add(raw_hero)
        if _check_image_url(raw_hero, image_session, image_cache):
            hero_url = raw_hero
        else:
            logger.info("깨진 대표 이미지 URL 건너뜀: %s", raw_hero)

    hero_photographer = ""
    copyright_codes: list[str] = []
    if common.get("cpyrhtDivCd"):
        copyright_codes.append(str(common["cpyrhtDivCd"]).strip())

    kor_gallery: list[dict[str, str]] = []
    for img in images:
        orig_url = _to_https(str(img.get("originimgurl") or ""))
        if not orig_url or orig_url in seen_urls:
            continue
        seen_urls.add(orig_url)
        if not _check_image_url(orig_url, image_session, image_cache):
            logger.info("깨진 추가 이미지 URL 건너뜀: %s", orig_url)
            continue
        if img.get("cpyrhtDivCd"):
            copyright_codes.append(str(img["cpyrhtDivCd"]).strip())
        if not hero_url:
            hero_url = orig_url
            continue
        kor_gallery.append(
            {
                "url": orig_url,
                "name": _clean_text(img.get("imgname")) or "관광지 사진",
            }
        )
        if len(kor_gallery) >= 6:
            break

    photo_cards: list[dict[str, Any]] = []
    for item in photo_gallery or []:
        p_url = _to_https(str(item.get("url") or ""))
        if not p_url or p_url in seen_urls:
            continue
        seen_urls.add(p_url)
        if not _check_image_url(p_url, image_session, image_cache):
            logger.info("깨진 관광사진 URL 건너뜀: %s", p_url)
            continue
        photographer = _clean_text(item.get("photographer")) or "한국관광공사"
        p_title = _clean_text(item.get("title")) or "국내 여행 풍경"
        p_date = _clean_text(item.get("photo_date"))
        if not hero_url:
            hero_url = p_url
            hero_photographer = photographer
            continue
        photo_cards.append(
            {
                "url": p_url,
                "title": p_title,
                "photo_date": p_date,
                "location": _clean_text(item.get("location")),
                "photographer": photographer,
                "matched_spot": _clean_text(item.get("matched_spot")),
            }
        )
        if len(photo_cards) >= config.PHOTO_GALLERY_MAX_IMAGES:
            break

    return hero_url, hero_photographer, kor_gallery, photo_cards, copyright_codes


def _build_inline_photos(
    kor_gallery: list[dict[str, str]],
    photo_cards: list[dict[str, Any]],
    spot_title: str,
    max_photos: int = 6,
) -> list[dict[str, Any]]:
    """보강 사진과 기본 추가 사진을 구분 없이 고르게 섞어 본문 대형 사진 리스트를 만든다."""
    normalized_photo: list[dict[str, Any]] = []
    for p_card in photo_cards:
        caption = (
            f"{p_card['title']} ({p_card['photo_date']})"
            if p_card["photo_date"]
            else p_card["title"]
        )
        normalized_photo.append(
            {
                "url": p_card["url"],
                "alt": p_card["title"] or spot_title,
                "caption": caption,
                "photographer": p_card["photographer"],
            }
        )

    normalized_kor: list[dict[str, Any]] = []
    for g in kor_gallery:
        label = _clean_image_caption(g.get("name") or "", spot_title)
        normalized_kor.append(
            {
                "url": g["url"],
                "alt": label,
                "caption": label,
                "photographer": "",
            }
        )

    combined: list[dict[str, Any]] = []
    max_len = max(len(normalized_photo), len(normalized_kor))
    for i in range(max_len):
        if i < len(normalized_photo):
            combined.append(normalized_photo[i])
        if len(combined) >= max_photos:
            break
        if i < len(normalized_kor):
            combined.append(normalized_kor[i])
        if len(combined) >= max_photos:
            break

    return combined[:max_photos]


def _render_large_photo_figure(photo: dict[str, Any]) -> str:
    """원본 비율 무크롭으로 본문 폭에 맞춰 큼직하게 보여주는 대형 사진 HTML을 만든다."""
    return (
        '<figure style="margin:26px 0 32px;text-align:center;">'
        f'<img src="{html.escape(photo["url"])}" alt="{html.escape(photo["alt"])}" '
        'style="display:block;margin:0 auto;max-height:640px;width:auto;max-width:100%;height:auto;border-radius:14px;box-shadow:0 8px 26px rgba(38,38,38,0.06);" />'
        f'<figcaption style="margin-top:10px;font-size:12px;line-height:1.55;color:#8c8378;">{html.escape(photo["caption"])}</figcaption>'
        "</figure>"
    )


def _resolve_copyright_notice(
    copyright_codes: list[str],
    photo_photographers: list[str] | None = None,
) -> str:
    """공공누리 유형 및 촬영자 정보를 하나의 자연스러운 통합 출처 문구로 생성한다."""
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

    unique_photographers = [
        p for p in dict.fromkeys(photo_photographers or []) if p
    ]
    if unique_photographers:
        source_text = f"한국관광공사 (사진 촬영: {html.escape(', '.join(unique_photographers))})"
    else:
        source_text = "한국관광공사"

    return (
        f"<strong>출처</strong>: {source_text} "
        f"| <strong>저작권</strong>: {html.escape(kogl_text)}<br />"
        f'<span style="color:#8c8378;font-size:12px;">{html.escape(rule_note)}</span>'
    )


def _parse_valid_korea_coords(
    mapx: Any, mapy: Any
) -> tuple[float, float] | None:
    """대한민국 유효 범위 내 위도·경도(lat, lon)만 파싱하고 (0, 0) 등 무효 좌표는 None을 반환한다."""
    try:
        lon = float(str(mapx).strip())
        lat = float(str(mapy).strip())
    except (TypeError, ValueError):
        return None

    if not (33.0 <= lat <= 39.0 and 124.0 <= lon <= 132.5):
        return None
    return lat, lon


def _build_map_urls(
    title: str,
    addr1: str,
    mapx: Any,
    mapy: Any,
    span_lon: float = 0.007,
    span_lat: float = 0.005,
) -> dict[str, Any]:
    """OpenStreetMap 임베드 URL과 네이버·카카오·구글 지도 URL을 계산한다."""
    query_text = f"{title} {addr1}".strip() or title
    naver_url = f"https://map.naver.com/p/search/{quote(query_text)}" if query_text else ""
    kakao_search_url = f"https://map.kakao.com/?q={quote(query_text)}" if query_text else ""

    coords = _parse_valid_korea_coords(mapx, mapy)
    if coords is None:
        return {"has_coords": False, "naver_url": naver_url, "kakao_url": kakao_search_url}
    lat, lon = coords

    bbox = (
        f"{lon - span_lon:.6f},{lat - span_lat:.6f},"
        f"{lon + span_lon:.6f},{lat + span_lat:.6f}"
    )
    osm_embed_url = (
        f"https://www.openstreetmap.org/export/embed.html?bbox={quote(bbox, safe=',')}"
        f"&layer=mapnik&marker={lat:.6f},{lon:.6f}"
    )
    kakao_url = f"https://map.kakao.com/link/map/{quote(title or '위치')},{lat:.6f},{lon:.6f}"
    google_url = f"https://www.google.com/maps/search/?api=1&query={lat:.6f},{lon:.6f}"
    return {
        "has_coords": True,
        "lat": lat,
        "lon": lon,
        "osm_embed_url": osm_embed_url,
        "naver_url": naver_url,
        "kakao_url": kakao_url,
        "google_url": google_url,
    }


def _render_mini_map_html(title: str, addr1: str, mapx: Any, mapy: Any) -> str:
    """코스 경유지 카드 안에 들어가는 컴팩트 OpenStreetMap 미니맵과 지도 링크를 만든다."""
    info = _build_map_urls(title, addr1, mapx, mapy, span_lon=0.005, span_lat=0.0035)
    if not info["naver_url"] and not info["has_coords"]:
        return ""

    mini_btn = (
        "display:inline-block;padding:6px 11px;border-radius:7px;text-decoration:none;"
        "font-size:12px;font-weight:600;margin:4px 6px 0 0;"
    )
    if not info["has_coords"]:
        return (
            '<div style="margin-top:12px;">'
            f'<a href="{info["naver_url"]}" target="_blank" rel="noopener noreferrer" style="{mini_btn}background:#3d5a4c;color:#ffffff;">네이버 지도</a>'
            f'<a href="{info["kakao_url"]}" target="_blank" rel="noopener noreferrer" style="{mini_btn}background:#f3ede2;color:#262626;border:1px solid #e2d9cb;">카카오맵</a>'
            "</div>"
        )

    return (
        '<div style="margin-top:14px;">'
        '<div style="border-radius:10px;overflow:hidden;border:1px solid #e6dfd5;background:#ffffff;">'
        f'<iframe title="{html.escape(title)} 미니맵" src="{info["osm_embed_url"]}" '
        'style="width:100%;height:180px;border:0;display:block;" loading="lazy"></iframe>'
        "</div>"
        '<div style="margin-top:8px;">'
        f'<a href="{info["naver_url"]}" target="_blank" rel="noopener noreferrer" style="{mini_btn}background:#3d5a4c;color:#ffffff;">네이버 지도</a>'
        f'<a href="{info["kakao_url"]}" target="_blank" rel="noopener noreferrer" style="{mini_btn}background:#f3ede2;color:#262626;border:1px solid #e2d9cb;">카카오맵</a>'
        f'<a href="{info["google_url"]}" target="_blank" rel="noopener noreferrer" style="{mini_btn}background:#ffffff;color:#4a453f;border:1px solid #dcd5ca;">구글 지도</a>'
        "</div>"
        "</div>"
    )


def _render_extra_info_html(
    content_type_id: str,
    info_list: list[dict[str, Any]],
    image_session: Any | None = None,
    image_cache: dict[str, bool] | None = None,
    course_summaries: list[str] | None = None,
) -> str:
    """반복정보(detailInfo2)를 미니멀 에디토리얼 톤 카드로 렌더링한다."""
    if not info_list:
        return ""

    blocks: list[str] = []
    if content_type_id == "25":
        for idx, item in enumerate(info_list, start=1):
            subname = _clean_text(item.get("subname"))
            raw_overview = item.get("subdetailoverview")
            ai_summary = (
                course_summaries[idx - 1].strip()
                if course_summaries and idx - 1 < len(course_summaries)
                else ""
            )
            summary_text = (
                _summarize_course_text(ai_summary, max_chars=220)
                if ai_summary
                else _summarize_course_text(raw_overview, max_chars=210)
            )
            sub_addr1 = _clean_text(item.get("sub_addr1"))
            subimg = _to_https(str(item.get("subdetailimg") or ""))
            if subimg and not _check_image_url(subimg, image_session, image_cache):
                logger.info("깨진 코스 경유지 이미지 URL 건너뜀: %s (%s)", subimg, subname)
                subimg = ""
            if not (subname or summary_text):
                continue

            addr_line = (
                f'<div style="font-size:12.5px;color:#736c63;margin:0 0 10px;">{html.escape(sub_addr1)}</div>'
                if sub_addr1
                else ""
            )
            summary_html = (
                f'<div style="font-size:14px;line-height:1.75;color:#4a453f;">{html.escape(summary_text)}</div>'
                if summary_text
                else ""
            )
            img_html = (
                f'<img src="{html.escape(subimg)}" alt="{html.escape(subname or "코스 사진")}" '
                'style="display:block;margin:14px auto 0;max-height:520px;width:auto;max-width:100%;height:auto;border-radius:10px;" />'
                if subimg
                else ""
            )
            mini_map_html = _render_mini_map_html(
                subname,
                sub_addr1,
                item.get("sub_mapx"),
                item.get("sub_mapy"),
            )
            blocks.append(
                '<div style="padding:18px 20px;background:#faf8f5;border:1px solid #eae4db;'
                'border-radius:12px;margin-bottom:16px;">'
                f'<div style="font-size:12px;font-weight:700;letter-spacing:0.04em;color:#3d5a4c;margin-bottom:4px;">COURSE {idx:02d}</div>'
                f'<div style="font-size:16px;font-weight:700;color:#262626;margin-bottom:4px;">{html.escape(subname)}</div>'
                f"{addr_line}{summary_html}{img_html}{mini_map_html}</div>"
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
    info = _build_map_urls(title, addr1, mapx, mapy)
    if not info["has_coords"]:
        return ""

    btn_style = (
        "display:inline-block;padding:9px 15px;border-radius:8px;text-decoration:none;"
        "font-size:13.5px;font-weight:600;margin:4px 8px 4px 0;"
    )
    return (
        '<section style="margin:34px 0;">'
        '<h2 style="font-size:18px;font-weight:700;color:#262626;margin:0 0 16px;padding-bottom:10px;border-bottom:1px solid #eae4db;letter-spacing:-0.01em;">위치 및 길찾기</h2>'
        '<div style="border-radius:14px;overflow:hidden;border:1px solid #eae4db;background:#faf8f5;">'
        f'<iframe title="{html.escape(title)} 위치 지도" src="{info["osm_embed_url"]}" '
        'style="width:100%;height:320px;border:0;display:block;" loading="lazy"></iframe>'
        "</div>"
        '<div style="margin-top:14px;">'
        f'<a href="{info["naver_url"]}" target="_blank" rel="noopener noreferrer" style="{btn_style}background:#3d5a4c;color:#ffffff;">네이버 지도로 보기</a>'
        f'<a href="{info["kakao_url"]}" target="_blank" rel="noopener noreferrer" style="{btn_style}background:#f3ede2;color:#262626;border:1px solid #e2d9cb;">카카오맵으로 보기</a>'
        f'<a href="{info["google_url"]}" target="_blank" rel="noopener noreferrer" style="{btn_style}background:#ffffff;color:#4a453f;border:1px solid #dcd5ca;">구글 지도로 보기</a>'
        "</div>"
        f'<p style="margin:10px 0 0;font-size:12px;color:#8c8378;">위치 좌표 · 위도 {info["lat"]:.6f}, 경도 {info["lon"]:.6f}</p>'
        "</section>"
    )


def _render_course_overview_map_html(
    title: str,
    info_list: list[dict[str, Any]],
    content_id: str,
) -> str:
    """여행코스(여정)의 모든 유효 경유지 좌표를 번호 마커와 동선으로 한눈에 보여주는 통합 지도를 만든다."""
    stops: list[dict[str, Any]] = []
    for idx, item in enumerate(info_list, start=1):
        coords = _parse_valid_korea_coords(item.get("sub_mapx"), item.get("sub_mapy"))
        if coords is None:
            continue
        lat, lon = coords
        subname = _clean_text(item.get("subname")) or f"코스 {idx}"
        sub_addr1 = _clean_text(item.get("sub_addr1"))
        urls = _build_map_urls(subname, sub_addr1, lon, lat)
        stops.append(
            {
                "num": idx,
                "name": subname,
                "addr": sub_addr1,
                "lat": lat,
                "lon": lon,
                "naver_url": urls["naver_url"],
            }
        )

    if not stops:
        return ""
    if len(stops) == 1:
        only = stops[0]
        return _render_map_html(only["name"], only["addr"], only["lon"], only["lat"])

    lats = [s["lat"] for s in stops]
    lons = [s["lon"] for s in stops]
    pad_lat = max((max(lats) - min(lats)) * 0.18, 0.008)
    pad_lon = max((max(lons) - min(lons)) * 0.18, 0.012)
    bbox = (
        f"{min(lons) - pad_lon:.6f},{min(lats) - pad_lat:.6f},"
        f"{max(lons) + pad_lon:.6f},{max(lats) + pad_lat:.6f}"
    )
    fallback_osm_url = (
        f"https://www.openstreetmap.org/export/embed.html?bbox={quote(bbox, safe=',')}"
        "&layer=mapnik"
    )

    dir_points = "/".join(f"{s['lat']:.6f},{s['lon']:.6f}" for s in stops[:10])
    google_dir_url = f"https://www.google.com/maps/dir/{dir_points}"

    safe_cid = re.sub(r"[^a-zA-Z0-9_-]", "", str(content_id or "course")) or "course"
    map_dom_id = f"ondo-course-map-{safe_cid}"
    stops_json = json.dumps(stops, ensure_ascii=False).replace("</", "<\\/")

    chip_parts: list[str] = []
    for s in stops:
        chip_label = f"{s['num']:02d} {s['name']}"
        if s["naver_url"]:
            chip_parts.append(
                f'<a href="{s["naver_url"]}" target="_blank" rel="noopener noreferrer" '
                'style="display:inline-block;padding:5px 10px;border-radius:999px;background:#faf8f5;'
                'border:1px solid #e6dfd5;color:#262626;font-size:12px;font-weight:600;text-decoration:none;margin:3px 4px 3px 0;">'
                f"{html.escape(chip_label)}</a>"
            )
        else:
            chip_parts.append(
                '<span style="display:inline-block;padding:5px 10px;border-radius:999px;background:#faf8f5;'
                'border:1px solid #e6dfd5;color:#262626;font-size:12px;font-weight:600;margin:3px 4px 3px 0;">'
                f"{html.escape(chip_label)}</span>"
            )
    chips_html = '<span style="color:#8c8378;font-size:12px;margin:0 4px 0 0;">→</span>'.join(
        chip_parts
    )

    script_html = (
        "<script>"
        "(function(){"
        f"var el=document.getElementById({json.dumps(map_dom_id)});"
        "if(!el)return;"
        f"var stops={stops_json};"
        "function init(){"
        "if(!window.L||!stops.length)return;"
        'el.innerHTML="";'
        "var map=L.map(el,{scrollWheelZoom:false});"
        'var baseLayer=L.tileLayer("https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png",{subdomains:"abcd",maxZoom:19,attribution:"&copy; OpenStreetMap &copy; CARTO"}).addTo(map);'
        "var tileErr=0,switched=false;"
        'baseLayer.on("tileerror",function(){tileErr++;if(!switched&&tileErr>=2){switched=true;map.removeLayer(baseLayer);L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}",{maxZoom:18,attribution:"Tiles &copy; Esri"}).addTo(map);}});'
        "var pts=[];"
        "stops.forEach(function(s){"
        "var ll=[s.lat,s.lon];pts.push(ll);"
        'var icon=L.divIcon({className:"",iconSize:[26,26],iconAnchor:[13,13],'
        'html:\'<div style="width:26px;height:26px;border-radius:999px;background:#3d5a4c;color:#ffffff;font-size:12px;font-weight:700;line-height:26px;text-align:center;border:2px solid #ffffff;box-shadow:0 2px 6px rgba(0,0,0,0.28);">\'+s.num+"</div>"});'
        'var pop=document.createElement("div");pop.style.fontSize="13px";pop.style.lineHeight="1.5";'
        'var t=document.createElement("strong");t.textContent="COURSE "+String(s.num).padStart(2,"0")+" · "+s.name;pop.appendChild(t);'
        'if(s.addr){var a=document.createElement("div");a.style.color="#736c63";a.style.fontSize="12px";a.style.marginTop="2px";a.textContent=s.addr;pop.appendChild(a);}'
        'if(s.naver_url){var lk=document.createElement("a");lk.href=s.naver_url;lk.target="_blank";lk.rel="noopener noreferrer";lk.style.display="inline-block";lk.style.marginTop="6px";lk.style.color="#3d5a4c";lk.style.fontWeight="600";lk.textContent="네이버 지도에서 보기";pop.appendChild(lk);}'
        "L.marker(ll,{icon:icon}).addTo(map).bindPopup(pop);"
        "});"
        'if(pts.length>=2){L.polyline(pts,{color:"#3d5a4c",weight:3.5,opacity:0.85,dashArray:"6, 6"}).addTo(map);}'
        "map.fitBounds(L.latLngBounds(pts),{padding:[36,36]});"
        "}"
        'var cssUrl="https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.min.css";'
        'if(!document.querySelector(\'link[href="\'+cssUrl+\'"]\')){var lnk=document.createElement("link");lnk.rel="stylesheet";lnk.href=cssUrl;document.head.appendChild(lnk);}'
        "if(window.L){init();return;}"
        'var sc=document.createElement("script");sc.src="https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.min.js";sc.onload=init;document.head.appendChild(sc);'
        "})();"
        "</script>"
    )

    btn_style = (
        "display:inline-block;padding:9px 15px;border-radius:8px;text-decoration:none;"
        "font-size:13.5px;font-weight:600;margin:4px 8px 4px 0;"
    )
    return (
        '<section style="margin:34px 0;">'
        '<h2 style="font-size:18px;font-weight:700;color:#262626;margin:0 0 6px;letter-spacing:-0.01em;">전체 코스 한눈에 보기</h2>'
        f'<p style="margin:0 0 14px;font-size:13px;color:#736c63;padding-bottom:10px;border-bottom:1px solid #eae4db;">{html.escape(title)}에 포함된 {len(stops)}개 경유지 위치를 번호 순서대로 모았어요. 핀을 누르면 상세 위치를 바로 확인할 수 있어요.</p>'
        f'<div id="{html.escape(map_dom_id)}" style="width:100%;height:380px;border-radius:14px;overflow:hidden;border:1px solid #eae4db;background:#faf8f5;">'
        f'<iframe title="{html.escape(title)} 전체 코스 지도" src="{fallback_osm_url}" '
        'style="width:100%;height:380px;border:0;display:block;" loading="lazy"></iframe>'
        "</div>"
        '<div style="margin-top:14px;">'
        f'<a href="{google_dir_url}" target="_blank" rel="noopener noreferrer" style="{btn_style}background:#3d5a4c;color:#ffffff;">구글 지도로 전체 경로 보기</a>'
        "</div>"
        f'<div style="margin-top:10px;line-height:1.9;">{chips_html}</div>'
        f"{script_html}"
        "</section>"
    )


def generate_blog_post(
    bundle: dict[str, Any], category_override: str | None = None
) -> dict[str, Any]:
    """수집된 관광정보와 보강 사진을 바탕으로 포토 에세이형 미니멀 블로그 포스트를 생성한다."""
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
    image_cache: dict[str, bool] = {}
    with config.create_http_session() as image_session:
        hero_url, hero_photographer, kor_gallery, photo_cards, copyright_codes = (
            _collect_gallery_urls(
                common,
                images,
                photo_gallery,
                image_session=image_session,
                image_cache=image_cache,
            )
        )
    inline_photos = _build_inline_photos(
        kor_gallery, photo_cards, spot_title=title, max_photos=6
    )

    photo_kw_hints: list[str] = []
    for p_item in photo_gallery:
        for kw in p_item.get("keywords") or []:
            if kw and kw not in photo_kw_hints:
                photo_kw_hints.append(kw)

    course_stops: list[tuple[str, str]] = []
    if ctype == "25" and info_list:
        for sub in info_list:
            sub_name = _clean_text(sub.get("subname"))
            sub_desc = _clean_text(sub.get("subdetailoverview"))
            if sub_name:
                course_stops.append((sub_name, sub_desc[:400]))

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
        course_stops=course_stops or None,
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
    sections = _normalize_editorial_sections(editorial, overview, title)
    closing_note = str(editorial.get("closing_note") or "").strip()
    raw_course_summaries = editorial.get("course_summaries")
    course_summaries = (
        [str(s).strip() for s in raw_course_summaries]
        if isinstance(raw_course_summaries, list)
        else None
    )

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

    # 2. 대표 대형 이미지 (원본 비율 무크롭)
    hero_html = ""
    if hero_url:
        hero_html = (
            '<figure style="margin:0 0 28px;text-align:center;">'
            f'<img src="{html.escape(hero_url)}" alt="{html.escape(title)} 대표 사진" '
            'style="display:block;margin:0 auto;max-height:640px;width:auto;max-width:100%;height:auto;border-radius:14px;box-shadow:0 8px 28px rgba(38,38,38,0.06);" />'
            f'<figcaption style="margin-top:10px;font-size:12px;color:#8c8378;">{html.escape(title)}</figcaption>'
            "</figure>"
        )

    # 3. 도입 에세이 + 매력·팁 통합 섹션 및 본문 중간 대형 사진 인터리빙
    lead_html = (
        '<div style="background:#faf8f5;border-left:3px solid #3d5a4c;padding:18px 20px;border-radius:0 12px 12px 0;margin:0 0 28px;">'
        f'<p style="margin:0;font-size:15.5px;line-height:1.9;color:#262626;">{html.escape(lead_paragraph)}</p>'
        "</div>"
        if lead_paragraph
        else ""
    )

    essay_blocks: list[str] = []
    for idx, sec in enumerate(sections):
        body_paragraphs = [
            p.strip() for p in sec["body"].splitlines() if p.strip()
        ] or [sec["body"]]
        body_html = "".join(
            f'<p style="margin:0 0 14px;font-size:15.5px;line-height:1.95;color:#333333;">{html.escape(p)}</p>'
            for p in body_paragraphs
        )
        section_html = (
            '<section style="margin:32px 0 8px;">'
            f'<h2 style="font-size:19px;font-weight:700;color:#262626;margin:0 0 14px;padding-bottom:10px;border-bottom:1px solid #eae4db;letter-spacing:-0.01em;">{html.escape(sec["heading"])}</h2>'
            f"{body_html}"
            "</section>"
        )
        essay_blocks.append(section_html)

        if idx < len(inline_photos):
            essay_blocks.append(_render_large_photo_figure(inline_photos[idx]))

    # 섹션 수보다 남은 추가 사진은 하단에 1장씩 시원한 대형 스트림으로 이어 배치
    remaining_photos = inline_photos[len(sections) :]
    for rem_photo in remaining_photos:
        essay_blocks.append(_render_large_photo_figure(rem_photo))

    essay_stream_html = "".join(essay_blocks)

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
    with config.create_http_session() as extra_image_session:
        extra_info_html = _render_extra_info_html(
            ctype,
            info_list,
            image_session=extra_image_session,
            image_cache=image_cache,
            course_summaries=course_summaries,
        )
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

    # 푸터 통합 출처 표기용 촬영자 수집
    photo_photographers: list[str] = [
        p["photographer"] for p in inline_photos if p.get("photographer")
    ]
    if hero_photographer:
        photo_photographers.insert(0, hero_photographer)

    # 6. 무료 지도 및 길찾기 (여정은 전체 경유지 통합 지도, 일반 장소/미식은 단일 지도)
    if ctype == "25":
        map_html = _render_course_overview_map_html(
            title=title,
            info_list=info_list,
            content_id=content_id,
        )
    else:
        map_html = _render_map_html(
            title=title,
            addr1=addr1,
            mapx=common.get("mapx"),
            mapy=common.get("mapy"),
        )

    # 7. 마무리 문장 + 공공누리/촬영자 통합 출처 푸터
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
        f"{header_html}{hero_html}{lead_html}{essay_stream_html}{info_table_html}{extra_info_html}{pet_html}{map_html}{closing_html}{footer_html}"
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
        "photo_gallery_count": len(photo_cards) + (1 if hero_photographer else 0),
    }
