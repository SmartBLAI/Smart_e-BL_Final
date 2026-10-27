"""db_smoke 의 테넌트 격리 계약을 pytest 로 옮긴 것. outcome·reality·AI 프록시의
타 테넌트 404 는 각자의 테스트 파일이 이미 다룬다 — 여기는 나머지 라우트만.
OIDC 미구성 503 / 토큰 없음 401 은 test_auth_mode.py 가 이미 다룬다."""

import uuid

import pytest
from sqlalchemy import text

from smart_e_bl.api.main import app
from smart_e_bl.api.security import Actor, get_actor
from smart_e_bl.config import settings
from smart_e_bl.db import AsyncSessionLocal


@pytest.fixture
async def tenant_b(client):
    """두 번째 테넌트·사용자를 SQL 로 만들고 끝나면 지운다(client 보다 먼저 정리)."""
    t, u = uuid.uuid4(), uuid.uuid4()
    async with AsyncSessionLocal() as s:
        await s.execute(text("INSERT INTO tenant (id, code, name) VALUES (:t, :c, 'other')"),
                        {"t": t, "c": f"t-{t}"})
        await s.execute(text("INSERT INTO app_user (id, tenant_id, email, name, role) "
                             "VALUES (:u, :t, :e, 'x', 'MEMBER')"),
                        {"u": u, "t": t, "e": f"{u}@x.test"})
        await s.commit()

    def act(role="MEMBER"):
        app.dependency_overrides[get_actor] = lambda: Actor(u, t, role)

    yield act
    app.dependency_overrides.pop(get_actor, None)
    async with AsyncSessionLocal() as s:
        await s.execute(text("DELETE FROM tenant WHERE id = :t"), {"t": t})
        await s.commit()


async def _count(sql: str, **p) -> int:
    async with AsyncSessionLocal() as s:
        return await s.scalar(text(sql), p)


async def test_cross_tenant_routes_404_without_side_effects(client, tenant_b, monkeypatch):
    monkeypatch.setattr(settings, "ingest_on_upload", True)
    sid = (await client.post("/api/v1/shipments")).json()["shipment_id"]
    up = await client.post(f"/api/v1/shipments/{sid}/documents",
                           files={"file": ("a.png", b"tenant-a-bytes", "image/png")})
    assert up.status_code == 201
    doc, job = up.json()["document_id"], up.json()["job_id"]
    assert job
    fields_before = await _count("SELECT count(*) FROM field_value WHERE shipment_id = :s", s=sid)
    docs_before = await _count("SELECT count(*) FROM document WHERE shipment_id = :s", s=sid)
    audit_before = await _count("SELECT count(*) FROM audit_log WHERE shipment_id = :s", s=sid)

    tenant_b()
    base = f"/api/v1/shipments/{sid}"
    # 목록: B 는 A 의 선적을 보지 못한다
    listed = (await client.get("/api/v1/shipments")).json()["shipments"]
    assert sid not in {s["shipment_id"] for s in listed}
    assert (await client.get(base)).status_code == 404
    assert (await client.get(f"{base}/documents/{doc}/file")).status_code == 404
    assert (await client.get(f"/api/v1/jobs/{job}")).status_code == 404
    save = {"document_id": doc, "page": 1, "fields": [{
        "field_name": "bl_no", "value": "HACK", "grade": "CONFIRMED", "extractor": "manual"}]}
    assert (await client.put(f"{base}/fields", json=save)).status_code == 404
    assert (await client.post(f"{base}/verification", json={"verdict": []})).status_code == 404
    assert (await client.post(f"{base}/documents",
                              files={"file": ("b.png", b"intruder", "image/png")})).status_code == 404
    assert (await client.delete(base)).status_code == 404
    assert (await client.post(f"{base}/fields/shipper/confirm")).status_code == 404

    # 부작용 없음: A 의 선적은 그대로, 필드·서류·감사 행이 늘지 않았다
    app.dependency_overrides.pop(get_actor, None)  # 부트스트랩(A)으로 복귀
    assert (await client.get(base)).status_code == 200
    assert (await client.get(f"/api/v1/jobs/{job}")).status_code == 200
    assert await _count("SELECT count(*) FROM field_value WHERE shipment_id = :s", s=sid) == fields_before
    assert await _count("SELECT count(*) FROM document WHERE shipment_id = :s", s=sid) == docs_before
    assert await _count("SELECT count(*) FROM audit_log WHERE shipment_id = :s", s=sid) == audit_before


async def test_viewer_role_cannot_mutate(client, tenant_b):
    tenant_b("VIEWER")
    assert (await client.post("/api/v1/shipments")).status_code == 403
    # 권한 검사가 소유권 검사보다 먼저라 존재하지 않는 선적이어도 403
    ghost = f"/api/v1/shipments/{uuid.uuid4()}"
    assert (await client.delete(ghost)).status_code == 403
    assert (await client.post(f"{ghost}/verification", json={"verdict": []})).status_code == 403
    assert (await client.post(f"{ghost}/fields/shipper/confirm")).status_code == 403
