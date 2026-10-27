"""F6 — 울산항 관제 레코드 정규화."""

from __future__ import annotations

from datetime import datetime

import pytest

from f6_reality.normalize import NormalizeError, group_voyages, record_to_event


def test_알려진_코드는_이벤트_타입으로_바뀐다(vts_records):
    records = vts_records([("3", datetime(2025, 1, 1, 14, 0))])
    event = record_to_event(records[0])
    assert event.event_type == "ARRIVAL"
    assert event.raw_code == "3"
    assert event.occurred_at == datetime(2025, 1, 1, 14, 0)


def test_모르는_코드는_버리지_않고_UNKNOWN_으로_남는다(vts_records):
    records = vts_records([("99", datetime(2025, 1, 1, 14, 0))])
    event = record_to_event(records[0])
    assert event.event_type == "UNKNOWN"
    assert event.raw_code == "99"


def test_시각을_해석할_수_없으면_예외를_던진다():
    with pytest.raises(NormalizeError):
        record_to_event({"ioprtVtsType": "3", "jobDt": "not-a-date"})


def test_콜사인_연도_항차로_그룹핑되고_comCnt_순으로_정렬된다(vts_records):
    records = vts_records([
        ("9", datetime(2025, 1, 2, 0, 0)),  # comCnt=001 이지만 늦은 시각
        ("3", datetime(2025, 1, 1, 14, 0)),  # comCnt=002 이지만 이른 시각
    ])
    by_call_sign = group_voyages(records)
    voyages = by_call_sign["150040"]
    assert len(voyages) == 1
    voyage = voyages[0]
    # comCnt 순으로 정렬되므로 원본 레코드 순서(입력 순서)가 유지된다.
    assert [e.event_type for e in voyage.events] == ["DEPARTURE", "ARRIVAL"]


def test_콜사인이나_항차번호가_없는_레코드는_건너뛴다(vts_records):
    records = vts_records([("3", datetime(2025, 1, 1, 14, 0))], call_sign="")
    by_call_sign = group_voyages(records)
    assert by_call_sign == {}


def test_실제_샘플_데이터_전체가_예외_없이_정규화된다():
    import json
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "f6_reality" / "fixtures" / "ulsan_vts_2025.json"
    records = json.loads(path.read_text(encoding="utf-8"))
    by_call_sign = group_voyages(records)
    assert "150040" in by_call_sign
    assert len(by_call_sign["150040"]) == 115
