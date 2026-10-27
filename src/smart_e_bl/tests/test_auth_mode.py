"""AUTH_MODE 스위치 테스트. DB 없이 돈다 — get_session 은 더미로 갈아끼운다."""

import httpx
import pytest

from smart_e_bl.api.main import app
from smart_e_bl.config import settings
from smart_e_bl.db import get_session


@pytest.fixture
async def anon():
    app.dependency_overrides[get_session] = lambda: None
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_session, None)


async def test_oidc_unconfigured_503(anon, monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "oidc")
    for k in ("oidc_issuer", "oidc_audience", "oidc_jwks_url"):
        monkeypatch.setattr(settings, k, "")
    assert (await anon.get("/api/v1/shipments")).status_code == 503


async def test_oidc_no_token_401(anon, monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "oidc")
    monkeypatch.setattr(settings, "oidc_issuer", "https://idp.test/")
    monkeypatch.setattr(settings, "oidc_audience", "aud")
    monkeypatch.setattr(settings, "oidc_jwks_url", "https://idp.test/jwks")
    assert (await anon.get("/api/v1/shipments")).status_code == 401


async def test_bootstrap_200(anon, monkeypatch):
    class FakeSession:
        async def scalars(self, *_):
            return []

    app.dependency_overrides[get_session] = lambda: FakeSession()
    monkeypatch.setattr(settings, "auth_mode", "bootstrap")
    assert (await anon.get("/api/v1/shipments")).status_code == 200


async def test_tenant_ai_route_requires_auth(anon, monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "oidc")
    for k in ("oidc_issuer", "oidc_audience", "oidc_jwks_url"):
        monkeypatch.setattr(settings, k, "")
    assert (await anon.post("/api/v1/ai/extract", content=b"x")).status_code == 503
    monkeypatch.setattr(settings, "oidc_issuer", "https://idp.test/")
    monkeypatch.setattr(settings, "oidc_audience", "aud")
    monkeypatch.setattr(settings, "oidc_jwks_url", "https://idp.test/jwks")
    assert (await anon.post("/api/v1/ai/extract", content=b"x")).status_code == 401
