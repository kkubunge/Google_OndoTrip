"""OndoTrip 프로젝트 전역 설정 및 관광공사 코드 매핑."""

from __future__ import annotations

import os
import ssl
import tempfile
from pathlib import Path

import certifi
import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

OUTPUT_DIR = BASE_DIR / "output"
HISTORY_FILE = BASE_DIR / "posted_history.json"
TOKEN_FILE = BASE_DIR / "token.json"

TOUR_API_KEY = os.getenv("TOUR_API_KEY", "").strip()
TOUR_API_ENDPOINT = os.getenv(
    "TOUR_API_ENDPOINT", "https://apis.data.go.kr/B551011/KorService2"
).rstrip("/")

# 한국관광공사 관광사진 정보 서비스 (PhotoGalleryService1) — 미지정 시 TOUR_API_KEY 재사용
PHOTO_API_KEY = os.getenv("PHOTO_API_KEY", "").strip() or TOUR_API_KEY
PHOTO_API_ENDPOINT = os.getenv(
    "PHOTO_API_ENDPOINT", "https://apis.data.go.kr/B551011/PhotoGalleryService1"
).rstrip("/")
PHOTO_GALLERY_MAX_IMAGES = 4

BLOGGER_BLOG_ID = os.getenv("BLOGGER_BLOG_ID", "").strip()
BLOGGER_URL = os.getenv("BLOGGER_URL", "").strip()
GOOGLE_CLIENT_SECRET_FILE = os.getenv("GOOGLE_CLIENT_SECRET_FILE", "").strip()
CLIENT_SECRET_PATH = (
    BASE_DIR / GOOGLE_CLIENT_SECRET_FILE if GOOGLE_CLIENT_SECRET_FILE else None
)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip()

# Slack 완료 보고 설정 (로컬 직접 실행 시 사용, GitHub Actions에서는 워크플로우 스텝이 보고)
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "").strip()
SLACK_REPORT_CHANNEL_ID = os.getenv("SLACK_REPORT_CHANNEL_ID", "").strip()

# 제외할 관광타입 (15: 일회성 행사/공연/축제 제외, 32: 숙박 제외)
EXCLUDED_CONTENT_TYPES: set[str] = {"15", "32"}

# 한국관광공사 국문 관광정보 관광타입(ContentTypeId) 매핑 (업로드 허용 타입만 포함)
CONTENT_TYPE_MAP: dict[str, str] = {
    "관광지": "12",
    "문화시설": "14",
    "여행코스": "25",
    "레포츠": "28",
    "쇼핑": "38",
    "음식점": "39",
    "맛집": "39",
}

CONTENT_TYPE_NAME_MAP: dict[str, str] = {
    "12": "관광지",
    "14": "문화시설",
    "25": "여행코스",
    "28": "레포츠",
    "32": "숙박",
    "38": "쇼핑",
    "39": "음식점",
}

# 블로그 공식 3대 활성 카테고리 (과거 '그날의 쉼터'는 이력 호환용으로만 보존)
BLOG_CATEGORIES: tuple[str, ...] = (
    "그날의 장소",
    "그날의 미식",
    "그날의 여정",
)
ARCHIVED_BLOG_CATEGORIES: tuple[str, ...] = ("그날의 쉼터",)

CATEGORY_ALIAS_MAP: dict[str, str] = {
    "장소": "그날의 장소",
    "그날의 장소": "그날의 장소",
    "그날의장소": "그날의 장소",
    "여행지": "그날의 장소",
    "미식": "그날의 미식",
    "그날의 미식": "그날의 미식",
    "그날의미식": "그날의 미식",
    "식탁": "그날의 미식",
    "그날의 식탁": "그날의 미식",
    "카페": "그날의 미식",
    "맛집": "그날의 미식",
    "음식점": "그날의 미식",
    "여정": "그날의 여정",
    "그날의 여정": "그날의 여정",
    "그날의여정": "그날의 여정",
    "코스": "그날의 여정",
    "여행코스": "그날의 여정",
}

CONTENT_TYPE_TO_CATEGORY: dict[str, str] = {
    "12": "그날의 장소",
    "14": "그날의 장소",
    "28": "그날의 장소",
    "38": "그날의 장소",
    "39": "그날의 미식",
    "25": "그날의 여정",
}

CATEGORY_DEFAULT_TYPE: dict[str, str] = {
    "그날의 장소": "관광지",
    "그날의 미식": "음식점",
    "그날의 여정": "여행코스",
}

# 관광지(12)/레포츠(28)로 등록되어 있어도 제목 기준 숙박·캠핑성 시설이면 업로드 제외
LODGING_TITLE_KEYWORDS: tuple[str, ...] = (
    "캠핑",
    "야영장",
    "오토캠핑",
    "글램핑",
    "카라반",
    "펜션",
    "리조트",
    "호텔",
    "모텔",
    "호스텔",
    "유스호스텔",
    "게스트하우스",
    "한옥스테이",
    "풀빌라",
    "민박",
    "콘도",
    "숙박",
)
SHELTER_TITLE_KEYWORDS = LODGING_TITLE_KEYWORDS

# 비여정(장소 + 미식 등) 누적 N개마다 여정 1개 업로드 규칙
JOURNEY_EVERY_N_POSTS = 10

# 자동 모드(--mode auto)에서 지역 미지정 시 순환할 권역 목록
AUTO_ROTATION_AREAS: tuple[str, ...] = (
    "서울", "경기", "강원", "제주", "부산",
    "경북", "전남", "충남", "전북", "경남",
    "인천", "대구", "충북", "대전", "광주",
    "울산", "세종",
)

# 자동 모드(--mode auto)에서 사용할 검색 수요 기반 인기 테마 키워드
AUTO_THEME_KEYWORDS: dict[str, tuple[str, ...]] = {
    "그날의 장소": (
        "수목원", "해수욕장", "한옥", "전망대", "폭포",
        "호수", "둘레길", "박물관", "사찰", "야경",
    ),
    "그날의 미식": (
        "카페", "베이커리", "디저트", "전통찻집", "브런치",
        "한정식", "국수", "해산물",
    ),
}

# 품질 필터 기준 (카테고리별 최소 개요 글자 수)
MIN_OVERVIEW_BY_CATEGORY: dict[str, int] = {
    "그날의 장소": 120,
    "그날의 미식": 40,
    "그날의 여정": 40,
}

# 법정동 시도 코드(lDongRegnCd) 매핑
LDONG_REGN_MAP: dict[str, str] = {
    "서울": "11",
    "서울특별시": "11",
    "부산": "26",
    "부산광역시": "26",
    "대구": "27",
    "대구광역시": "27",
    "인천": "28",
    "인천광역시": "28",
    "광주": "29",
    "광주광역시": "29",
    "대전": "30",
    "대전광역시": "30",
    "울산": "31",
    "울산광역시": "31",
    "세종": "36110",
    "세종특별자치시": "36110",
    "경기": "41",
    "경기도": "41",
    "강원": "51",
    "강원특별자치도": "51",
    "강원도": "51",
    "충북": "43",
    "충청북도": "43",
    "충남": "44",
    "충청남도": "44",
    "전북": "52",
    "전북특별자치도": "52",
    "전라북도": "52",
    "전남": "46",
    "전라남도": "46",
    "경북": "47",
    "경상북도": "47",
    "경남": "48",
    "경상남도": "48",
    "제주": "50",
    "제주특별자치도": "50",
    "제주도": "50",
}

LDONG_REGN_NAME_MAP: dict[str, str] = {
    "11": "서울",
    "26": "부산",
    "27": "대구",
    "28": "인천",
    "29": "광주",
    "30": "대전",
    "31": "울산",
    "36110": "세종",
    "41": "경기",
    "51": "강원",
    "43": "충북",
    "44": "충남",
    "52": "전북",
    "46": "전남",
    "47": "경북",
    "48": "경남",
    "50": "제주",
}


def resolve_content_type(value: str | None) -> str | None:
    """관광타입 이름 또는 숫자 코드를 표준 ContentTypeId 문자열로 변환한다."""
    if not value:
        return None
    cleaned = str(value).strip()
    if cleaned in EXCLUDED_CONTENT_TYPES or cleaned in ("행사", "축제", "숙박"):
        raise ValueError(
            f"제외 정책에 따라 업로드할 수 없는 관광타입입니다: '{value}'."
        )
    if cleaned in CONTENT_TYPE_NAME_MAP:
        return cleaned
    if cleaned in CONTENT_TYPE_MAP:
        return CONTENT_TYPE_MAP[cleaned]
    allowed_codes = [
        code for code in CONTENT_TYPE_NAME_MAP if code not in EXCLUDED_CONTENT_TYPES
    ]
    raise ValueError(
        f"지원하지 않는 관광타입입니다: '{value}'. "
        f"가능한 값: {', '.join(CONTENT_TYPE_MAP.keys())} 또는 코드({', '.join(allowed_codes)})"
    )


def is_excluded_content(
    content_type_id: str | None, title: str | None = None
) -> tuple[bool, str]:
    """행사/축제(15), 숙박(32) 및 숙박·캠핑성 콘텐츠 제외 여부를 (제외여부, 사유)로 반환한다."""
    ctype = str(content_type_id or "").strip()
    if ctype == "15":
        return True, "축제/행사 제외 정책"
    if ctype == "32":
        return True, "숙박 제외 정책"
    if ctype in EXCLUDED_CONTENT_TYPES:
        return True, f"제외 관광타입({ctype}) 정책"

    cleaned_title = str(title or "").strip()
    if cleaned_title and ctype != "25":
        if any(kw in cleaned_title for kw in LODGING_TITLE_KEYWORDS):
            return True, "숙박·캠핑성 콘텐츠 제외 정책"

    return False, ""


def resolve_blog_category(
    category: str | None = None,
    content_type_id: str | None = None,
    title: str | None = None,
) -> str:
    """사용자 지정 카테고리 또는 관광타입에 따라 공식 3대 블로그 카테고리를 반환한다."""
    if category:
        cleaned = str(category).strip()
        if cleaned in CATEGORY_ALIAS_MAP:
            return CATEGORY_ALIAS_MAP[cleaned]
        raise ValueError(
            f"지원하지 않는 블로그 카테고리입니다: '{category}'. "
            f"가능한 값: {', '.join(BLOG_CATEGORIES)}"
        )
    ctype = str(content_type_id or "")
    if ctype in CONTENT_TYPE_TO_CATEGORY:
        return CONTENT_TYPE_TO_CATEGORY[ctype]
    return "그날의 장소"


def resolve_ldong_regn(value: str | None) -> str | None:
    """지역명 또는 법정동 시도 코드를 표준 lDongRegnCd 문자열로 변환한다."""
    if not value:
        return None
    cleaned = str(value).strip()
    if cleaned in ("전국", "전체", "all", "ALL"):
        return None
    if cleaned in LDONG_REGN_NAME_MAP:
        return cleaned
    if cleaned in LDONG_REGN_MAP:
        return LDONG_REGN_MAP[cleaned]
    if cleaned.isdigit():
        return cleaned
    raise ValueError(
        f"지원하지 않는 지역명입니다: '{value}'. "
        f"예: 서울, 부산, 강원, 제주 등"
    )


class _SystemSSLAdapter(HTTPAdapter):
    """Windows 등 OS 시스템 인증서 저장소를 사용하는 requests HTTPS 어댑터."""

    def init_poolmanager(self, *args: object, **kwargs: object) -> object:
        kwargs["ssl_context"] = ssl.create_default_context()
        return super().init_poolmanager(*args, **kwargs)

    def cert_verify(
        self, conn: object, url: str, verify: object, cert: object
    ) -> None:
        super().cert_verify(conn, url, verify, cert)
        if verify is True:
            conn.ca_certs = None  # type: ignore[attr-defined]


def mount_system_ssl(session: requests.Session) -> requests.Session:
    """기존 requests.Session(OAuth2Session 포함)에 OS 시스템 SSL 어댑터를 장착한다."""
    session.mount("https://", _SystemSSLAdapter())
    return session


def create_http_session() -> requests.Session:
    """OS 시스템 인증서 저장소 기반 SSL 검증을 적용한 requests.Session을 반환한다."""
    return mount_system_ssl(requests.Session())


def get_ca_bundle_path() -> str:
    """certifi와 OS(Windows) 인증서 저장소를 병합한 CA 번들 PEM 경로를 반환한다."""
    bundle_path = Path(tempfile.gettempdir()) / "ondotrip_ca_bundle.pem"
    if bundle_path.exists() and bundle_path.stat().st_size > 0:
        return str(bundle_path)

    pems: list[str] = [Path(certifi.where()).read_text(encoding="utf-8")]
    enum_certs = getattr(ssl, "enum_certificates", None)
    if callable(enum_certs):
        for store in ("ROOT", "CA"):
            try:
                for cert_bytes, encoding, _trust in enum_certs(store):
                    if encoding == "x509_asn":
                        pems.append(ssl.DER_cert_to_PEM_cert(cert_bytes))
            except OSError:
                continue

    bundle_path.write_text("\n".join(pems), encoding="utf-8")
    return str(bundle_path)

