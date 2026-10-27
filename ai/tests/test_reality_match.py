"""F6 — B/L ↔ 울산항 관제 기록 매칭."""

from __future__ import annotations

from datetime import datetime

from f6_reality.matcher import match_vessel, vessel_key
from f6_reality.normalize import group_voyages


def _voyages(vts_records, **overrides):
    events = [
        ("3", datetime(2025, 1, 1, 14, 0)),
        ("9", datetime(2025, 1, 2, 0, 0)),
    ]
    records = vts_records(events, **overrides)
    return group_voyages(records)


def test_콜사인이_있으면_그것만_쓴다(vts_records):
    by_call_sign = _voyages(vts_records)
    match = match_vessel(by_call_sign, call_sign="150040")
    assert match.matched
    assert match.strategy == "call_sign"
    assert match.voyage.voyage_no == "001"


def test_없는_콜사인은_매칭_실패다(vts_records):
    by_call_sign = _voyages(vts_records)
    match = match_vessel(by_call_sign, call_sign="999999")
    assert not match.matched
    assert match.strategy == "call_sign"


def test_선명_정규화_후_대조된다(vts_records):
    by_call_sign = _voyages(vts_records, vessel_en="OSUNG")
    match = match_vessel(by_call_sign, vessel_name="M/V OSUNG V.12")
    assert match.matched
    assert match.strategy == "vessel_name"
    assert match.call_sign == "150040"


def test_동명이선이면_후보를_남기고_매칭하지_않는다(vts_records):
    events = [
        ("3", datetime(2025, 1, 1, 14, 0)),
        ("9", datetime(2025, 1, 2, 0, 0)),
    ]
    records_a = vts_records(events, call_sign="AAA", vessel_en="SAME NAME")
    records_b = vts_records(events, call_sign="BBB", vessel_en="SAME NAME")
    by_call_sign = group_voyages(records_a + records_b)

    match = match_vessel(by_call_sign, vessel_name="SAME NAME")
    assert not match.matched
    assert match.strategy == "vessel_name"
    assert sorted(match.candidates) == ["AAA", "BBB"]


def test_선명도_콜사인도_없으면_매칭하지_않는다(vts_records):
    by_call_sign = _voyages(vts_records)
    match = match_vessel(by_call_sign, vessel_name="")
    assert not match.matched
    assert match.strategy == "none"


def test_기준일이_항차_창_안에_있으면_해당_항차를_고른다(vts_records):
    by_call_sign = _voyages(vts_records)
    match = match_vessel(
        by_call_sign, call_sign="150040", target_date=datetime(2025, 1, 1, 20, 0)
    )
    assert match.matched
    assert match.voyage.voyage_no == "001"


def test_기준일이_7일_넘게_벗어나면_매칭하지_않는다(vts_records):
    by_call_sign = _voyages(vts_records)
    match = match_vessel(
        by_call_sign, call_sign="150040", target_date=datetime(2025, 2, 1)
    )
    assert not match.matched


def test_vessel_key는_접두_접미_표기를_정리한다():
    assert vessel_key("M/V OSUNG") == vessel_key("OSUNG")
    assert vessel_key("MSC BIANCA V.112") == vessel_key("MSC BIANCA")
    assert vessel_key("OSUNG HO") == vessel_key("OSUNG")
    # "선명 / 항차" 병기
    assert vessel_key("M/V OSUNG / 2608E") == vessel_key("OSUNG")
    assert vessel_key("HMM ALGECIRAS/2608E") == vessel_key("HMM ALGECIRAS")
    assert vessel_key("OSUNG / V.112") == vessel_key("OSUNG")
    assert vessel_key("OSUNG / VOY 0042W") == vessel_key("OSUNG")
