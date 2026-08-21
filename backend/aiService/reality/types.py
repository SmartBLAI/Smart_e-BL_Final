"""
F6 현실 대조 공용 타입.

이벤트·항차·매칭 결과를 담는다. 판정 출력(`Verdict`/`Violation`/`SkippedRule`)은
새로 만들지 않고 `ruleEngine.types` 를 그대로 쓴다 — F3·F6 이 심각도 3단계와
`passed`/`violated`/`not_evaluated` 3상태 규약을 공유해야 하고, 병렬 타입은
화면을 두 벌 만든다(`docs/ai-service/f6-customs-reality-check.md` §5).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from ruleEngine.types import Severity

# 울산항만공사 관제 이벤트 코드(ioprtVtsType) → 내부 표준 event_type.
# 모르는 코드는 버리지 않고 UNKNOWN 으로 남긴다 — normalize.py 참고.
EVENT_TYPES: Dict[str, str] = {
    "3": "ARRIVAL",
    "4": "BERTH",
    "5": "UNBERTH",
    "6": "SHIFT_BERTH",
    "7": "ANCHOR",
    "8": "WEIGH_ANCHOR",
    "9": "DEPARTURE",
}

# 정박지 시설 코드. 입항이 계류인지 묘박인지 판별하는 데 쓴다(C-STAT-01).
ANCHORAGE_FACILITY_CODE = "WAM"


@dataclass
class PortEvent:
    """관제 이벤트 1건(정규화됨)."""

    event_type: str  # EVENT_TYPES 값 또는 "UNKNOWN"
    raw_code: str  # 원본 ioprtVtsType. UNKNOWN 추적용
    occurred_at: datetime  # jobDt
    seq: int  # comCnt. 항차 내 정렬 키
    facility_code: str = ""
    facility_name: str = ""

    @property
    def is_anchorage(self) -> bool:
        return self.facility_code == ANCHORAGE_FACILITY_CODE

    def to_dict(self) -> dict:
        return {
            "event_type": self.event_type,
            "raw_code": self.raw_code,
            "occurred_at": self.occurred_at.isoformat(),
            "seq": self.seq,
            "facility_code": self.facility_code,
            "facility_name": self.facility_name,
        }


@dataclass
class Voyage:
    """항차 1건 — 같은 (콜사인, 연도, 항차번호) 이벤트 묶음, comCnt 순 정렬됨."""

    call_sign: str
    year: str
    voyage_no: str
    vessel_name_kr: str
    vessel_name_en: str
    events: List[PortEvent] = field(default_factory=list)

    @property
    def arrival(self) -> Optional[PortEvent]:
        return next((e for e in self.events if e.event_type == "ARRIVAL"), None)

    @property
    def departure(self) -> Optional[PortEvent]:
        return next(
            (e for e in reversed(self.events) if e.event_type == "DEPARTURE"), None
        )

    def to_dict(self) -> dict:
        return {
            "call_sign": self.call_sign,
            "year": self.year,
            "voyage_no": self.voyage_no,
            "vessel_name_kr": self.vessel_name_kr,
            "vessel_name_en": self.vessel_name_en,
            "events": [e.to_dict() for e in self.events],
        }


@dataclass
class VesselMatch:
    """B/L → 울산항 관제 기록 매칭 결과."""

    matched: bool
    strategy: str  # "call_sign" | "vessel_name" | "none"
    reason: str = ""  # matched=False 일 때 왜
    call_sign: Optional[str] = None
    vessel_name: Optional[str] = None
    voyage: Optional[Voyage] = None
    candidates: List[str] = field(default_factory=list)  # 동명이선 콜사인 목록

    def to_dict(self) -> dict:
        window = None
        if self.voyage and self.voyage.arrival and self.voyage.departure:
            window = {
                "arrival": self.voyage.arrival.occurred_at.isoformat(),
                "departure": self.voyage.departure.occurred_at.isoformat(),
            }
        return {
            "matched": self.matched,
            "strategy": self.strategy,
            "reason": self.reason,
            "call_sign": self.call_sign,
            "vessel_name": self.vessel_name,
            "voyage": self.voyage.voyage_no if self.voyage else None,
            "window": window,
            "candidates": self.candidates,
        }


@dataclass
class RealityContext:
    """검사 함수에 넘기는 실행 컨텍스트.

    `population` 은 매칭된 선박(콜사인)의 전 항차 목록이다 —
    C-TIME-04(체류시간 이상치)가 사분위수를 계산하는 데 쓴다.
    """

    match: VesselMatch
    population: List[Voyage] = field(default_factory=list)
    as_of: Optional[datetime] = None


__all__ = [
    "ANCHORAGE_FACILITY_CODE",
    "EVENT_TYPES",
    "PortEvent",
    "RealityContext",
    "Severity",
    "VesselMatch",
    "Voyage",
]
