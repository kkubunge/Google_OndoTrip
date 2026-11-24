"""한국관광공사 국문 관광정보(KorService2) 및 관광사진(PhotoGalleryService1) API 클라이언트."""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import unquote

import requests

import config

logger = logging.getLogger(__name__)

# 관광사진 지역 일치 검증용 시/도 명칭 변형 매핑
_REGION_ALIAS_GROUPS: tuple[tuple[str, ...], ...] = (
    ("서울", "서울특별시", "서울시"),
    ("부산", "부산광역시", "부산시"),
    ("대구", "대구광역시", "대구시"),
    ("인천", "인천광역시", "인천시"),
    ("광주", "광주광역시", "전남광주통합특별시"),
    ("대전", "대전광역시", "대전시"),
    ("울산", "울산광역시", "울산시"),
    ("세종", "세종특별자치시", "세종시"),
    ("경기", "경기도"),
    ("강원", "강원도", "강원특별자치도"),
    ("충북", "충청북도"),
    ("충남", "충청남도"),
    ("전북", "전라북도", "전북특별자치도"),
    ("전남", "전라남도", "전남광주통합특별시"),
    ("경북", "경상북도"),
    ("경남", "경상남도"),
    ("제주", "제주도", "제주특별자치도"),
)
_SPOT_SUFFIX_RE = re.compile(
    r"(수목원|박물관|해수욕장|전망대|스카이워크|공원|둘레길|미술관|기념관|체험관)$"
)
_PAREN_RE = re.compile(r"\([^)]*\)|\[[^\]]*\]")
_IMAGE_MAGIC_PREFIXES: tuple[bytes, ...] = (
    b"\xff\xd8",  # JPEG
    b"\x89PNG",   # PNG
    b"GIF8",      # GIF
    b"BM",        # BMP
)


def _has_image_magic(head: bytes) -> bool:
    """앞부분 바이트가 실제 이미지 파일 시그니처인지 확인한다."""
    if not head:
        return False
    if any(head.startswith(sig) for sig in _IMAGE_MAGIC_PREFIXES):
        return True
    return len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP"


def is_valid_image_url(
    url: str,
    session: requests.Session | None = None,
    timeout: int = 8,
) -> bool:
    """실제 HTTP HEAD/GET 검증으로 404 등 깨진 이미지 URL을 차단한다."""
    cleaned = str(url or "").strip()
    if not cleaned.startswith(("http://", "https://")):
        return False

    owns_session = session is None
    sess = session or config.create_http_session()
    try:
        try:
            head_resp = sess.head(cleaned, timeout=timeout, allow_redirects=True)
            if head_resp.status_code == 200:
                ct = str(head_resp.headers.get("Content-Type") or "").lower()
                cl_raw = str(head_resp.headers.get("Content-Length") or "").strip()
                cl_ok = (not cl_raw.isdigit()) or int(cl_raw) > 0
                if ct.startswith("image/") and cl_ok:
                    return True
            if head_resp.status_code in (404, 410):
                return False
        except Exception:
            pass

        try:
            with sess.get(
                cleaned,
                headers={"Range": "bytes=0-31"},
                stream=True,
                timeout=timeout,
                allow_redirects=True,
            ) as get_resp:
                if get_resp.status_code not in (200, 206):
                    return False
                ct = str(get_resp.headers.get("Content-Type") or "").lower()
                chunk = next(get_resp.iter_content(chunk_size=32), b"")
                if _has_image_magic(chunk):
                    return True
                return ct.startswith("image/") and len(chunk) > 0
        except Exception:
            return False
    finally:
        if owns_session:
            sess.close()


class TourAPIError(RuntimeError):
    """한국관광공사 Open API 호출 중 오류가 발생했을 때 사용하는 예외."""


class PhotoGalleryClient:
    """한국관광공사 관광사진 정보(PhotoGalleryService1, 매뉴얼 v4.2) 조회 클라이언트."""

    def __init__(
        self,
        api_key: str | None = None,
        endpoint: str | None = None,
        mobile_app: str = "OndoTrip",
        timeout: int = 15,
    ) -> None:
        raw_key = api_key or config.PHOTO_API_KEY
        if not raw_key:
            raise ValueError("PHOTO_API_KEY 또는 TOUR_API_KEY가 설정되어 있지 않습니다.")
        # 공공데이터포털 Encoding 키 이중 인코딩 방지
        self.service_key = unquote(raw_key)
        self.endpoint = (endpoint or config.PHOTO_API_ENDPOINT).rstrip("/")
        self.mobile_app = mobile_app
        self.timeout = timeout
        self.session = config.create_http_session()

    @staticmethod
    def format_photo_month(raw: Any) -> str:
        """촬영월(YYYYMM)과 일부 YYMMDD(예: 260414) 혼재 값을 읽기 쉬운 날짜로 포맷한다."""
        digits = re.sub(r"\D", "", str(raw or ""))
        if len(digits) == 6:
            if digits.startswith(("19", "20")):
                return f"{digits[:4]}.{digits[4:6]}"
            return f"20{digits[:2]}.{digits[2:4]}.{digits[4:6]}"
        if len(digits) == 8:
            return f"{digits[:4]}.{digits[4:6]}.{digits[6:8]}"
        return str(raw or "").strip()

    @staticmethod
    def _clean_search_title(title: str) -> str:
        """괄호 부가 설명과 중복 공백을 정리해 검색에 적합한 핵심 명칭을 만든다."""
        stripped = _PAREN_RE.sub(" ", str(title or ""))
        return re.sub(r"\s+", " ", stripped).strip()

    @staticmethod
    def _extract_region_hints(addr1: str) -> tuple[tuple[str, ...], list[str]]:
        """주소 첫/둘째 토큰에서 시/도 별칭 그룹과 시/군/구 토큰을 추출한다."""
        tokens = str(addr1 or "").strip().split()
        if not tokens:
            return (), []

        first = tokens[0]
        prov_aliases: tuple[str, ...] = ()
        for group in _REGION_ALIAS_GROUPS:
            if any(first == alias or first.startswith(alias) for alias in group):
                prov_aliases = group
                break

        city_tokens: list[str] = []
        if len(tokens) >= 2:
            second = tokens[1].strip()
            if len(second) >= 2:
                city_tokens.append(second)
                short_city = re.sub(r"(시|군|구)$", "", second)
                if len(short_city) >= 2 and short_city != second:
                    city_tokens.append(short_city)
        return prov_aliases, city_tokens

    @staticmethod
    def _matches_location(
        addr1: str, gal_location: str, gal_keywords: str
    ) -> bool:
        """촬영장소·키워드가 대상 주소 권역과 일치하는지 검증해 동명이지 오매칭을 막는다."""
        if not addr1.strip():
            return True
        prov_aliases, city_tokens = PhotoGalleryClient._extract_region_hints(addr1)
        if not prov_aliases and not city_tokens:
            return True

        photo_loc = str(gal_location or "").strip()
        target_blob = f"{photo_loc} {gal_keywords}".strip()
        if not target_blob:
            return False

        # 촬영장소에 명백히 다른 시/도가 표기되어 있으면 제외 (시/군/구 일치 시에도 도가 다르면 배제)
        if photo_loc and prov_aliases:
            photo_first = photo_loc.split()[0]
            for group in _REGION_ALIAS_GROUPS:
                if group == prov_aliases:
                    continue
                if any(photo_first == a or photo_first.startswith(a) for a in group):
                    # 단, 통합명칭/도-시 공유 예외 방지를 위해 우리 시/도 별칭이 전혀 없을 때만 차단
                    if not any(alias in photo_loc for alias in prov_aliases):
                        return False

        if any(alias in target_blob for alias in prov_aliases):
            return True
        if any(city in target_blob for city in city_tokens):
            return True
        return False

    @staticmethod
    def _matches_keyword(
        search_kw: str,
        gal_title: str,
        gal_keywords: str,
        *,
        strict_exact: bool = False,
    ) -> bool:
        """검색 핵심어가 사진 제목 또는 검색 키워드에 실제로 매칭되는지 검증한다."""
        compact_kw = re.sub(r"\s+", "", search_kw)
        if len(compact_kw) < 2:
            return False
        compact_blob = re.sub(r"\s+", "", f"{gal_title} {gal_keywords}")
        if compact_kw in compact_blob:
            return True
        if strict_exact:
            return False
        parts = [p for p in search_kw.split() if len(p) >= 2]
        return bool(parts) and all(p in compact_blob for p in parts)

    def search_photos(
        self,
        keyword: str,
        num_of_rows: int = 20,
        page_no: int = 1,
        arrange: str = "A",
    ) -> list[dict[str, Any]]:
        """키워드로 관광사진갤러리(/gallerySearchList1) 목록을 조회한다."""
        url = f"{self.endpoint}/gallerySearchList1"
        query = {
            "serviceKey": self.service_key,
            "MobileOS": "ETC",
            "MobileApp": self.mobile_app,
            "_type": "json",
            "arrange": arrange,
            "numOfRows": num_of_rows,
            "pageNo": page_no,
            "keyword": keyword,
        }
        resp = self.session.get(url, params=query, timeout=self.timeout)
        resp.raise_for_status()
        text = resp.text.strip()
        if text.startswith("<"):
            raise TourAPIError(TourAPIClient._parse_xml_error("gallerySearchList1", text))
        data = resp.json()
        inner = data.get("response", {})
        header = inner.get("header", {})
        if str(header.get("resultCode", "")) != "0000":
            raise TourAPIError(
                f"[gallerySearchList1] API 오류 ({header.get('resultCode')}: {header.get('resultMsg')})"
            )
        return TourAPIClient._extract_items(inner.get("body", {}))

    def find_matching_photos(
        self,
        title: str,
        addr1: str = "",
        content_type_id: str = "12",
        info_list: list[dict[str, Any]] | None = None,
        max_count: int = 4,
    ) -> list[dict[str, Any]]:
        """장소·미식·여정 콘텐츠에 오매칭 없이 어울리는 관광사진 목록을 찾는다."""
        clean_title = self._clean_search_title(title)
        if not clean_title:
            return []

        ctype = str(content_type_id or "12").strip()
        strict_food = ctype == "39"

        # 검색 후보 목록: (검색어, 매칭기준명, 최대수집수, 엄격일치여부)
        search_targets: list[tuple[str, str, int, bool]] = [
            (clean_title, clean_title, max_count, strict_food)
        ]

        # 장소 등 4자 이상이면서 일반 시설 접미사로 끝나면 본명 2차 후보 준비 (미식 제외)
        if ctype != "39" and len(clean_title) >= 4:
            stripped_base = _SPOT_SUFFIX_RE.sub("", clean_title).strip()
            if (
                stripped_base
                and stripped_base != clean_title
                and len(re.sub(r"\s+", "", stripped_base)) >= 2
            ):
                search_targets.append((stripped_base, clean_title, max_count, False))

        # 여행코스(25)는 경유지 subname(최대 4개)도 함께 조회
        if ctype == "25" and info_list:
            for sub in info_list[:4]:
                sub_raw = str(sub.get("subname") or "").strip()
                sub_clean = self._clean_search_title(sub_raw)
                if sub_clean and sub_clean != clean_title:
                    search_targets.append((sub_clean, sub_clean, 2, False))

        results: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        seen_urls: set[str] = set()
        queried_keywords: set[str] = set()

        for query_kw, matched_spot, cap_for_target, is_strict in search_targets:
            if len(results) >= max_count:
                break
            if query_kw in queried_keywords:
                continue
            # 1차 원제목 검색에서 이미 충분히 찾았으면 2차 접미사 제거 검색은 생략
            if ctype != "25" and results and query_kw != clean_title:
                continue
            queried_keywords.add(query_kw)

            try:
                raw_items = self.search_photos(query_kw, num_of_rows=20, arrange="A")
            except Exception as exc:
                logger.warning("관광사진 검색 실패 (%s): %s", query_kw, exc)
                continue

            added_for_target = 0
            for item in raw_items:
                raw_url = str(item.get("galWebImageUrl") or "").strip()
                if not raw_url:
                    continue
                https_url = (
                    "https://" + raw_url[7:] if raw_url.startswith("http://") else raw_url
                )
                cid = str(item.get("galContentId") or "").strip()
                if cid in seen_ids or https_url in seen_urls:
                    continue

                gal_title = str(item.get("galTitle") or "").strip()
                gal_loc = str(item.get("galPhotographyLocation") or "").strip()
                gal_kw = str(item.get("galSearchKeyword") or "").strip()

                if not self._matches_keyword(
                    query_kw, gal_title, gal_kw, strict_exact=is_strict
                ):
                    continue
                if not self._matches_location(addr1, gal_loc, gal_kw):
                    continue
                if not is_valid_image_url(https_url, session=self.session):
                    logger.info("깨진 관광사진 URL 건너뜀: %s (%s)", https_url, gal_title)
                    continue

                seen_ids.add(cid)
                seen_urls.add(https_url)
                kw_tags = [
                    t.strip() for t in gal_kw.split(",") if t.strip()
                ][:5]
                results.append(
                    {
                        "content_id": cid,
                        "title": gal_title or matched_spot,
                        "url": https_url,
                        "photo_date": self.format_photo_month(
                            item.get("galPhotographyMonth")
                        ),
                        "location": gal_loc,
                        "photographer": str(
                            item.get("galPhotographer") or "한국관광공사"
                        ).strip(),
                        "keywords": kw_tags,
                        "source": "PhotoGalleryService1",
                        "matched_spot": matched_spot,
                    }
                )
                added_for_target += 1
                if len(results) >= max_count or added_for_target >= cap_for_target:
                    break

        return results


class TourAPIClient:
    """KorService2 오퍼레이션을 호출하고 결과를 정규화하는 클라이언트."""

    def __init__(
        self,
        api_key: str | None = None,
        endpoint: str | None = None,
        mobile_app: str = "OndoTrip",
        timeout: int = 20,
    ) -> None:
        raw_key = api_key or config.TOUR_API_KEY
        if not raw_key:
            raise ValueError("TOUR_API_KEY가 설정되어 있지 않습니다.")
        # 공공데이터포털 Encoding 키가 requests에서 이중 인코딩되지 않도록 디코딩
        self.service_key = unquote(raw_key)
        self.endpoint = (endpoint or config.TOUR_API_ENDPOINT).rstrip("/")
        self.mobile_app = mobile_app
        self.timeout = timeout
        self.session = config.create_http_session()
        self.photo_client: PhotoGalleryClient | None = (
            PhotoGalleryClient(api_key=config.PHOTO_API_KEY, mobile_app=mobile_app)
            if config.PHOTO_API_KEY
            else None
        )

    def _request(self, operation: str, **params: Any) -> dict[str, Any]:
        """공통 파라미터를 포함해 KorService2 GET 요청을 수행한다."""
        url = f"{self.endpoint}/{operation}"
        query: dict[str, Any] = {
            "serviceKey": self.service_key,
            "MobileOS": "ETC",
            "MobileApp": self.mobile_app,
            "_type": "json",
        }
        for key, value in params.items():
            if value is not None and value != "":
                query[key] = value

        response = self.session.get(url, params=query, timeout=self.timeout)
        response.raise_for_status()
        text = response.text.strip()

        if text.startswith("<"):
            raise TourAPIError(self._parse_xml_error(operation, text))

        data = response.json()
        resp = data.get("response", {})
        header = resp.get("header", {})
        result_code = str(header.get("resultCode", ""))
        result_msg = str(header.get("resultMsg", ""))
        if result_code != "0000":
            raise TourAPIError(
                f"[{operation}] API 오류 (코드: {result_code}, 메시지: {result_msg})"
            )
        return resp.get("body", {})

    @staticmethod
    def _parse_xml_error(operation: str, xml_text: str) -> str:
        """공공데이터포털 XML 오류 응답에서 에러 코드와 메시지를 추출한다."""
        try:
            root = ET.fromstring(xml_text)
            auth_msg = root.findtext(".//returnAuthMsg") or ""
            reason_code = root.findtext(".//returnReasonCode") or ""
            err_msg = root.findtext(".//errMsg") or "XML 오류 응답"
            return (
                f"[{operation}] {err_msg} "
                f"(코드: {reason_code}, 상세: {auth_msg})"
            )
        except ET.ParseError:
            return f"[{operation}] XML 오류 응답: {xml_text[:200]}"

    @staticmethod
    def _extract_items(body: dict[str, Any]) -> list[dict[str, Any]]:
        """응답 body의 items.item을 항상 리스트 형태로 정규화한다."""
        items = body.get("items")
        if not items or isinstance(items, str):
            return []
        item = items.get("item")
        if not item:
            return []
        if isinstance(item, dict):
            return [item]
        if isinstance(item, list):
            return [entry for entry in item if isinstance(entry, dict)]
        return []

    def get_area_based_list(
        self,
        content_type_id: str | None = "12",
        ldong_regn_cd: str | None = None,
        ldong_signgu_cd: str | None = None,
        arrange: str = "Q",
        num_of_rows: int = 20,
        page_no: int = 1,
    ) -> list[dict[str, Any]]:
        """지역기반 관광정보 목록(/areaBasedList2)을 조회한다."""
        body = self._request(
            "areaBasedList2",
            contentTypeId=content_type_id,
            lDongRegnCd=ldong_regn_cd,
            lDongSignguCd=ldong_signgu_cd if ldong_regn_cd else None,
            arrange=arrange,
            numOfRows=num_of_rows,
            pageNo=page_no,
        )
        return self._extract_items(body)

    def search_keyword(
        self,
        keyword: str,
        ldong_regn_cd: str | None = None,
        arrange: str = "Q",
        num_of_rows: int = 20,
        page_no: int = 1,
    ) -> list[dict[str, Any]]:
        """키워드 검색(/searchKeyword2)으로 관광정보 목록을 조회한다."""
        # Ver 4.4 기준 searchKeyword2에는 contentTypeId 파라미터가 없음
        body = self._request(
            "searchKeyword2",
            keyword=keyword,
            lDongRegnCd=ldong_regn_cd,
            arrange=arrange,
            numOfRows=num_of_rows,
            pageNo=page_no,
        )
        return self._extract_items(body)

    def search_festival(
        self,
        event_start_date: str,
        event_end_date: str | None = None,
        ldong_regn_cd: str | None = None,
        arrange: str = "Q",
        num_of_rows: int = 20,
        page_no: int = 1,
    ) -> list[dict[str, Any]]:
        """행사/축제 정보(/searchFestival2)를 날짜 기준으로 조회한다."""
        body = self._request(
            "searchFestival2",
            eventStartDate=event_start_date,
            eventEndDate=event_end_date,
            lDongRegnCd=ldong_regn_cd,
            arrange=arrange,
            numOfRows=num_of_rows,
            pageNo=page_no,
        )
        return self._extract_items(body)

    def get_detail_common(self, content_id: str) -> dict[str, Any]:
        """공통정보(/detailCommon2)를 조회한다."""
        # Ver 4.4 기준 contentId만 전달하면 전체 공통정보 반환
        body = self._request(
            "detailCommon2",
            contentId=str(content_id),
            numOfRows=10,
            pageNo=1,
        )
        items = self._extract_items(body)
        return items[0] if items else {}

    def get_detail_intro(
        self, content_id: str, content_type_id: str
    ) -> dict[str, Any]:
        """소개정보(/detailIntro2)를 조회한다."""
        body = self._request(
            "detailIntro2",
            contentId=str(content_id),
            contentTypeId=str(content_type_id),
            numOfRows=10,
            pageNo=1,
        )
        items = self._extract_items(body)
        return items[0] if items else {}

    def get_detail_info(
        self, content_id: str, content_type_id: str
    ) -> list[dict[str, Any]]:
        """반복정보(/detailInfo2)를 조회한다."""
        body = self._request(
            "detailInfo2",
            contentId=str(content_id),
            contentTypeId=str(content_type_id),
            numOfRows=30,
            pageNo=1,
        )
        return self._extract_items(body)

    def get_detail_images(self, content_id: str) -> list[dict[str, Any]]:
        """이미지정보(/detailImage2)를 조회한다."""
        body = self._request(
            "detailImage2",
            contentId=str(content_id),
            imageYN="Y",
            numOfRows=20,
            pageNo=1,
        )
        return self._extract_items(body)

    def get_detail_pet_tour(self, content_id: str) -> dict[str, Any]:
        """반려동물 동반여행 정보(/detailPetTour2)를 조회한다."""
        body = self._request(
            "detailPetTour2",
            contentId=str(content_id),
            numOfRows=10,
            pageNo=1,
        )
        items = self._extract_items(body)
        for item in items:
            if str(item.get("contentid", "")) == str(content_id):
                return item
        return {}

    def _safe_call(self, fn: Any, *args: Any, default: Any) -> Any:
        """부가 상세 API 호출 실패 시 전체 수집이 중단되지 않도록 방어한다."""
        try:
            return fn(*args)
        except Exception as exc:
            logger.warning("부가 상세 정보 조회 생략 (%s): %s", fn.__name__, exc)
            return default

    def get_full_spot_bundle(
        self,
        content_id: str,
        content_type_id: str | None = None,
        summary_item: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """단일 콘텐츠의 공통·소개·반복·이미지·반려동물 상세정보를 통합 수집한다."""
        cid = str(content_id)
        common = self.get_detail_common(cid)
        if not common and summary_item:
            common = dict(summary_item)

        ctype = str(
            content_type_id
            or common.get("contenttypeid")
            or (summary_item or {}).get("contenttypeid")
            or "12"
        )

        intro = self._safe_call(self.get_detail_intro, cid, ctype, default={})
        info_list = self._safe_call(self.get_detail_info, cid, ctype, default=[])
        if ctype == "25" and info_list:
            sub_cache: dict[str, dict[str, Any]] = {}
            for item in info_list:
                subcid = str(item.get("subcontentid") or "").strip()
                if not subcid:
                    continue
                if subcid not in sub_cache:
                    sub_cache[subcid] = self._safe_call(
                        self.get_detail_common, subcid, default={}
                    )
                sub_common = sub_cache[subcid]
                if not sub_common:
                    continue
                item["sub_addr1"] = str(sub_common.get("addr1") or "").strip()
                item["sub_mapx"] = str(sub_common.get("mapx") or "").strip()
                item["sub_mapy"] = str(sub_common.get("mapy") or "").strip()
                if not str(item.get("subdetailoverview") or "").strip() and sub_common.get("overview"):
                    item["subdetailoverview"] = sub_common["overview"]

        images = self._safe_call(self.get_detail_images, cid, default=[])
        pet_info = self._safe_call(self.get_detail_pet_tour, cid, default={})

        spot_title = str(
            common.get("title") or (summary_item or {}).get("title") or ""
        ).strip()
        addr1 = str(
            common.get("addr1") or (summary_item or {}).get("addr1") or ""
        ).strip()
        photo_gallery = (
            self._safe_call(
                self.photo_client.find_matching_photos,
                spot_title,
                addr1,
                ctype,
                info_list,
                config.PHOTO_GALLERY_MAX_IMAGES,
                default=[],
            )
            if self.photo_client and spot_title
            else []
        )

        return {
            "content_id": cid,
            "content_type_id": ctype,
            "summary": summary_item or {},
            "common": common,
            "intro": intro,
            "info_list": info_list,
            "images": images,
            "photo_gallery": photo_gallery,
            "pet_info": pet_info,
        }
