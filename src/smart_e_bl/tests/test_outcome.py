"""S10 결과 기록: 왕복·미존재 204·타 테넌트 404."""

import uuid

from sqlalchemy import text

from smart_e_bl.api.main import app
from smart_e_bl.api.security import Actor, get_actor
from smart_e_bl.db import AsyncSessionLocal

BODY = {"decision": "AMENDMENT", "reason": "LC_DISCREPANCY", "memo": "수정 요청", "decided_on": "2026-10-01"}


async def _shipment(client) -> str:
    return (await client.post("/api/v1/shipments")).json()["shipment_id"]


async def test_outcome_roundtrip_and_missing(client):
    sid = await _shipment(client)
    assert (await client.get(f"/api/v1/shipments/{sid}/outcome")).status_code == 204
    put = await client.put(f"/api/v1/shipments/{sid}/outcome", json=BODY)
    assert put.status_code == 200 and put.json()["source"] == "USER_INPUT"
    got = (await client.get(f"/api/v1/shipments/{sid}/outcome")).json()
    assert got["decision"] == "AMENDMENT" and got["decided_on"] == "2026-10-01"
    # 재저장은 upsert
    again = await client.put(f"/api/v1/shipments/{sid}/outcome", json={**BODY, "decision": "APPROVED"})
    assert again.json()["decision"] == "APPROVED"


async def test_outcome_rejects_unknown_decision(client):
    sid = await _shipment(client)
    res = await client.put(f"/api/v1/shipments/{sid}/outcome", json={**BODY, "decision": "MAYBE"})
    assert res.status_code == 422


async def test_outcome_cross_tenant_404(client):
    sid = await _shipment(client)
    tenant_id, user_id = uuid.uuid4(), uuid.uuid4()
    async with AsyncSessionLocal() as s:
        await s.execute(text("INSERT INTO tenant (id, code, name) VALUES (:t, :c, 'other')"),
                        {"t": tenant_id, "c": f"t-{tenant_id}"})
        await s.execute(text("INSERT INTO app_user (id, tenant_id, email, name, role) "
                             "VALUES (:u, :t, :e, 'x', 'MEMBER')"),
                        {"u": user_id, "t": tenant_id, "e": f"{user_id}@x.test"})
        await s.commit()
    app.dependency_overrides[get_actor] = lambda: Actor(user_id, tenant_id, "MEMBER")
    try:
        assert (await client.get(f"/api/v1/shipments/{sid}/outcome")).status_code == 404
        assert (await client.put(f"/api/v1/shipments/{sid}/outcome", json=BODY)).status_code == 404
    finally:
        app.dependency_overrides.pop(get_actor, None)
        async with AsyncSessionLocal() as s:
            await s.execute(text("DELETE FROM tenant WHERE id = :t"), {"t": tenant_id})
            await s.commit()
