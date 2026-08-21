"""FastAPI 계층 테스트 — 공유 시크릿 헤더(`X-Internal-Token`) 검사."""

from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi", reason="FastAPI 미설치 시 건너뜀")
from fastapi.testclient import TestClient  # noqa: E402

from api import main as main_module  # noqa: E402
from api.main import app  # noqa: E402


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


class TestInternalToken:
    def test_토큰_미설정이면_검사하지_않는다(self, client, monkeypatch):
        monkeypatch.setattr(main_module, "AI_INTERNAL_TOKEN", "")
        assert client.get("/health").status_code == 200

    def test_토큰_설정시_헤더_없으면_401(self, client, monkeypatch):
        monkeypatch.setattr(main_module, "AI_INTERNAL_TOKEN", "secret123")
        resp = client.get("/reality/rules")
        assert resp.status_code == 401

    def test_토큰_설정시_헤더_틀리면_401(self, client, monkeypatch):
        monkeypatch.setattr(main_module, "AI_INTERNAL_TOKEN", "secret123")
        resp = client.get("/reality/rules", headers={"X-Internal-Token": "wrong"})
        assert resp.status_code == 401

    def test_토큰_설정시_헤더_맞으면_통과한다(self, client, monkeypatch):
        monkeypatch.setattr(main_module, "AI_INTERNAL_TOKEN", "secret123")
        resp = client.get("/reality/rules", headers={"X-Internal-Token": "secret123"})
        assert resp.status_code == 200

    def test_health는_토큰_설정시에도_예외다(self, client, monkeypatch):
        """docker-compose 헬스체크가 토큰 없이 자기 자신을 찌른다."""
        monkeypatch.setattr(main_module, "AI_INTERNAL_TOKEN", "secret123")
        assert client.get("/health").status_code == 200
