"""
B/L → 울산항 관제 기록 매칭.

콜사인이 1급 키인데 B/L 에는 콜사인 칸이 없다(`ocr/types.py:BLFields` 참고).
그래서 이름으로 조인하고, 이름 매칭은 접두/접미 표기 흔들림과 동명이선을
흡수해야 한다(design doc §3.2).
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from terms import normalize_key

from .types import VesselMatch, Voyage

# B/L 선명에 흔히 붙는 접두·접미. 정규화 키 계산 전에 벗겨낸다.
_VESSEL_PREFIX = re.compile(r"^(M/?V|M/?T|S/?S)\.?\s+", re.IGNORECASE)
_VOYAGE_SUFFIX = re.compile(r"\s*V\.?\s*\d+[A-Z]?\s*$", re.IGNORECASE)
_VESSEL_SUFFIX = re.compile(r"\s+(HO|호)$", re.IGNORECASE)

# 매칭 창 밖이라도 인접 항차로 볼 최대 거리. 실측 최대 체류(≈3.4일)를
# 넉넉히 덮는다(design doc §3.2).
_ADJACENT_WINDOW = timedelta(days=7)


def vessel_key(name: str) -> str:
    """B/L·관제 기록 양쪽에서 같은 규칙으로 선명을 정규화한다."""
    if not name:
        return ""
    cleaned = _VOYAGE_SUFFIX.sub("", name)
    cleaned = _VESSEL_PREFIX.sub("", cleaned)
    cleaned = _VESSEL_SUFFIX.sub("", cleaned)
    return normalize_key(cleaned)


def _pick_voyage(voyages: List[Voyage], target: Optional[datetime]) -> Optional[Voyage]:
    """날짜로 항차를 고른다. 창 안에 들면 그것, 아니면 7일 이내 최근접."""
    complete = [v for v in voyages if v.arrival and v.departure]
    if not complete:
        return None
    if target is None:
        # 기준일이 없으면 가장 최근 항차로 본다 — 그래야 룰이 최소한
        # 무엇과 대조했는지는 답할 수 있다.
        return complete[-1]

    for voyage in complete:
        if voyage.arrival.occurred_at <= target <= voyage.departure.occurred_at:
            return voyage

    nearest, distance = None, None
    for voyage in complete:
        d = min(
            abs(target - voyage.arrival.occurred_at),
            abs(target - voyage.departure.occurred_at),
        )
        if distance is None or d < distance:
            nearest, distance = voyage, d
    if nearest is not None and distance is not None and distance <= _ADJACENT_WINDOW:
        return nearest
    return None


def match_vessel(
    by_call_sign: Dict[str, List[Voyage]],
    *,
    call_sign: Optional[str] = None,
    vessel_name: Optional[str] = None,
    target_date: Optional[datetime] = None,
) -> VesselMatch:
    """B/L 필드로 관제 기록에서 선박·항차를 찾는다.

    콜사인이 있으면 그것만 쓴다(폴백 순서 1). 없으면 선명 정규화 키로
    대조한다(폴백 순서 2). 동명이선(콜사인 후보 ≥2)이면 어느 쪽도 고르지
    않는다 — 틀린 배로 판정하는 것보다 판정하지 않는 편이 낫다.
    """
    if call_sign:
        voyages = by_call_sign.get(call_sign)
        if not voyages:
            return VesselMatch(
                matched=False,
                strategy="call_sign",
                reason="해당 콜사인의 울산항 관제 기록이 없습니다",
                call_sign=call_sign,
                vessel_name=vessel_name,
            )
        voyage = _pick_voyage(voyages, target_date)
        if voyage is None:
            return VesselMatch(
                matched=False,
                strategy="call_sign",
                reason="기준일과 맞는 항차를 찾지 못했습니다",
                call_sign=call_sign,
                vessel_name=vessel_name,
            )
        return VesselMatch(
            matched=True,
            strategy="call_sign",
            call_sign=call_sign,
            vessel_name=vessel_name,
            voyage=voyage,
        )

    key = vessel_key(vessel_name or "")
    if not key:
        return VesselMatch(
            matched=False,
            strategy="none",
            reason="선명이 없어 매칭할 수 없습니다",
            vessel_name=vessel_name,
        )

    candidates = [
        cs
        for cs, voyages in by_call_sign.items()
        if voyages
        and (
            vessel_key(voyages[0].vessel_name_en) == key
            or vessel_key(voyages[0].vessel_name_kr) == key
        )
    ]

    if not candidates:
        return VesselMatch(
            matched=False,
            strategy="vessel_name",
            reason="울산항 관제 기록에서 이 선박을 찾지 못했습니다",
            vessel_name=vessel_name,
        )
    if len(candidates) > 1:
        return VesselMatch(
            matched=False,
            strategy="vessel_name",
            reason="동명이선 — 콜사인 없이는 선박을 특정할 수 없습니다",
            vessel_name=vessel_name,
            candidates=sorted(candidates),
        )

    matched_call_sign = candidates[0]
    voyage = _pick_voyage(by_call_sign[matched_call_sign], target_date)
    if voyage is None:
        return VesselMatch(
            matched=False,
            strategy="vessel_name",
            reason="기준일과 맞는 항차를 찾지 못했습니다",
            call_sign=matched_call_sign,
            vessel_name=vessel_name,
        )
    return VesselMatch(
        matched=True,
        strategy="vessel_name",
        call_sign=matched_call_sign,
        vessel_name=vessel_name,
        voyage=voyage,
    )


__all__ = ["match_vessel", "vessel_key"]
