"""
울산항만공사 "항만 내 선박 운항정보" 이벤트 소스.

`EventSource` 는 원시 레코드(dict) 목록을 돌려주는 것까지만 책임진다 —
정규화(`normalize.py`)와는 다른 관심사다. 소스를 바꿔도(fixture ↔ 실 API)
정규화·매칭·룰은 그대로 둘 수 있다.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol
from urllib import parse as urlparse
from urllib import request as urlrequest
from xml.etree import ElementTree as ET

DEFAULT_FIXTURE_PATH = Path(__file__).with_name("fixtures") / "ulsan_vts_2025.json"

# 해양수산부_선박제원정보. 선명 → 콜사인 역방향 조회에 쓴다(울산항 VTS 는
# 선명으로 못 거른다). 고정 엔드포인트라 URL 자체는 상수로 둔다 — 필요하면
# MOF_VSSL_BASE_URL 로 덮어쓸 수 있다.
DEFAULT_MOF_VSSL_URL = "https://apis.data.go.kr/1192000/SicsVsslManp3/Info3"


class EventSourceError(RuntimeError):
    """이벤트 소스 호출·설정 오류. main.py 가 503 으로 번역한다."""


def _mask_service_key(text: str) -> str:
    """오류 메시지에 URL 이 통째로 실릴 때(예: 스킴 없는 base_url 이면
    urlopen 이 `ValueError: unknown url type: '<전체 URL>'` 을 던진다)
    `serviceKey=` 뒤 값을 지운다 — 로그(`docker logs`)로 실키가 새는 걸 막는다.
    """
    return re.sub(r"(serviceKey=)[^&\s]+", r"\1***", text)


class EventSource(Protocol):
    name: str

    def fetch(
        self, *, call_sign: Optional[str] = None, year: Optional[str] = None
    ) -> List[Dict[str, Any]]: ...


class FixtureSource:
    """패키지 내 샘플 JSON. 개발·테스트·인증키 미발급 상태의 기본값.

    샘플은 이미 전체 선박이 섞여 있고 매칭은 엔진이 클라이언트에서 하므로
    `call_sign`/`year` 는 받되 무시한다(실 API 소스와 시그니처만 맞춘다).
    """

    name = "fixture"

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path or Path(
            os.getenv("REALITY_FIXTURE_PATH", "") or DEFAULT_FIXTURE_PATH
        )

    def fetch(
        self, *, call_sign: Optional[str] = None, year: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            raise EventSourceError(
                f"샘플 이벤트 파일을 읽을 수 없습니다: {self.path}"
            ) from exc
        if not isinstance(data, list):
            raise EventSourceError(f"샘플 이벤트 파일 형식이 잘못되었습니다: {self.path}")
        return data


class UlsanVtsSource:
    """공공데이터포털 실 API.

    설정이 없으면(키 미발급) 즉시 EventSourceError 를 던진다 — 빈 이벤트
    목록으로 조용히 떨어지면 그 결과는 '경보 없음'으로 읽힌다
    (design doc §1 무상태 절과 같은 이유).
    """

    name = "ulsan"

    def __init__(
        self,
        base_url: Optional[str] = None,
        service_key: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> None:
        self.base_url = base_url or os.getenv("ULSAN_VTS_BASE_URL", "")
        self.service_key = service_key or os.getenv("ULSAN_VTS_SERVICE_KEY", "")
        self.timeout = timeout or float(os.getenv("ULSAN_VTS_TIMEOUT", "8"))

    def fetch(
        self, *, call_sign: Optional[str] = None, year: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        if not self.base_url or not self.service_key or self.service_key == "changeme":
            raise EventSourceError(
                "ULSAN_VTS_BASE_URL/ULSAN_VTS_SERVICE_KEY 가 설정되지 않았습니다"
            )
        if not call_sign:
            # 실측 확인: callsgn 없이 호출하면 (ptentVtsYr 유무와 무관하게)
            # 게이트웨이가 HTTP_ERROR(reasonCode 04)를 낸다 — 전체 목록
            # 조회를 지원하지 않는다. 그래서 이 API 는 선박을 먼저 알아야
            # 조회할 수 있다(엔진이 fetch 전에 call_sign 을 넘겨야 한다).
            raise EventSourceError(
                "울산항 VTS 는 callsgn 없이 호출할 수 없습니다 — 콜사인을 알아야 조회할 수 있습니다"
            )
        # serviceKey 는 공공데이터포털이 이미 퍼센트 인코딩해 발급하는
        # "Encoding" 키다 — urlencode 에 그대로 넣으면 %2B 가 %252B 로
        # 이중 인코딩되어 인증이 깨진다. 그래서 이 값만 인코딩 없이 붙인다.
        #
        # 파라미터명은 API 문서(docs/endpoint screen shot.png) 기준 — JSON
        # 요청은 `resultType=json` 이다("type" 이 아니다).
        params: Dict[str, str] = {
            "resultType": "json",
            "numOfRows": "1000",
            "pageNo": "1",
            "callsgn": call_sign,
        }
        if year:
            params["ptentVtsYr"] = year
        query = urlparse.urlencode(params)
        url = f"{self.base_url}?serviceKey={self.service_key}&{query}"
        try:
            with urlrequest.urlopen(url, timeout=self.timeout) as resp:
                data = json.loads(resp.read())
        except Exception as exc:
            # 잡히지 않은 예외 타입(예: base_url 에 스킴이 없으면 urlopen 이
            # 던지는 ValueError)도 여기서 막는다 — 그 예외 메시지엔 요청
            # URL 전체(serviceKey 포함)가 그대로 들어있다.
            raise EventSourceError(
                f"울산항 VTS 호출에 실패했습니다: {_mask_service_key(str(exc))}"
            ) from exc
        return _extract_items(data)


def _extract_items(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """실 응답에서 레코드 목록을 뽑는다.

    실측 결과 이 API 는 세 가지 봉투 모양을 섞어 쓴다:
      1) 정상 — `response.body.items.item`(레코드 1건이면 item 이 dict).
      2) 결과 없음 — 최상위 `{"resultCode":"030","resultMsg":"NODATA_ERROR"}`.
         오류가 아니라 0건이라 빈 리스트로 취급한다.
      3) 게이트웨이 오류 — `OpenAPI_ServiceResponse.cmmMsgHeader`(파라미터
         누락 등). 진짜 오류라 EventSourceError 로 올린다.
    """
    if "response" in data:
        header = data["response"].get("header", {})
        if header.get("resultCode") not in (None, "00"):
            raise EventSourceError(
                f"울산항 VTS 오류: {header.get('resultCode')} {header.get('resultMsg')}"
            )
        body = data["response"].get("body", {})
        items = body.get("items", [])
        if isinstance(items, dict):
            items = items.get("item", [])
        if isinstance(items, dict):
            items = [items]
        if items == "":
            items = []
        if not isinstance(items, list):
            raise EventSourceError("울산항 VTS 응답 형식이 예상과 다릅니다")
        # numOfRows=1000 으로 고정 요청한다 — 실제 전체 건수가 이보다 많으면
        # 뒷부분이 조용히 잘려서, 있던 이벤트가 "없음"으로 오판될 수 있다.
        # 페이지네이션 대신 잘렸다는 사실 자체를 오류로 드러낸다(P2-4).
        try:
            total_count = int(body.get("totalCount"))
        except (TypeError, ValueError):
            total_count = None
        if total_count is not None and total_count > len(items):
            raise EventSourceError(
                f"울산항 VTS 응답이 잘렸습니다: 전체 {total_count}건 중 {len(items)}건만 받았습니다"
            )
        return items
    if data.get("resultCode") == "030":
        return []
    alt = data.get("OpenAPI_ServiceResponse", {}).get("cmmMsgHeader")
    if alt:
        raise EventSourceError(
            f"울산항 VTS 오류: {alt.get('returnReasonCode')} {alt.get('errMsg')}"
        )
    raise EventSourceError("울산항 VTS 응답 형식이 예상과 다릅니다")


def resolve_call_sign(
    vessel_name: str,
    *,
    base_url: Optional[str] = None,
    service_key: Optional[str] = None,
    timeout: Optional[float] = None,
) -> Optional[str]:
    """선명으로 해양수산부 선박제원정보에서 콜사인을 찾는다.

    울산항 VTS 는 callsgn 없이 조회가 안 되므로, 요청에 call_sign 이
    없으면 이걸로 먼저 찾는다. `vsslNm` 검색은 부분일치다(실측: "OSUNG"
    검색에 "NO.2000 BOSUNG"도 걸림) — 그래서 응답에서 영문/국문 선명이
    "정확히" 같은 항목만 받아들인다. 0건이거나 동명이선박으로 하나로 안
    좁혀지면 `None` — 조회 실패가 아니라 "특정 못 함"이라 예외를 던지지
    않는다(design doc §6: 매칭 실패는 오류가 아니라 정상 결과).
    """
    # B/L 선명("M/V OSUNG / 2608E")을 그대로 검색·비교하면 제원의 "OSUNG"과 영영
    # 안 맞는다 — 매칭과 같은 정규화로 검색어를 만들고 비교도 정규화 키로 한다.
    from .matcher import strip_vessel_affixes, vessel_key

    name = strip_vessel_affixes(vessel_name)
    if not name:
        return None
    key = vessel_key(name)
    base_url = base_url or os.getenv("MOF_VSSL_BASE_URL", "") or DEFAULT_MOF_VSSL_URL
    # 공공데이터포털 일반인증키는 계정 단위라, 울산항 VTS 에 쓰는 키를
    # 승인된 다른 API(이 서비스)에도 그대로 쓸 수 있다(실측 확인).
    service_key = service_key or os.getenv("ULSAN_VTS_SERVICE_KEY", "")
    timeout = timeout or float(os.getenv("ULSAN_VTS_TIMEOUT", "8"))
    if not service_key or service_key == "changeme":
        return None
    query = urlparse.urlencode({"pageNo": "1", "numOfRows": "50", "vsslNm": name})
    url = f"{base_url}?serviceKey={service_key}&{query}"
    try:
        with urlrequest.urlopen(url, timeout=timeout) as resp:
            root = ET.fromstring(resp.read())
    except Exception:
        # UlsanVtsSource.fetch() 와 같은 이유로 catch-all — 여기는 예외를
        # 다시 던지지 않고 그냥 "특정 못 함"(None)으로 삼키므로 메시지에
        # 키가 실릴 일 자체가 없다(마스킹 불필요).
        return None
    if root.findtext("header/resultCode") != "00":
        return None
    matches = {
        item.findtext("clsgn")
        for item in root.findall("body/items/item")
        if vessel_key(item.findtext("vsslEngNm") or "") == key
        or vessel_key(item.findtext("vsslKorNm") or "") == key
    }
    matches.discard(None)
    matches.discard("")
    if len(matches) == 1:
        return next(iter(matches))
    return None


def source_from_env() -> EventSource:
    """`REALITY_EVENT_SOURCE` 로 소스를 고른다. 기본은 fixture."""
    name = os.getenv("REALITY_EVENT_SOURCE", "fixture").strip().lower()
    if name == "ulsan":
        return UlsanVtsSource()
    return FixtureSource()


__all__ = [
    "DEFAULT_FIXTURE_PATH",
    "DEFAULT_MOF_VSSL_URL",
    "EventSource",
    "EventSourceError",
    "FixtureSource",
    "UlsanVtsSource",
    "resolve_call_sign",
    "source_from_env",
]
