"""
울산항만공사 관제 레코드 정규화.

원시 레코드는 `callsgn`·`ptentVtsYr`·`vyg`·`comCnt`·`vslKornNm`·`vslEngNm`·
`ioprtVtsType`·`fcltSpecCd`·`fcltKornNm`·`jobDt` 등을 가진다(시각은
`YYYYMMDDHHMMSS`).

판정에 쓰는 시각은 `jobDt` 하나다. `ptentDt`/`dfptDt` 는 항차 전체의
기준값이지 이벤트별 시각이 아니고, `updtDt` 는 레코드 갱신 시각이라 사건
시각이 아니다(design doc §3.1).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List

from .types import EVENT_TYPES, PortEvent, Voyage

_TIMESTAMP_FORMAT = "%Y%m%d%H%M%S"


class NormalizeError(ValueError):
    """레코드 형식이 예상과 다를 때."""


def _parse_timestamp(raw: Any) -> datetime:
    try:
        return datetime.strptime(str(raw), _TIMESTAMP_FORMAT)
    except (TypeError, ValueError) as exc:
        raise NormalizeError(f"시각을 해석할 수 없습니다: {raw!r}") from exc


def record_to_event(record: Dict[str, Any]) -> PortEvent:
    code = str(record.get("ioprtVtsType", ""))
    return PortEvent(
        event_type=EVENT_TYPES.get(code, "UNKNOWN"),
        raw_code=code,
        occurred_at=_parse_timestamp(record.get("jobDt")),
        seq=int(record.get("comCnt", 0)),
        facility_code=str(record.get("fcltSpecCd", "")),
        facility_name=str(record.get("fcltKornNm", "")),
    )


def group_voyages(records: List[Dict[str, Any]]) -> Dict[str, List[Voyage]]:
    """원시 레코드를 콜사인별 항차 목록으로 그룹핑한다.

    그룹 키는 (callsgn, ptentVtsYr, vyg), 정렬은 comCnt. 반환은
    콜사인 → 항차 목록(연도·항차번호 오름차순)이다 — matcher.py 가
    콜사인으로 1차 필터링한 뒤 날짜로 항차를 고른다.
    """
    buckets: Dict[tuple, List[Dict[str, Any]]] = defaultdict(list)
    for record in records:
        call_sign = str(record.get("callsgn", ""))
        year = str(record.get("ptentVtsYr", ""))
        voyage_no = str(record.get("vyg", ""))
        if not call_sign or not voyage_no:
            continue
        buckets[(call_sign, year, voyage_no)].append(record)

    by_call_sign: Dict[str, List[Voyage]] = defaultdict(list)
    for (call_sign, year, voyage_no), recs in buckets.items():
        recs_sorted = sorted(recs, key=lambda r: int(r.get("comCnt", 0)))
        voyage = Voyage(
            call_sign=call_sign,
            year=year,
            voyage_no=voyage_no,
            vessel_name_kr=str(recs_sorted[0].get("vslKornNm", "")),
            vessel_name_en=str(recs_sorted[0].get("vslEngNm", "")),
            events=[record_to_event(r) for r in recs_sorted],
        )
        by_call_sign[call_sign].append(voyage)

    for voyages in by_call_sign.values():
        voyages.sort(key=lambda v: (v.year, v.voyage_no))
    return dict(by_call_sign)


__all__ = ["NormalizeError", "group_voyages", "record_to_event"]
