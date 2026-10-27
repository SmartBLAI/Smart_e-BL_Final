"""P1-11: 게이트웨이 upsert·필드코드 왕복·상태 전이가 최소 한 번은
검증되도록 하는 스모크 테스트. 케이스 전부·경계값은 다루지 않는다 —
"업로드→필드 저장→조회" 왕복 하나와, 이번 개선 라운드에서 고친 두 방어
(빈 파일 거부, 다른 선적 소속 document_id 거부)만 확인한다.
"""

import uuid

import pytest


async def _create_shipment(client) -> str:
    res = await client.post("/api/v1/shipments")
    assert res.status_code == 201
    return res.json()["shipment_id"]


async def _upload(client, shipment_id: str, content: bytes = b"fake-image-bytes"):
    return await client.post(
        f"/api/v1/shipments/{shipment_id}/documents",
        files={"file": ("test.png", content, "image/png")},
    )


async def test_upload_save_fields_and_read_back(client):
    shipment_id = await _create_shipment(client)

    upload_res = await _upload(client, shipment_id)
    assert upload_res.status_code == 201
    document_id = upload_res.json()["document_id"]

    save_res = await client.put(
        f"/api/v1/shipments/{shipment_id}/fields",
        json={
            "document_id": document_id,
            "page": 1,
            "fields": [
                {
                    "field_name": "shipper",
                    "value": "Test Shipper Co.",
                    "confidence": 0.92,
                    "grade": "CONFIRMED",
                    "extractor": "rule",
                    # bbox는 이미지 너비/높이 대비 정규화 비율(0~1)이다 (field_value_bbox_ck)
                    "bbox": [0.1, 0.1, 0.5, 0.2],
                }
            ],
        },
    )
    assert save_res.status_code == 200
    body = save_res.json()
    assert body["saved"] == 1
    assert body["skipped"] == []

    get_res = await client.get(f"/api/v1/shipments/{shipment_id}")
    assert get_res.status_code == 200
    fields = {f["field_name"]: f for f in get_res.json()["fields"]}
    assert fields["shipper"]["value"] == "Test Shipper Co."


async def test_empty_file_upload_rejected(client):
    shipment_id = await _create_shipment(client)
    res = await _upload(client, shipment_id, content=b"")
    assert res.status_code == 400


async def test_oversized_upload_rejected_without_buffering_it_whole(client, monkeypatch):
    """P2-8: 상한을 낮춰서, 다 읽기 전에 청크 단계에서 끊기는지 확인한다."""
    from smart_e_bl.api import main as main_module

    monkeypatch.setattr(main_module, "_MAX_UPLOAD_BYTES", 10)
    shipment_id = await _create_shipment(client)
    res = await _upload(client, shipment_id, content=b"x" * (1024 * 1024))
    assert res.status_code == 413


async def test_save_fields_clears_stale_normalized_value_when_value_changes(client):
    """값을 고쳤는데 옛 정규화값이 남으면 재조회 때 "표시 단위 <옛값> · 값 변경 아님"이 뜬다."""
    shipment_id = await _create_shipment(client)
    document_id = (await _upload(client, shipment_id)).json()["document_id"]

    def body(value: str, normalized: str | None) -> dict:
        return {
            "document_id": document_id,
            "page": 1,
            "fields": [
                {
                    "field_name": "port_of_loading",
                    "value": value,
                    "normalized_value": normalized,
                    "confidence": 0.92,
                    "grade": "CONFIRMED",
                    "extractor": "rule",
                    "bbox": [0.1, 0.1, 0.5, 0.2],
                }
            ],
        }

    async def stored() -> dict:
        res = await client.get(f"/api/v1/shipments/{shipment_id}")
        return {f["field_name"]: f for f in res.json()["fields"]}["port_of_loading"]

    url = f"/api/v1/shipments/{shipment_id}/fields"
    await client.put(url, json=body("PUSAN, KOREA", "KRPUS"))
    # 값이 그대로면 정규화값 유지
    await client.put(url, json=body("PUSAN, KOREA", "KRPUS"))
    assert (await stored())["normalized_value"] == "KRPUS"
    # 값만 바뀌고 프론트가 옛 정규화값을 되돌려 보내도 비워진다
    await client.put(url, json=body("BUSAN", "KRPUS"))
    row = await stored()
    assert row["value"] == "BUSAN"
    assert row["normalized_value"] is None


@pytest.mark.parametrize(
    "field_overrides",
    [
        {"confidence": 1.5},
        {"confidence": -0.1},
        {"bbox": [0.1, 0.1, 1.5, 0.2]},
        {"bbox": [0.5, 0.1, 0.4, 0.2]},
    ],
)
async def test_save_fields_rejects_out_of_range_field_values(client, field_overrides):
    shipment_id = await _create_shipment(client)
    upload_res = await _upload(client, shipment_id)
    document_id = upload_res.json()["document_id"]

    field = {
        "field_name": "shipper",
        "value": "Test Shipper Co.",
        "confidence": 0.92,
        "grade": "CONFIRMED",
        "extractor": "rule",
        "bbox": [0.1, 0.1, 0.5, 0.2],
        **field_overrides,
    }
    res = await client.put(
        f"/api/v1/shipments/{shipment_id}/fields",
        json={"document_id": document_id, "page": 1, "fields": [field]},
    )
    assert res.status_code == 422


async def test_save_fields_rejects_non_positive_page(client):
    shipment_id = await _create_shipment(client)
    upload_res = await _upload(client, shipment_id)
    document_id = upload_res.json()["document_id"]

    res = await client.put(
        f"/api/v1/shipments/{shipment_id}/fields",
        json={"document_id": document_id, "page": 0, "fields": []},
    )
    assert res.status_code == 422


async def test_create_shipment_rejects_unexpected_body_fields(client):
    """P2-16: 선적 생성은 아직 입력을 안 받는다 — 몸통 파라미터가 없던
    시절엔 title: 12345 같은 아무 값이나 조용히 201로 통과됐다."""
    res = await client.post("/api/v1/shipments", json={"title": 12345})
    assert res.status_code == 422


async def test_delete_shipment_removes_it_and_its_documents(client):
    shipment_id = await _create_shipment(client)
    await _upload(client, shipment_id)

    res = await client.delete(f"/api/v1/shipments/{shipment_id}")
    assert res.status_code == 204

    res = await client.get(f"/api/v1/shipments/{shipment_id}")
    assert res.status_code == 404


async def test_delete_shipment_404_when_missing(client):
    res = await client.delete("/api/v1/shipments/00000000-0000-0000-0000-000000000099")
    assert res.status_code == 404


async def test_save_fields_rejects_document_from_other_shipment(client):
    shipment_a = await _create_shipment(client)
    shipment_b = await _create_shipment(client)

    upload_res = await _upload(client, shipment_a)
    document_id = upload_res.json()["document_id"]

    res = await client.put(
        f"/api/v1/shipments/{shipment_b}/fields",
        json={
            "document_id": document_id,
            "page": 1,
            "fields": [],
        },
    )
    assert res.status_code == 404


async def test_verification_snapshot_round_trips(client):
    """저장한 판정이 상세 조회로 다시 나와야 한다.

    안 나오면 새로고침 시 판정이 사라져 화면이 "검증 완료" 배지 옆에 "아직
    검증을 실행하지 않았습니다"를 같이 띄우고, S3 검증 게이트의 Critical
    조건도 항상 0건으로 읽힌다.
    """
    shipment_id = await _create_shipment(client)

    before = await client.get(f"/api/v1/shipments/{shipment_id}")
    assert before.json()["verdicts"] == []
    assert before.json()["prediction"] is None

    verdict = [{"verdict_id": "D015#0", "rule_id": "D015", "severity": "Critical",
                "result": "VIOLATION", "message": "테스트 위반"}]
    prediction = {"probability": 0.42, "top_factors": [], "deferred_count": 3}
    save_res = await client.post(
        f"/api/v1/shipments/{shipment_id}/verification",
        json={"verdict": verdict, "prediction": prediction, "override_reason": None},
    )
    assert save_res.status_code == 200
    assert save_res.json()["status"] == "VERIFIED"

    after = (await client.get(f"/api/v1/shipments/{shipment_id}")).json()
    assert after["status"] == "VERIFIED"
    assert after["verdicts"] == verdict
    assert after["prediction"] == prediction


async def test_confirm_field_persists_grade(client):
    shipment_id = await _create_shipment(client)
    document_id = (await _upload(client, shipment_id)).json()["document_id"]
    await client.put(
        f"/api/v1/shipments/{shipment_id}/fields",
        json={
            "document_id": document_id,
            "page": 1,
            "fields": [
                {
                    "field_name": "shipper",
                    "value": "Test Shipper Co.",
                    "confidence": 0.5,
                    "grade": "REQUIRED",
                    "extractor": "rule",
                    "bbox": [0.1, 0.1, 0.5, 0.2],
                }
            ],
        },
    )

    async def grade() -> str:
        res = await client.get(f"/api/v1/shipments/{shipment_id}")
        return {f["field_name"]: f for f in res.json()["fields"]}["shipper"]["grade"]

    assert await grade() == "REQUIRED"
    base = f"/api/v1/shipments/{shipment_id}/fields"
    assert (await client.post(f"{base}/shipper/confirm")).status_code == 204
    assert await grade() == "CONFIRMED"
    assert (await client.post(f"{base}/no_such_field/confirm")).status_code == 404


async def test_single_field_put_saves_value_clears_normalized_and_audits(client):
    shipment_id = await _create_shipment(client)
    document_id = (await _upload(client, shipment_id)).json()["document_id"]
    url = f"/api/v1/shipments/{shipment_id}/fields"

    def body(field):
        return {"document_id": document_id, "page": 1, "fields": [field]}

    base = {"field_name": "port_of_loading", "confidence": 0.9, "grade": "CONFIRMED",
            "extractor": "rule", "bbox": [0.1, 0.1, 0.5, 0.2]}
    await client.put(url, json=body({**base, "value": "BUSAN", "normalized_value": "KRPUS"}))
    await client.put(url, json=body({**base, "value": "SHANGHAI", "grade": "REQUIRED"}))

    got = (await client.get(f"/api/v1/shipments/{shipment_id}")).json()["fields"]
    f = {x["field_name"]: x for x in got}["port_of_loading"]
    assert (f["value"], f["normalized_value"], f["grade"]) == ("SHANGHAI", None, "REQUIRED")

    from sqlalchemy import text
    from smart_e_bl.db import AsyncSessionLocal
    async with AsyncSessionLocal() as s:
        n = await s.scalar(
            text("SELECT count(*) FROM audit_log WHERE shipment_id = :s AND action = 'FIELD_EDIT'"),
            {"s": shipment_id},
        )
    assert n == 1


async def test_lc_upload_stores_lc_no_and_expiry_on_shipment(client, monkeypatch):
    # L/C 업로드 때 파싱한 번호·유효기일이 선적 헤더에 저장돼야 목록에 나온다.
    import httpx

    from smart_e_bl.api import main

    async def fake_forward(operation, body, *a, **k):
        assert operation == "lc/mt700"
        return httpx.Response(200, json={"lc": {"lc_no": "LC123", "expiry_date": "2026-12-25"}})

    monkeypatch.setattr(main, "_ai_forward", fake_forward)
    shipment_id = await _create_shipment(client)
    res = await client.post(
        f"/api/v1/shipments/{shipment_id}/documents",
        files={"file": ("lc.txt", b":20:LC123\n", "text/plain")},
        data={"doc_type": "LC_MT700"},
    )
    assert res.status_code == 201

    listed = (await client.get("/api/v1/shipments")).json()["shipments"]
    row = next(s for s in listed if s["shipment_id"] == shipment_id)
    assert (row["lc_no"], row["lc_expiry_date"]) == ("LC123", "2026-12-25")


async def test_overview_equals_per_shipment_and_query_count_is_bounded(client):
    from sqlalchemy import event

    from smart_e_bl.db import async_engine

    ids = [(await client.post("/api/v1/shipments")).json()["shipment_id"] for _ in range(3)]
    doc = (await client.post(f"/api/v1/shipments/{ids[0]}/documents",
                             files={"file": ("t.png", b"x", "image/png")})).json()["document_id"]
    await client.put(f"/api/v1/shipments/{ids[0]}/fields", json={"document_id": doc, "page": 1, "fields": [
        {"field_name": "vessel", "value": "M/V X", "confidence": 0.9, "grade": "CONFIRMED",
         "extractor": "rule", "bbox": [0.1, 0.1, 0.5, 0.2]}]})
    # ids[1] 은 현실 대조 기록(run) 하나만 — 0번은 서류만 있고 대조 없음, 2번은 빈 선적
    from smart_e_bl.db import AsyncSessionLocal
    from smart_e_bl.models import RealityRun, Shipment
    async with AsyncSessionLocal() as s:
        sh = await s.get(Shipment, uuid.UUID(ids[1]))
        s.add(RealityRun(tenant_id=sh.tenant_id, shipment_id=sh.id, adapter="fixture", ok=True,
                         match={"matched": False, "vessel_name": "X"}, verdict={"skipped": []}))
        await s.commit()

    counts = []
    def count(*_): counts.append(1)
    event.listen(async_engine.sync_engine, "before_cursor_execute", count)
    try:
        res = await client.get("/api/v1/shipments/overview")
    finally:
        event.remove(async_engine.sync_engine, "before_cursor_execute", count)
    assert res.status_code == 200
    body = {s["shipment_id"]: s for s in res.json()["shipments"]}
    for sid in ids:
        item = dict(body[sid])
        reality = item.pop("reality")
        assert item == (await client.get(f"/api/v1/shipments/{sid}")).json()
        assert reality == (await client.get(f"/api/v1/shipments/{sid}/reality")).json()
    # 선적 수와 무관한 상수 개 (actor 조회 + count + list + 상세 3 + 현실 3 + 여유)
    assert len(counts) <= 12


async def test_shipments_list_pagination(client):
    ids = [(await client.post("/api/v1/shipments")).json()["shipment_id"] for _ in range(3)]
    full = (await client.get("/api/v1/shipments")).json()
    assert full["total"] == len(full["shipments"]) and full["next"] is None
    p1 = (await client.get("/api/v1/shipments?limit=2")).json()
    assert len(p1["shipments"]) == 2 and p1["next"] == 2 and p1["total"] == full["total"]
    p2 = (await client.get(f"/api/v1/shipments?limit=2&offset={p1['next']}")).json()
    assert [s["shipment_id"] for s in p1["shipments"] + p2["shipments"]][:2 + len(p2["shipments"])] \
        == [s["shipment_id"] for s in full["shipments"]][:2 + len(p2["shipments"])]
    assert set(ids) <= {s["shipment_id"] for s in full["shipments"]}


async def test_concurrent_same_bl_no_does_not_500(client):
    import asyncio

    bl = f"BL-{uuid.uuid4().hex[:8]}"
    ids = [(await client.post("/api/v1/shipments")).json()["shipment_id"] for _ in range(4)]

    async def save(sid):
        doc = (await client.post(f"/api/v1/shipments/{sid}/documents",
                                 files={"file": (f"{sid}.png", b"x", "image/png")})).json()["document_id"]
        return await client.put(f"/api/v1/shipments/{sid}/fields", json={
            "document_id": doc, "page": 1, "fields": [{
                "field_name": "bl_no", "value": bl, "confidence": 0.9, "grade": "CONFIRMED",
                "extractor": "rule", "bbox": [0.1, 0.1, 0.5, 0.2]}]})

    results = await asyncio.gather(*(save(i) for i in ids))
    assert [r.status_code for r in results] == [200] * 4
    owners = [s for s in (await client.get("/api/v1/shipments")).json()["shipments"] if s["bl_no"] == bl]
    assert len(owners) == 1  # 나머지는 번호 표시만 건너뛴다(순차 경로와 동일)
