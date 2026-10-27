"""F6 현실 대조 영속화: 스냅샷·경보 중복 제거·확인·화이트리스트. ai-service(httpx)는 목."""

import json
import uuid
from datetime import date
from types import SimpleNamespace

import httpx
import pytest

from smart_e_bl.api import ai_gateway
from smart_e_bl.api.main import app
from smart_e_bl.api.security import Actor, get_actor
from smart_e_bl.config import settings

VOYAGE = {"call_sign": "150040", "year": "2025", "voyage_no": "001"}
VIOLATING = {
    "shipment_id": None,
    "source": {"adapter": "fixture", "port": "울산", "records": 3, "fetched_at": "2026-01-01T00:00:00"},
    "match": {"matched": True, "strategy": "vessel_name", "reason": "", "call_sign": "150040",
              "vessel_name": "OSUNG HO", "voyage": "001", "window": None, "candidates": []},
    "verdict": {
        "catalog": {"label": "v1+test"}, "evaluated_count": 6,
        "violations": [{"rule_id": "C-TIME-01", "severity": "critical", "title": "적재일이 입항보다 앞섬",
                        "message": "본선적재일이 입항일보다 앞섭니다", "fields": ["on_board_date"],
                        "observed": {"on_board_date": "2024-12-30"}}],
        "skipped": [{"rule_id": "C-VSL-01", "title": "동명이선", "reason": "후보 없음"}],
    },
    "events": [
        {"event_type": "ARRIVAL", "raw_code": "3", "occurred_at": "2025-01-01T14:01:00", "seq": 1,
         "facility_code": "WAM", "facility_name": "정박지 02"},
        {"event_type": "ANCHOR", "raw_code": "7", "occurred_at": "2025-01-01T15:00:00", "seq": 2,
         "facility_code": "WAM", "facility_name": "정박지 02"},
        {"event_type": "DEPARTURE", "raw_code": "9", "occurred_at": "2025-01-02T00:01:00", "seq": 3,
         "facility_code": "", "facility_name": ""},
    ],
    "voyage": VOYAGE,
}
UNMATCHED_VERDICT = {
    "catalog": {"label": "v1+test"}, "evaluated_count": 0, "violations": [],
    "skipped": [{"rule_id": "C-VSL-01", "title": "동명이선", "reason": "매칭 실패"},
                {"rule_id": "C-ROUTE-01", "title": "울산 선박 미확인", "reason": "커버리지 밖"}],
}
UNMATCHED = {
    **VIOLATING, "verdict": UNMATCHED_VERDICT,
    "match": {"matched": False, "strategy": "vessel_name", "reason": "선박을 찾지 못했습니다",
              "call_sign": None, "vessel_name": "X", "voyage": None, "window": None, "candidates": []},
    "events": [], "voyage": None,
}


@pytest.fixture
def fake_ai(monkeypatch):
    monkeypatch.setattr(settings, "ai_service_url", "http://ai.test")
    state = {"status": 200, "body": VIOLATING}

    class FakeClient:
        def __init__(self, **_): ...
        async def __aenter__(self): return self
        async def __aexit__(self, *_): ...
        async def post(self, url, content, headers):
            return httpx.Response(state["status"], content=json.dumps(state["body"]).encode())

    monkeypatch.setattr(ai_gateway, "httpx", SimpleNamespace(AsyncClient=FakeClient, RequestError=httpx.RequestError))
    return state


async def _shipment(client, pol: str | None = None) -> str:
    sid = (await client.post("/api/v1/shipments")).json()["shipment_id"]
    doc = (await client.post(f"/api/v1/shipments/{sid}/documents",
                             files={"file": ("t.png", b"x", "image/png")})).json()["document_id"]

    def field(name, value):
        return {"field_name": name, "value": value, "confidence": 0.9, "grade": "CONFIRMED",
                "extractor": "rule", "bbox": [0.1, 0.1, 0.5, 0.2]}

    res = await client.put(f"/api/v1/shipments/{sid}/fields", json={"document_id": doc, "page": 1, "fields": [
        field("vessel", "M/V OSUNG HO"), field("on_board_date", "2024-12-30"),
        field("bl_no", f"BL-{uuid.uuid4().hex[:8]}"),
        *([field("port_of_loading", pol)] if pol else []),
    ]})
    assert res.status_code == 200
    return sid


async def _clean_whitelist(client):
    for w in (await client.get("/api/v1/reality/whitelist")).json()["whitelist"]:
        await client.delete(f"/api/v1/reality/whitelist/{w['id']}")


async def test_check_stores_events_and_alerts_and_recheck_dedupes(client, fake_ai):
    await _clean_whitelist(client)
    sid = await _shipment(client)
    first = (await client.post(f"/api/v1/shipments/{sid}/reality/check")).json()
    assert len(first["realityEvents"]) == 3 and len(first["alerts"]) == 1
    alert = first["alerts"][0]
    assert alert["severity"] == "Critical" and alert["acknowledged"] is False
    assert len(alert["reality_event_ids"]) == 2  # C-TIME-* 는 입·출항 이벤트만
    assert alert["document_event_ids"] == ["shipped_on_board_date"]  # 프론트 정식 필드명
    assert first["vesselMatch"]["method"] == "NAME_FALLBACK"
    assert first["adapterStatus"]["connected"] is True and first["skipped"][0]["rule_id"] == "C-VSL-01"

    again = (await client.post(f"/api/v1/shipments/{sid}/reality/check")).json()
    assert len(again["alerts"]) == 1 and len(again["realityEvents"]) == 3
    assert again["alerts"][0]["alert_id"] == alert["alert_id"]
    assert again["alerts"][0]["last_seen_at"] > alert["last_seen_at"]
    stored = (await client.get(f"/api/v1/shipments/{sid}/reality")).json()
    assert stored["alerts"] == again["alerts"]
    listed = (await client.get("/api/v1/alerts?severity=Critical&status=OPEN")).json()["alerts"]
    assert any(a["alert_id"] == alert["alert_id"] and a["bl_no"] for a in listed)


async def test_acknowledge(client, fake_ai):
    await _clean_whitelist(client)
    sid = await _shipment(client)
    alert = (await client.post(f"/api/v1/shipments/{sid}/reality/check")).json()["alerts"][0]
    res = await client.post(f"/api/v1/alerts/{alert['alert_id']}/acknowledge")
    assert res.status_code == 200 and res.json()["status"] == "ACKNOWLEDGED" and res.json()["acknowledged"]
    # 재점검해도 확인 상태는 유지
    again = (await client.post(f"/api/v1/shipments/{sid}/reality/check")).json()
    assert again["alerts"][0]["status"] == "ACKNOWLEDGED"


async def test_whitelist_flips_open_and_new_alerts_start_whitelisted(client, fake_ai):
    await _clean_whitelist(client)
    sid = await _shipment(client)
    await client.post(f"/api/v1/shipments/{sid}/reality/check")
    res = await client.post("/api/v1/reality/whitelist",
                            json={"rule_id": "C-TIME-01", "call_sign": "150040", "reason": "시연"})
    assert res.status_code == 201 and res.json()["alerts_flipped"] >= 1
    assert (await client.post("/api/v1/reality/whitelist",
                              json={"rule_id": "C-TIME-01", "call_sign": "150040", "reason": "중복"})
            ).status_code == 409
    assert (await client.get(f"/api/v1/shipments/{sid}/reality")).json()["alerts"][0]["status"] == "WHITELISTED"

    sid2 = await _shipment(client)
    fresh = (await client.post(f"/api/v1/shipments/{sid2}/reality/check")).json()
    assert fresh["alerts"][0]["status"] == "WHITELISTED"
    assert (await client.delete(f"/api/v1/reality/whitelist/{res.json()['id']}")).status_code == 200
    assert (await client.delete(f"/api/v1/reality/whitelist/{res.json()['id']}")).status_code == 404


ROUTE_VIOLATION = {"rule_id": "C-ROUTE-01", "severity": "critical", "title": "울산 선박 미확인",
                   "message": "울산항 관제 기록에 선박이 없습니다", "fields": ["port_of_loading"], "observed": {}}


async def test_unmatched_ulsan_raises_route_alert_without_events(client, fake_ai):
    await _clean_whitelist(client)
    fake_ai["body"] = {**UNMATCHED, "verdict": {**UNMATCHED_VERDICT, "violations": [ROUTE_VIOLATION]}}
    sid = await _shipment(client, pol="ULSAN, KOREA")
    res = (await client.post(f"/api/v1/shipments/{sid}/reality/check")).json()
    assert [a["rule_id"] for a in res["alerts"]] == ["C-ROUTE-01"]
    assert res["alerts"][0]["reality_event_ids"] == [] and res["realityEvents"] == []
    assert res["vesselMatch"]["method"] == "NOT_FOUND"


async def test_unmatched_non_ulsan_is_skipped_not_alert(client, fake_ai):
    await _clean_whitelist(client)
    fake_ai["body"] = UNMATCHED  # 엔진이 위반 없이 skipped 로 돌려준다
    sid = await _shipment(client, pol="BUSAN")
    res = (await client.post(f"/api/v1/shipments/{sid}/reality/check")).json()
    assert res["alerts"] == [] and res["realityEvents"] == []
    assert {s["rule_id"] for s in res["skipped"]} == {"C-VSL-01", "C-ROUTE-01"}


async def test_missing_inputs_returns_skipped_without_calling_ai(client, fake_ai):
    sid = (await client.post("/api/v1/shipments")).json()["shipment_id"]
    res = await client.post(f"/api/v1/shipments/{sid}/reality/check")
    assert res.status_code == 200 and res.json()["alerts"] == []
    assert "대조하지 않았습니다" in res.json()["skipped"][0]["reason"]


async def test_upstream_failure_recorded_and_counted(client, fake_ai):
    sid = await _shipment(client)
    fake_ai["status"] = 503
    for n in (1, 2):
        assert (await client.post(f"/api/v1/shipments/{sid}/reality/check")).status_code == 502
        status = (await client.get(f"/api/v1/shipments/{sid}/reality")).json()["adapterStatus"]
        assert status["connected"] is False and status["consecutive_failures"] == n
    fake_ai["status"] = 200
    await client.post(f"/api/v1/shipments/{sid}/reality/check")
    status = (await client.get(f"/api/v1/shipments/{sid}/reality")).json()["adapterStatus"]
    assert status["connected"] is True and status["consecutive_failures"] == 0


async def test_cross_tenant_is_404(client, fake_ai):
    await _clean_whitelist(client)
    sid = await _shipment(client)
    alert = (await client.post(f"/api/v1/shipments/{sid}/reality/check")).json()["alerts"][0]
    wl = (await client.post("/api/v1/reality/whitelist",
                            json={"rule_id": "C-OTHER", "reason": "x"})).json()
    app.dependency_overrides[get_actor] = lambda: Actor(uuid.uuid4(), uuid.uuid4(), "ADMIN")
    try:
        assert (await client.post(f"/api/v1/shipments/{sid}/reality/check")).status_code == 404
        assert (await client.get(f"/api/v1/shipments/{sid}/reality")).status_code == 404
        assert (await client.post(f"/api/v1/alerts/{alert['alert_id']}/acknowledge")).status_code == 404
        assert (await client.delete(f"/api/v1/reality/whitelist/{wl['id']}")).status_code == 404
        assert (await client.get("/api/v1/alerts")).json()["alerts"] == []
    finally:
        app.dependency_overrides.pop(get_actor, None)
    await client.delete(f"/api/v1/reality/whitelist/{wl['id']}")


async def test_edited_value_beats_stale_normalized_value(client, fake_ai):
    from sqlalchemy import text

    from smart_e_bl.api.reality import _build_bl
    from smart_e_bl.db import AsyncSessionLocal, sync_session
    from smart_e_bl.worker.main import _eligible_shipments

    sid = await _shipment(client, pol="BUSAN")
    async with AsyncSessionLocal() as s:  # 사용자가 고친 뒤의 상태: value 만 바뀌고 normalized_value 는 낡음
        await s.execute(text("UPDATE field_value SET value = 'M/V OSUNG', normalized_value = 'HMM ALGECIRAS / 2608E' "
                             "WHERE shipment_id = :s AND field_code = 'BL.VESSEL_VOYAGE'"), {"s": sid})
        await s.execute(text("UPDATE field_value SET value = 'ULSAN, KOREA', normalized_value = 'BUSAN' "
                             "WHERE shipment_id = :s AND field_code = 'BL.PORT_OF_LOADING'"), {"s": sid})
        await s.execute(text("UPDATE field_value SET value = :d, normalized_value = :d "
                             "WHERE shipment_id = :s AND field_code = 'BL.ONBOARD_DATE'"),
                        {"s": sid, "d": date.today().isoformat()})  # lookback 안으로
        await s.commit()
        assert (await _build_bl(s, uuid.UUID(sid)))["vessel"] == "M/V OSUNG"
    with sync_session() as s:
        assert any(str(k[0]) == sid for k in _eligible_shipments(s))


async def test_alert_resolves_when_no_longer_fired_and_refires_open(client, fake_ai):
    await _clean_whitelist(client)
    fake_ai["body"] = {**UNMATCHED, "verdict": {**UNMATCHED_VERDICT, "violations": [ROUTE_VIOLATION]}}
    sid = await _shipment(client, pol="ULSAN, KOREA")
    first = (await client.post(f"/api/v1/shipments/{sid}/reality/check")).json()
    assert [a["rule_id"] for a in first["alerts"]] == ["C-ROUTE-01"]
    fake_ai["body"] = VIOLATING | {"verdict": {**VIOLATING["verdict"], "violations": []}}
    second = (await client.post(f"/api/v1/shipments/{sid}/reality/check")).json()
    assert second["alerts"] == []
    assert (await client.get(f"/api/v1/shipments/{sid}/reality")).json()["alerts"] == []
    aid = first["alerts"][0]["alert_id"]
    assert not any(a["alert_id"] == aid for a in (await client.get("/api/v1/alerts")).json()["alerts"])
    resolved = (await client.get("/api/v1/alerts?status=RESOLVED")).json()["alerts"]
    assert any(a["alert_id"] == aid for a in resolved)
    fake_ai["body"] = {**UNMATCHED, "verdict": {**UNMATCHED_VERDICT, "violations": [ROUTE_VIOLATION]}}
    third = (await client.post(f"/api/v1/shipments/{sid}/reality/check")).json()
    assert third["alerts"][0]["alert_id"] == aid and third["alerts"][0]["status"] == "OPEN"


async def test_deleting_whitelist_reopens_alerts(client, fake_ai):
    await _clean_whitelist(client)
    sid = await _shipment(client)
    await client.post(f"/api/v1/shipments/{sid}/reality/check")
    wl = (await client.post("/api/v1/reality/whitelist",
                            json={"rule_id": "C-TIME-01", "call_sign": "150040", "reason": "시연"})).json()
    other = (await client.post("/api/v1/reality/whitelist",
                               json={"rule_id": "C-TIME-01", "call_sign": "999999", "reason": "다른 선박"})).json()
    await client.delete(f"/api/v1/reality/whitelist/{other['id']}")  # 무관한 항목 삭제는 영향 없음
    assert (await client.get(f"/api/v1/shipments/{sid}/reality")).json()["alerts"][0]["status"] == "WHITELISTED"
    await client.delete(f"/api/v1/reality/whitelist/{wl['id']}")
    assert (await client.get(f"/api/v1/shipments/{sid}/reality")).json()["alerts"][0]["status"] == "OPEN"


async def test_skipped_rule_does_not_resolve_alert(client, fake_ai):
    await _clean_whitelist(client)
    sid = await _shipment(client)
    first = (await client.post(f"/api/v1/shipments/{sid}/reality/check")).json()
    rule = first["alerts"][0]["rule_id"]
    # 다음 점검에서 그 룰을 판정하지 못함(예: 날짜 해석 실패) — 해소가 아니라 판정 불가
    fake_ai["body"] = VIOLATING | {"verdict": {
        **VIOLATING["verdict"], "violations": [],
        "skipped": [{"rule_id": rule, "title": "-", "reason": "본선적재일을 해석할 수 없습니다"}],
    }}
    second = (await client.post(f"/api/v1/shipments/{sid}/reality/check")).json()
    assert [a["rule_id"] for a in second["alerts"]] == [rule]
    assert second["alerts"][0]["status"] == "OPEN"


async def test_duplicate_seq_in_one_response_is_deduped_keep_last(client, fake_ai):
    sid = await _shipment(client)
    dup = {**VIOLATING, "events": [
        *VIOLATING["events"],
        {"event_type": "ANCHOR", "raw_code": "8", "occurred_at": "2025-01-01T15:30:00", "seq": 2,
         "facility_code": "WAM", "facility_name": "정박지 02"},
    ]}
    fake_ai["body"] = dup
    view = (await client.post(f"/api/v1/shipments/{sid}/reality/check")).json()
    evs = view["realityEvents"]
    assert [e["raw_code"] for e in evs] == ["3", "8", "9"]  # seq 2 는 마지막 값, 행은 3개
    alert = (await client.get("/api/v1/alerts")).json()["alerts"]
    ids = next(a for a in alert if a["shipment_id"] == sid)["reality_event_ids"]
    assert len(ids) == len(set(ids)) and set(ids) <= {e["event_id"] for e in evs}
