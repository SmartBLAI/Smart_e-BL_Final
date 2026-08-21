"""F6 — RealityEngine 룰 6건."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from reality.engine import RealityEngine
from reality.adapter import FixtureSource


@pytest.fixture
def engine():
    return RealityEngine(source=FixtureSource())


def _violation_ids(verdict):
    return {v.rule_id for v in verdict.violations}


def _skipped_ids(verdict):
    return {s.rule_id for s in verdict.skipped}


# ── C-ROUTE-01 ───────────────────────────────────────────────────

def test_ROUTE01_울산_선언했는데_매칭_실패면_위반(engine, vts_records):
    records = vts_records([
        ("3", datetime(2025, 1, 1, 14, 0)),
        ("9", datetime(2025, 1, 2, 0, 0)),
    ], vessel_en="OSUNG")
    bl = {"vessel": "NOT-A-MATCH", "port_of_loading": "ULSAN", "port_of_discharge": "LA"}
    _, verdict = engine.check(bl, records)
    assert "C-ROUTE-01" in _violation_ids(verdict)


def test_ROUTE01_울산_선언_안했으면_평가불가(engine, vts_records):
    records = vts_records([
        ("3", datetime(2025, 1, 1, 14, 0)),
        ("9", datetime(2025, 1, 2, 0, 0)),
    ], vessel_en="OSUNG")
    bl = {"vessel": "OSUNG", "port_of_loading": "BUSAN", "port_of_discharge": "LA"}
    _, verdict = engine.check(bl, records)
    assert "C-ROUTE-01" in _skipped_ids(verdict)
    assert "C-ROUTE-01" not in _violation_ids(verdict)


# ── C-VSL-01 ─────────────────────────────────────────────────────

def test_VSL01_동명이선이면_경고(engine, vts_records):
    events = [
        ("3", datetime(2025, 1, 1, 14, 0)),
        ("9", datetime(2025, 1, 2, 0, 0)),
    ]
    records = vts_records(events, call_sign="AAA", vessel_en="SAME") + vts_records(
        events, call_sign="BBB", vessel_en="SAME"
    )
    bl = {"vessel": "SAME", "port_of_loading": "ULSAN", "port_of_discharge": "LA"}
    _, verdict = engine.check(bl, records)
    assert "C-VSL-01" in _violation_ids(verdict)


def test_VSL01_콜사인으로_직접_매칭하면_평가불가(engine, vts_records):
    records = vts_records([
        ("3", datetime(2025, 1, 1, 14, 0)),
        ("9", datetime(2025, 1, 2, 0, 0)),
    ])
    bl = {"vessel": "무관", "port_of_loading": "ULSAN"}
    _, verdict = engine.check(bl, records, call_sign="150040")
    assert "C-VSL-01" in _skipped_ids(verdict)


# ── C-TIME-01 / C-TIME-02 ────────────────────────────────────────

def test_TIME01_적재일이_입항일보다_앞서면_위반(engine, vts_records):
    records = vts_records([
        ("3", datetime(2025, 1, 1, 14, 0)),
        ("9", datetime(2025, 1, 2, 0, 0)),
    ])
    bl = {"vessel": "TESTSHIP", "on_board_date": "2024-12-30"}
    _, verdict = engine.check(bl, records, call_sign="150040")
    assert "C-TIME-01" in _violation_ids(verdict)


def test_TIME02_적재일이_출항일보다_늦으면_위반(engine, vts_records):
    records = vts_records([
        ("3", datetime(2025, 1, 1, 14, 0)),
        ("9", datetime(2025, 1, 2, 0, 0)),
    ])
    bl = {"vessel": "TESTSHIP", "on_board_date": "2025-01-05"}
    _, verdict = engine.check(bl, records, call_sign="150040", as_of=datetime(2025, 1, 1, 20, 0))
    assert "C-TIME-02" in _violation_ids(verdict)


def test_TIME01_TIME02_정상범위면_통과(engine, vts_records):
    records = vts_records([
        ("3", datetime(2025, 1, 1, 14, 0)),
        ("9", datetime(2025, 1, 2, 0, 0)),
    ])
    bl = {"vessel": "TESTSHIP", "on_board_date": "2025-01-01"}
    _, verdict = engine.check(bl, records, call_sign="150040")
    assert "C-TIME-01" not in _violation_ids(verdict)
    assert "C-TIME-02" not in _violation_ids(verdict)


# ── C-TIME-04 ────────────────────────────────────────────────────

def test_TIME04_체류시간_이상치는_위반(engine, vts_records):
    records = []
    base = datetime(2025, 1, 1)
    # 정상 항차 5건 — 체류 10시간.
    for i in range(5):
        start = base + timedelta(days=i * 3)
        records += vts_records(
            [("3", start), ("9", start + timedelta(hours=10))],
            voyage_no=f"{i + 1:03d}",
        )
    # 이상 항차 1건 — 체류 200시간.
    outlier_start = base + timedelta(days=30)
    records += vts_records(
        [("3", outlier_start), ("9", outlier_start + timedelta(hours=200))],
        voyage_no="006",
    )

    bl = {"vessel": "TESTSHIP", "on_board_date": outlier_start.strftime("%Y-%m-%d")}
    _, verdict = engine.check(
        bl, records, call_sign="150040", as_of=outlier_start + timedelta(hours=1)
    )
    assert "C-TIME-04" in _violation_ids(verdict)


def test_TIME04_표본_부족이면_평가불가(engine, vts_records):
    records = vts_records([
        ("3", datetime(2025, 1, 1, 14, 0)),
        ("9", datetime(2025, 1, 2, 0, 0)),
    ])
    bl = {"vessel": "TESTSHIP"}
    _, verdict = engine.check(bl, records, call_sign="150040")
    assert "C-TIME-04" in _skipped_ids(verdict)


# ── C-STAT-01 ────────────────────────────────────────────────────

def test_STAT01_상태_문법_위반을_잡는다(engine, vts_records):
    # 정박지(WAM)로 입항했는데(묘박 상태) 바로 이안(UNBERTH, 계류 해제)한다
    # — 계류한 적이 없으니 문법 위반이다.
    records = vts_records([
        ("3", datetime(2025, 1, 1, 14, 0), "WAM", "정박지 01"),
        ("5", datetime(2025, 1, 1, 20, 0)),
        ("9", datetime(2025, 1, 2, 0, 0)),
    ])
    bl = {"vessel": "TESTSHIP"}
    _, verdict = engine.check(bl, records, call_sign="150040")
    assert "C-STAT-01" in _violation_ids(verdict)


def test_STAT01_정상_순서는_통과(engine, vts_records):
    records = vts_records([
        ("3", datetime(2025, 1, 1, 14, 0)),
        ("4", datetime(2025, 1, 1, 15, 0)),
        ("5", datetime(2025, 1, 1, 20, 0)),
        ("9", datetime(2025, 1, 2, 0, 0)),
    ])
    bl = {"vessel": "TESTSHIP"}
    _, verdict = engine.check(bl, records, call_sign="150040")
    assert "C-STAT-01" not in _violation_ids(verdict)


# ── 실 데이터 회귀 ───────────────────────────────────────────────

def test_실_샘플_115개_항차_전체가_조용하다(engine):
    """오탐률 측정의 기준선. 실측 데이터에 룰이 하나도 울리면 안 된다."""
    path = Path(__file__).resolve().parents[1] / "reality" / "fixtures" / "ulsan_vts_2025.json"
    records = json.loads(path.read_text(encoding="utf-8"))

    bl = {
        "vessel": "OSUNG",
        "port_of_loading": "ULSAN",
        "port_of_discharge": "SINGAPORE",
        "on_board_date": "2025-01-01",
    }
    _, verdict = engine.check(bl, records, call_sign="150040", as_of=datetime(2025, 1, 1, 20, 0))
    assert verdict.violations == []
