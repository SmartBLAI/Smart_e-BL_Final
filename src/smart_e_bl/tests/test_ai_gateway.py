"""AI 프록시: 허용 op 통과+감사 기록, 미지원 op 404, 업스트림 5xx -> 502. httpx 는 목."""

from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import text

from smart_e_bl.api import ai_gateway
from smart_e_bl.config import settings
from smart_e_bl.db import AsyncSessionLocal


@pytest.fixture
def fake_ai(monkeypatch):
    monkeypatch.setattr(settings, "ai_service_url", "http://ai.test")
    monkeypatch.setattr(settings, "ai_internal_token", "tok")
    state = {"status": 200, "calls": []}

    class FakeClient:
        def __init__(self, **_): ...
        async def __aenter__(self): return self
        async def __aexit__(self, *_): ...
        async def post(self, url, content, headers):
            if not isinstance(content, bytes):  # 게이트웨이는 본문을 스트리밍으로 넘긴다
                content = b"".join([c async for c in content])
            state["calls"].append((url, headers, content))
            return httpx.Response(state["status"], content=b'{"ok":true}')

    monkeypatch.setattr(ai_gateway, "httpx", SimpleNamespace(AsyncClient=FakeClient, RequestError=httpx.RequestError))
    return state


async def _shipment(client) -> str:
    return (await client.post("/api/v1/shipments")).json()["shipment_id"]


async def test_allowed_operation_proxied_and_audited(client, fake_ai):
    sid = await _shipment(client)
    res = await client.post(f"/api/v1/shipments/{sid}/ai/reality/check", json={"a": 1})
    assert res.status_code == 200 and res.json() == {"ok": True}
    assert res.headers["cache-control"] == "no-store"
    url, headers, _ = fake_ai["calls"][0]
    assert url == "http://ai.test/reality/check" and headers["X-Internal-Token"] == "tok"
    async with AsyncSessionLocal() as s:
        n = await s.scalar(text("SELECT count(*) FROM audit_log WHERE shipment_id = :s "
                                "AND action = 'AI_REALITY_CHECK'"), {"s": sid})
    assert n == 1


async def test_unknown_operation_404(client, fake_ai):
    sid = await _shipment(client)
    assert (await client.post(f"/api/v1/shipments/{sid}/ai/rm-rf", json={})).status_code == 404
    assert fake_ai["calls"] == []


async def test_upstream_500_becomes_502(client, fake_ai):
    sid = await _shipment(client)
    fake_ai["status"] = 500
    assert (await client.post(f"/api/v1/shipments/{sid}/ai/verify", json={})).status_code == 502


async def test_upstream_auth_errors_become_502_but_client_errors_pass(client, fake_ai):
    sid = await _shipment(client)
    for upstream, expected in ((401, 502), (403, 502), (400, 400), (404, 404), (413, 413), (422, 422)):
        fake_ai["status"] = upstream
        assert (await client.post(f"/api/v1/shipments/{sid}/ai/verify", json={})).status_code == expected


async def test_tenant_route_forwards_multipart_byte_identical_and_audits(client, fake_ai):
    body = b"--XX\r\nContent-Disposition: form-data; name=file; filename=a.pdf\r\n\r\n\x00\xff%PDF\r\n--XX--\r\n"
    ct = "multipart/form-data; boundary=XX"
    res = await client.post("/api/v1/ai/extract/pdf?page=0", content=body, headers={"content-type": ct})
    assert res.status_code == 200 and res.headers["cache-control"] == "no-store"
    url, headers, sent = fake_ai["calls"][0]
    assert url == "http://ai.test/extract/pdf?page=0" and sent == body
    assert headers["Content-Type"] == ct and headers["X-Internal-Token"] == "tok"
    async with AsyncSessionLocal() as s:
        n = await s.scalar(text("SELECT count(*) FROM audit_log WHERE action = 'AI_EXTRACT_PDF' "
                                "AND entity_type = 'tenant' AND shipment_id IS NULL"))
    assert n >= 1


async def test_tenant_route_disallowed_op_404_and_get_not_routed(client, fake_ai):
    assert (await client.post("/api/v1/ai/report/share", json={})).status_code == 404
    assert (await client.post("/api/v1/ai/../etc", json={})).status_code in (404, 405)
    assert (await client.get("/api/v1/ai/glossary")).status_code in (404, 405)
    assert fake_ai["calls"] == []



async def test_tenant_route_oversize_stream_413_without_reading_everything(client, fake_ai):
    limit = settings.max_document_bytes + 1024 * 1024
    chunk, pulled = b"x" * (256 * 1024), 0

    async def body():  # content-length 없는 청크 전송 — 상한을 넘으면 더 읽지 않아야 한다
        nonlocal pulled
        for _ in range(limit // len(chunk) + 200):
            pulled += 1
            yield chunk

    res = await client.post("/api/v1/ai/extract/pdf", content=body(),
                            headers={"content-type": "application/octet-stream"})
    assert res.status_code == 413
    assert pulled <= limit // len(chunk) + 2  # 상한 직후 중단, 나머지 200 청크는 안 읽음
    assert fake_ai["calls"] == []
