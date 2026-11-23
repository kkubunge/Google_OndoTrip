"""한국관광공사 국문 관광정보 서비스(KorService2, 매뉴얼 Ver 4.4) API 클라이언트."""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import unquote

import requests

import config

logger = logging.getLogger(__name__)


class TourAPIError(RuntimeError):
    """한국관광공사 Open API 호출 중 오류가 발생했을 때 사용하는 예외."""


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
        images = self._safe_call(self.get_detail_images, cid, default=[])
        pet_info = self._safe_call(self.get_detail_pet_tour, cid, default={})

        return {
            "content_id": cid,
            "content_type_id": ctype,
            "summary": summary_item or {},
            "common": common,
            "intro": intro,
            "info_list": info_list,
            "images": images,
            "pet_info": pet_info,
        }
