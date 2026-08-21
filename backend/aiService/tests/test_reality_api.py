"""FastAPI 계층 테스트 — F6 `/reality/*` 엔드포인트 계약."""

from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi", reason="FastAPI 미설치 시 건너뜀")
from fastapi.testclient import TestClient  # noqa: E402

from api.main import _call_sign_cache, _resolve_call_sign_cached, app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


class TestHealth:
    def test_현실_대조_카탈로그를_보고한다(self, client):
        body = client.get("/health").json()

        assert "reality_catalog" in body
        assert body["reality_source"] == "fixture"


class TestRealityRules:
    def test_룰_목록에_조문이_실린다(self, client):
        body = client.get("/reality/rules").json()

        assert body["count"] == 6
        assert body["count"] == len(body["rules"])
        assert all(r["source"] for r in body["rules"])


class TestResolveCallSignCache:
    def test_같은_선명은_외부_API를_한_번만_부른다(self, monkeypatch):
        _call_sign_cache.clear()
        calls = []

        def _fake(name):
            calls.append(name)
            return "CACHED123"

        monkeypatch.setattr("api.main.resolve_call_sign", _fake)
        assert _resolve_call_sign_cached("CACHETESTSHIP") == "CACHED123"
        assert _resolve_call_sign_cached("CACHETESTSHIP") == "CACHED123"
        assert calls == ["CACHETESTSHIP"]
        _call_sign_cache.clear()


class TestRealityCheck:
    def test_빈_bl은_400(self, client):
        resp = client.post("/reality/check", json={"bl": {}})
        assert resp.status_code == 400

    def test_매칭_성공하면_200이고_판정이_실린다(self, client):
        resp = client.post(
            "/reality/check",
            json={
                "bl": {
                    "vessel": "OSUNG",
                    "port_of_loading": "ULSAN, KOREA",
                    "port_of_discharge": "SINGAPORE",
                    "on_board_date": "2025-01-01",
                }
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["match"]["matched"] is True
        assert body["match"]["call_sign"] == "150040"
        assert body["verdict"]["evaluated_count"] == 6
        assert body["source"]["adapter"] == "fixture"

    def test_매칭_실패도_200이고_위반이_아니라_평가불가로_남는다(self, client):
        """매칭 실패는 오류가 아니다 — HTTP 는 200, 판정은 not_evaluated 다."""
        resp = client.post(
            "/reality/check",
            json={"bl": {"vessel": "이런 배는 없다", "port_of_loading": "BUSAN"}},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["match"]["matched"] is False
        assert body["verdict"]["violations"] == []
        assert len(body["verdict"]["skipped"]) == 6

    def test_콜사인을_주면_선명보다_우선한다(self, client):
        resp = client.post(
            "/reality/check",
            json={"bl": {"vessel": "엉뚱한 이름"}, "call_sign": "150040"},
        )
        body = resp.json()
        assert body["match"]["matched"] is True
        assert body["match"]["strategy"] == "call_sign"

    def test_events를_직접_주면_그것으로만_대조하고_소스를_안탄다(self, client, vts_records):
        from datetime import datetime

        records = vts_records([
            ("3", datetime(2025, 6, 1, 10, 0)),
            ("9", datetime(2025, 6, 1, 20, 0)),
        ], call_sign="ZZZ99", vessel_en="CUSTOMSHIP")
        resp = client.post(
            "/reality/check",
            json={"bl": {"vessel": "CUSTOMSHIP", "on_board_date": "2025-06-01"}, "events": records},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["source"]["adapter"] == "request"
        assert body["source"]["records"] == 2
        assert body["match"]["matched"] is True
        assert body["match"]["call_sign"] == "ZZZ99"
