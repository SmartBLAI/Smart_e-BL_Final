"""P2-11: baseline 리비전의 downgrade()가 스키마 전체를 지우기 전에
opt-in 가드를 지키는지 확인한다. 실제 DB나 alembic 러너는 건드리지 않는다 —
`alembic.op`을 흉내만 내는 스텁으로 바꿔 끼워 함수 내부 로직만 검증한다.
"""

import importlib.util
from pathlib import Path

import pytest

_MODULE_PATH = (
    Path(__file__).resolve().parents[3] / "migrations" / "versions" / "0001_baseline.py"
)


def _load_baseline():
    spec = importlib.util.spec_from_file_location("baseline_0001", _MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_opt_in_없이_downgrade하면_RuntimeError(monkeypatch):
    module = _load_baseline()
    monkeypatch.delenv("ALEMBIC_ALLOW_SCHEMA_DROP", raising=False)

    with pytest.raises(RuntimeError, match="ALEMBIC_ALLOW_SCHEMA_DROP"):
        module.downgrade()


def test_opt_in하면_스키마를_지운다(monkeypatch):
    module = _load_baseline()
    monkeypatch.setenv("ALEMBIC_ALLOW_SCHEMA_DROP", "1")
    executed = []
    monkeypatch.setattr(module.op, "execute", executed.append)

    module.downgrade()

    assert executed == ["DROP SCHEMA public CASCADE", "CREATE SCHEMA public"]
