"""F6 주기 점검: 울산 + 기간 안 선적만 현실 대조 대상. ai-service(httpx)는 목."""

import uuid
from datetime import date, timedelta

from sqlalchemy import func, select

from smart_e_bl.db import sync_session
from smart_e_bl.models import RealityRun
from smart_e_bl.worker.main import poll_reality

from .test_reality import fake_ai  # noqa: F401  (fixture)


async def _shipment(client, pol: str, on_board: date) -> str:
    sid = (await client.post("/api/v1/shipments")).json()["shipment_id"]
    doc = (await client.post(f"/api/v1/shipments/{sid}/documents",
                             files={"file": ("t.png", b"x", "image/png")})).json()["document_id"]
    fields = [{"field_name": n, "value": v, "confidence": 0.9, "grade": "CONFIRMED",
               "extractor": "rule", "bbox": [0.1, 0.1, 0.5, 0.2]}
              for n, v in (("vessel", "M/V OSUNG HO"), ("on_board_date", on_board.isoformat()),
                           ("port_of_loading", pol), ("bl_no", f"BL-{uuid.uuid4().hex[:8]}"))]
    res = await client.put(f"/api/v1/shipments/{sid}/fields", json={"document_id": doc, "page": 1, "fields": fields})
    assert res.status_code == 200
    return sid


def _runs(sid: str) -> int:
    with sync_session() as s:
        return s.scalar(select(func.count()).select_from(RealityRun).where(RealityRun.shipment_id == uuid.UUID(sid)))


async def test_poll_checks_only_eligible(client, fake_ai):  # noqa: F811
    today = date.today()
    ok = await _shipment(client, "ULSAN, KOREA", today - timedelta(days=3))
    old = await _shipment(client, "ULSAN, KOREA", today - timedelta(days=400))
    other = await _shipment(client, "BUSAN", today - timedelta(days=3))
    import asyncio
    await asyncio.to_thread(poll_reality)  # asyncio.run 은 실행 중인 루프 밖 스레드에서만 가능
    assert (_runs(ok), _runs(old), _runs(other)) == (1, 0, 0)
