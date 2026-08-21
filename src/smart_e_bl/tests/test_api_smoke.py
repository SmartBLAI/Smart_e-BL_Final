"""P1-11: 게이트웨이 upsert·필드코드 왕복·상태 전이가 최소 한 번은
검증되도록 하는 스모크 테스트. 케이스 전부·경계값은 다루지 않는다 —
"업로드→필드 저장→조회" 왕복 하나와, 이번 개선 라운드에서 고친 두 방어
(빈 파일 거부, 다른 선적 소속 document_id 거부)만 확인한다.
"""

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
