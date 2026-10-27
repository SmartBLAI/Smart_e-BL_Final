"""
F6 현실 대조 검사 함수 레지스트리.

`ruleEngine.checks` 의 `CheckOutcome`·`passed`·`violated`·`not_evaluated` 를
그대로 쓴다 — 평가불가를 통과로 뭉개지 않는 3상태 규약을 F3·F6 이 공유해야
하기 때문이다(design doc §5).

각 함수는 `(bl, ctx, rule) -> CheckOutcome` 이다. `ctx` 는 `RealityContext`
— 매칭 결과와, 체류시간 분포 계산에 쓰는 같은 선박의 전 항차 목록을 담는다.
매칭 자체가 안 됐으면(`ctx.match.matched is False`) 대부분의 검사는
`not_evaluated` 다 — 못 찾은 것이지 위반이 아니다(design doc §3.2).

예외 하나: `port_matches_source`(C-ROUTE-01) 는 매칭 실패도 평가 대상이다.
이 검사의 존재 이유 자체가 "서류는 울산항을 언급하는데 관제 기록엔 없다"는
경우를 잡는 것이기 때문이다.
"""

from __future__ import annotations

import statistics
from typing import Callable, Dict

from f3_rules.checks import CheckOutcome, field_value, not_evaluated, parse_date, passed, violated

from .types import RealityContext, Voyage

# 서류가 울산항을 언급하는지 판별하는 별칭. UN/LOCODE(KRUSN)까지 포함한다.
_ULSAN_ALIASES = ("울산", "ULSAN", "KRUSN")

# C-TIME-04 최소 표본. 이보다 적으면 사분위수가 의미 없다.
_MIN_STAY_SAMPLE = 4


def _mentions_ulsan(value) -> bool:
    if not value:
        return False
    upper = str(value).upper()
    return any(alias in upper for alias in _ULSAN_ALIASES)


def _stay_hours(voyage: Voyage) -> float:
    delta = voyage.departure.occurred_at - voyage.arrival.occurred_at
    return delta.total_seconds() / 3600.0


def port_matches_source(bl, ctx: RealityContext, rule: dict) -> CheckOutcome:
    pol = field_value(bl, "port_of_loading")
    pod = field_value(bl, "port_of_discharge")
    if not _mentions_ulsan(pol) and not _mentions_ulsan(pod):
        return not_evaluated("서류의 적재항/양륙항이 울산항을 언급하지 않습니다(커버리지 밖)")
    if ctx.match.matched:
        return passed(port_of_loading=pol, port_of_discharge=pod)
    return violated(
        detail=f"매칭 실패 사유: {ctx.match.reason}",
        port_of_loading=pol,
        port_of_discharge=pod,
    )


def vessel_uniquely_matched(bl, ctx: RealityContext, rule: dict) -> CheckOutcome:
    match = ctx.match
    if match.strategy != "vessel_name":
        return not_evaluated("콜사인으로 직접 매칭되어 동명이선 위험이 없습니다")
    if match.candidates:
        return violated(
            detail=f"콜사인 후보 {len(match.candidates)}건: {', '.join(match.candidates)}",
            vessel_name=match.vessel_name,
        )
    if match.matched:
        return passed(vessel_name=match.vessel_name, call_sign=match.call_sign)
    return not_evaluated("선명으로 후보를 찾지 못했습니다")


def on_board_not_before_arrival(bl, ctx: RealityContext, rule: dict) -> CheckOutcome:
    voyage = ctx.match.voyage
    if voyage is None:
        return not_evaluated(ctx.match.reason or "매칭된 항차가 없습니다")
    raw = field_value(bl, "on_board_date")
    if not raw:
        return not_evaluated("서류에 본선적재일이 없습니다")
    parsed = parse_date(raw)
    if parsed is None:
        return not_evaluated(f"본선적재일을 해석할 수 없습니다: {raw}")
    arrival = voyage.arrival.occurred_at
    if parsed.date() < arrival.date():
        return violated(
            detail=f"본선적재일({parsed.date()}) < 실제 입항일({arrival.date()})",
            on_board_date=raw,
            arrival=arrival.isoformat(),
        )
    return passed(on_board_date=raw, arrival=arrival.isoformat())


def on_board_not_after_departure(bl, ctx: RealityContext, rule: dict) -> CheckOutcome:
    voyage = ctx.match.voyage
    if voyage is None:
        return not_evaluated(ctx.match.reason or "매칭된 항차가 없습니다")
    raw = field_value(bl, "on_board_date")
    if not raw:
        return not_evaluated("서류에 본선적재일이 없습니다")
    parsed = parse_date(raw)
    if parsed is None:
        return not_evaluated(f"본선적재일을 해석할 수 없습니다: {raw}")
    departure = voyage.departure.occurred_at
    if parsed.date() > departure.date():
        return violated(
            detail=f"본선적재일({parsed.date()}) > 실제 출항일({departure.date()})",
            on_board_date=raw,
            departure=departure.isoformat(),
        )
    return passed(on_board_date=raw, departure=departure.isoformat())


def stay_duration_outlier(bl, ctx: RealityContext, rule: dict) -> CheckOutcome:
    voyage = ctx.match.voyage
    if voyage is None:
        return not_evaluated(ctx.match.reason or "매칭된 항차가 없습니다")
    population = [v for v in ctx.population if v.arrival and v.departure]
    if len(population) < _MIN_STAY_SAMPLE:
        return not_evaluated(f"체류시간 표본이 부족합니다(n={len(population)})")

    durations = sorted(_stay_hours(v) for v in population)
    q1, _, q3 = statistics.quantiles(durations, n=4)
    iqr = q3 - q1
    threshold = q3 + 1.5 * iqr
    current = _stay_hours(voyage)
    if current > threshold:
        return violated(
            detail=f"체류 {current:.1f}시간 > 상한 {threshold:.1f}시간(Q3+1.5·IQR, n={len(population)})",
            stay_hours=f"{current:.1f}",
            threshold_hours=f"{threshold:.1f}",
        )
    return passed(stay_hours=f"{current:.1f}", threshold_hours=f"{threshold:.1f}")


def event_sequence_valid(bl, ctx: RealityContext, rule: dict) -> CheckOutcome:
    voyage = ctx.match.voyage
    if voyage is None:
        return not_evaluated(ctx.match.reason or "매칭된 항차가 없습니다")

    ok, reason = _validate_sequence(voyage)
    if not ok:
        return violated(detail=reason, voyage=voyage.voyage_no)
    return passed(voyage=voyage.voyage_no)


def _validate_sequence(voyage: Voyage) -> tuple[bool, str]:
    events = voyage.events
    if not events:
        return False, "이벤트가 없습니다"
    if events[0].event_type != "ARRIVAL":
        return False, "항차가 입항으로 시작하지 않습니다"
    if events[-1].event_type != "DEPARTURE":
        return False, "항차가 출항으로 끝나지 않습니다"
    for prev, curr in zip(events, events[1:]):
        if curr.occurred_at < prev.occurred_at:
            return False, "이벤트 시각이 comCnt 순서와 어긋납니다"
    unknown_codes = sorted({e.raw_code for e in events if e.event_type == "UNKNOWN"})
    if unknown_codes:
        return False, f"알 수 없는 이벤트 코드: {', '.join(unknown_codes)}"

    state = None  # "BERTHED" | "ANCHORED" | None
    for e in events:
        if e.event_type == "ARRIVAL":
            state = "ANCHORED" if e.is_anchorage else "BERTHED"
        elif e.event_type in ("BERTH", "SHIFT_BERTH"):
            state = "BERTHED"
        elif e.event_type == "ANCHOR":
            state = "ANCHORED"
        elif e.event_type == "UNBERTH":
            if state != "BERTHED":
                return False, "이안 전에 계류 상태가 아니었습니다"
            state = None
        elif e.event_type == "WEIGH_ANCHOR":
            if state != "ANCHORED":
                return False, "양묘 전에 묘박 상태가 아니었습니다"
            state = None
    return True, ""


CheckFn = Callable[[object, RealityContext, dict], CheckOutcome]

REGISTRY: Dict[str, CheckFn] = {
    "port_matches_source": port_matches_source,
    "vessel_uniquely_matched": vessel_uniquely_matched,
    "on_board_not_before_arrival": on_board_not_before_arrival,
    "on_board_not_after_departure": on_board_not_after_departure,
    "stay_duration_outlier": stay_duration_outlier,
    "event_sequence_valid": event_sequence_valid,
}

__all__ = ["REGISTRY"]
