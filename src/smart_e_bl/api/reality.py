"""F6 현실 대조 영속화 + 경보 관리.

ai-service 는 stateless 라 점검 결과를 저장하지 않는다. 스냅샷·중복 제거·확인/화이트리스트
상태는 게이트웨이의 일이다 (docs/backend/ai-service/f6-customs-reality-check.md §1).
울산 외 항만·평가 못 한 룰은 '경보'가 아니다 — 엔진이 not_evaluated 로 준 룰은 skipped 로 그대로 보여준다.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import any_, case, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from smart_e_bl.api.ai_gateway import call_ai
from smart_e_bl.api.security import Actor, audit, get_actor, owned_shipment, require_editor
from smart_e_bl.db import get_session
from smart_e_bl.fields import field_code, field_name
from smart_e_bl.models import (
    FieldValue,
    RealityAlert,
    RealityEvent,
    RealityRun,
    RealityWhitelist,
    Shipment,
)

router = APIRouter(prefix="/api/v1", tags=["reality"])

COVERAGE_NOTE = "울산항 VTS 관제 기록만 대조 (울산 외 항만·세관 이벤트 없음)"
_KST = ZoneInfo("Asia/Seoul")  # 울산항 관제 시각은 tz 없이 오므로 KST 로 본다
_BL_FIELDS = {  # field_definition.code -> ai-service bl 키
    "BL.VESSEL_VOYAGE": "vessel",
    "BL.PORT_OF_LOADING": "port_of_loading",
    "BL.PORT_OF_DISCHARGE": "port_of_discharge",
    "BL.ONBOARD_DATE": "on_board_date",
    "BL.BL_NO": "bl_no",
}
_SEVERITY_RANK = {"critical": 0, "warning": 1, "info": 2}


async def _build_bl(session: AsyncSession, shipment_id: uuid.UUID) -> dict:
    rows = await session.execute(
        select(FieldValue.field_code, FieldValue.value, FieldValue.normalized_value).where(
            FieldValue.shipment_id == shipment_id,
            FieldValue.is_representative,
            FieldValue.field_code.in_(_BL_FIELDS),
        )
    )
    # 사용자가 고친 value 가 우선이다 (normalized_value 는 낡은 추출값일 수 있다)
    bl = {_BL_FIELDS[code]: (value or norm) for code, value, norm in rows}
    return {k: v for k, v in bl.items() if v}


def _event_json(e: RealityEvent) -> dict:
    return {
        "event_id": str(e.id), "shipment_id": str(e.shipment_id), "source": "ULSAN_VTS",
        "source_event_code": e.raw_code or "", "event_type": e.event_type,
        "occurred_at": e.occurred_at.isoformat(), "recorded_at": e.fetched_at.isoformat(),
        "location": "KRUSN", "quantity": None, "container_no": None,
        "trust_grade": "A", "precision": "DATETIME", "voyage_no": e.voyage_key,
        "facility": (None if not e.facility_code
                     else "정박지" if e.facility_code == "WAM" else "계류시설"),
        "raw_code": e.raw_code,
    }


def _alert_json(a: RealityAlert, bl_no: str | None) -> dict:
    return {
        "alert_id": str(a.id), "shipment_id": str(a.shipment_id),
        "severity": a.severity.capitalize(), "message": a.message,
        "bl_no": bl_no or "",
        "document_event_ids": list(a.document_fields),
        "reality_event_ids": [str(i) for i in a.reality_event_ids],
        "acknowledged": a.status != "OPEN", "created_at": a.first_seen_at.isoformat(),
        # 프론트 타입 밖 추가 필드: 경보 센터가 룰·상태·재관측 시각을 보여준다
        "rule_id": a.rule_id, "title": a.title, "status": a.status,
        "last_seen_at": a.last_seen_at.isoformat(),
    }


def _match_method(match: dict) -> str:
    if match.get("matched"):
        return "CALLSIGN" if match.get("strategy") == "call_sign" else "NAME_FALLBACK"
    return "AMBIGUOUS" if len(match.get("candidates") or []) > 1 else "NOT_FOUND"


async def _views(
    session: AsyncSession, tenant_id: uuid.UUID, shipments: list[Shipment],
    extra_skipped: list | None = None,
) -> dict[uuid.UUID, dict]:
    """선적 여러 건의 현실 대조 뷰를 쿼리 3번(runs·events·alerts, IN)으로 만든다."""
    ids = [s.id for s in shipments]
    # 선적별 최근 50건 — 윈도 함수로 한 번에
    rn = func.row_number().over(
        partition_by=RealityRun.shipment_id,
        order_by=(RealityRun.created_at.desc(), RealityRun.id.desc()),
    ).label("rn")
    ranked = select(RealityRun.id, rn).where(
        RealityRun.shipment_id.in_(ids), RealityRun.tenant_id == tenant_id
    ).subquery()
    runs_by: dict[uuid.UUID, list[RealityRun]] = {i: [] for i in ids}
    for r in await session.scalars(
        select(RealityRun).join(ranked, ranked.c.id == RealityRun.id)
        .where(ranked.c.rn <= 50).order_by(RealityRun.created_at.desc(), RealityRun.id.desc())
    ):
        runs_by[r.shipment_id].append(r)
    last_ok_by = {i: next((r for r in rs if r.ok), None) for i, rs in runs_by.items()}
    voyage_of = {i: ((r.match or {}).get("voyage_key") if r else None) for i, r in last_ok_by.items()}

    events_by: dict[uuid.UUID, list[RealityEvent]] = {i: [] for i in ids}
    keys = {k for k in voyage_of.values() if k}
    if keys:
        for e in await session.scalars(
            select(RealityEvent).where(
                RealityEvent.shipment_id.in_([i for i, k in voyage_of.items() if k]),
                RealityEvent.tenant_id == tenant_id, RealityEvent.voyage_key.in_(keys),
            ).order_by(RealityEvent.occurred_at, RealityEvent.seq)
        ):
            if e.voyage_key == voyage_of[e.shipment_id]:
                events_by[e.shipment_id].append(e)
    alerts_by: dict[uuid.UUID, list[RealityAlert]] = {i: [] for i in ids}
    for a in await session.scalars(
        select(RealityAlert).where(
            RealityAlert.shipment_id.in_(ids), RealityAlert.tenant_id == tenant_id,
            RealityAlert.status != "RESOLVED",
        ).order_by(RealityAlert.last_seen_at.desc())
    ):
        alerts_by[a.shipment_id].append(a)

    out = {}
    for shipment in shipments:
        runs, last_ok = runs_by[shipment.id], last_ok_by[shipment.id]
        failures = next((i for i, r in enumerate(runs) if r.ok), len(runs))
        match = (last_ok.match if last_ok else None) or {}
        out[shipment.id] = {
            "realityEvents": [_event_json(e) for e in events_by[shipment.id]],
            "alerts": [_alert_json(a, shipment.bl_no) for a in alerts_by[shipment.id]],
            "adapterStatus": {
                "name": "ULSAN_VTS", "connected": bool(runs) and runs[0].ok,
                "last_synced_at": last_ok.created_at.isoformat() if last_ok else None,
                "consecutive_failures": failures, "coverage_note": COVERAGE_NOTE,
            },
            "vesselMatch": {
                "bl_vessel": match.get("bl_vessel") or match.get("vessel_name") or "", "normalized": match.get("vessel_name") or "",
                "call_sign": match.get("call_sign"), "method": _match_method(match),
                "candidates": match.get("candidates") or [],
            } if last_ok else None,
            "skipped": (list((last_ok.verdict or {}).get("skipped") or []) if last_ok else []) + (extra_skipped or []),
        }
    return out


async def _view(
    session: AsyncSession, tenant_id: uuid.UUID, shipment: Shipment, extra_skipped: list | None = None,
) -> dict:
    return (await _views(session, tenant_id, [shipment], extra_skipped))[shipment.id]


async def run_reality_check(session: AsyncSession, actor: Actor, shipment_id: uuid.UUID) -> dict:
    shipment = await owned_shipment(session, actor, shipment_id)
    bl = await _build_bl(session, shipment_id)
    if not (bl.get("vessel") and bl.get("on_board_date")):
        # 입력 부족은 오류가 아니라 '대조 안 함' — 숨기지 않고 사유를 돌려준다
        return await _view(session, actor.tenant_id, shipment, [{
            "rule_id": None, "title": "현실 대조",
            "reason": "선명 또는 본선적재일이 없어 대조하지 않았습니다.",
        }])
    try:
        resp = await call_ai(session, actor, shipment_id, "reality/check", {"bl": bl})
        data = resp.json()
    except HTTPException as exc:
        await session.rollback()
        session.add(RealityRun(
            tenant_id=actor.tenant_id, shipment_id=shipment_id, adapter="unknown",
            ok=False, error=str(exc.detail)[:500],
        ))
        await session.commit()
        raise

    match, verdict, voyage = data["match"], data["verdict"], data.get("voyage")
    adapter = data["source"]["adapter"]
    fingerprint = (verdict.get("catalog") or {}).get("label")
    voyage_key = (f"{voyage['call_sign']}|{voyage['year']}|{voyage['voyage_no']}"
                  if voyage and match.get("matched") else None)
    session.add(RealityRun(
        tenant_id=actor.tenant_id, shipment_id=shipment_id, adapter=adapter,
        records=data["source"].get("records", 0), matched=bool(match.get("matched")),
        match={**match, "voyage_key": voyage_key, "bl_vessel": bl["vessel"]}, verdict=verdict,
        catalog_fingerprint=fingerprint, ok=True,
    ))

    events: list[RealityEvent] = []
    if voyage_key:
        # 같은 키(seq)가 한 응답에 여러 번 오면 마지막 것만 — 한 INSERT 안에서 같은 행을
        # 두 번 건드리면 ON CONFLICT DO UPDATE 가 오류를 낸다.
        rows: dict[int, dict] = {}
        for e in data.get("events") or []:
            at = datetime.fromisoformat(e["occurred_at"])
            rows[e["seq"]] = dict(
                tenant_id=actor.tenant_id, shipment_id=shipment_id, source=adapter,
                call_sign=voyage["call_sign"], voyage_key=voyage_key, seq=e["seq"],
                event_type=e["event_type"], raw_code=e.get("raw_code"),
                occurred_at=at if at.tzinfo else at.replace(tzinfo=_KST),
                facility_code=e.get("facility_code"), facility_name=e.get("facility_name"),
                fetched_at=func.now(),
            )
        if rows:
            ins = pg_insert(RealityEvent).values(list(rows.values()))
            saved = (await session.execute(ins.on_conflict_do_update(
                index_elements=["shipment_id", "source", "voyage_key", "seq"],
                set_={k: getattr(ins.excluded, k) for k in
                      ("event_type", "raw_code", "occurred_at", "facility_code", "facility_name", "fetched_at")},
            ).returning(RealityEvent))).scalars().all()
            by_seq = {r.seq: r for r in saved}  # 반환 순서가 아니라 키로 되돌린다
            events = [by_seq[seq] for seq in rows]

    whitelist = (await session.scalars(
        select(RealityWhitelist).where(RealityWhitelist.tenant_id == actor.tenant_id)
    )).all()
    fired: list[str] = []
    for v in verdict.get("violations") or []:
        key = hashlib.sha256(f"{shipment_id}|{v['rule_id']}|{voyage_key or ''}".encode()).hexdigest()
        relevant = [e for e in events if e.event_type in ("ARRIVAL", "DEPARTURE")] \
            if v["rule_id"].startswith("C-TIME-") else []
        # C-ROUTE-01(매칭 실패 + 울산 언급)만 근거가 '현실 기록의 부재'라 events 가 빈다
        ids = [e.id for e in (relevant or events)]
        fired.append(key)
        muted = any(w.rule_id == v["rule_id"] and w.call_sign in (None, match.get("call_sign"))
                    for w in whitelist)
        values = dict(
            tenant_id=actor.tenant_id, shipment_id=shipment_id, rule_id=v["rule_id"],
            severity=v["severity"], title=v["title"], message=v["message"],
            observed=v.get("observed"), document_fields=[field_name(field_code(f)) for f in v.get("fields") or []],
            reality_event_ids=ids, catalog_fingerprint=fingerprint, adapter=adapter,
            status="WHITELISTED" if muted else "OPEN", dedupe_key=key,
        )
        ins = pg_insert(RealityAlert).values(**values)
        # 동시 점검 경합 방지: 원자적 upsert. 재점검은 관측만 갱신하고 상태(확인·화이트리스트)는 유지,
        # RESOLVED 였던 경보만 다시 나타난 것이므로 새로 계산한 상태(OPEN/WHITELISTED)로 되돌린다.
        await session.execute(ins.on_conflict_do_update(
            index_elements=["dedupe_key"],
            set_={
                "message": v["message"], "observed": v.get("observed"), "reality_event_ids": ids,
                "last_seen_at": func.now(),
                "status": case((RealityAlert.status == "RESOLVED", ins.excluded.status),
                               else_=RealityAlert.status),
            },
        ))
    # 이번 점검에서 다시 나타나지 않은 경보는 해소 처리 (WHITELISTED 는 그대로)
    stale = update(RealityAlert).where(
        RealityAlert.tenant_id == actor.tenant_id, RealityAlert.shipment_id == shipment_id,
        RealityAlert.status.in_(("OPEN", "ACKNOWLEDGED")),
    )
    if fired:
        stale = stale.where(RealityAlert.dedupe_key.not_in(fired))
    # 판정하지 못한(skipped) 룰은 "해소"가 아니라 "모름" — 기존 경보를 그대로 둔다.
    unevaluated = [s.get("rule_id") for s in verdict.get("skipped", []) if s.get("rule_id")]
    if unevaluated:
        stale = stale.where(RealityAlert.rule_id.not_in(unevaluated))
    await session.execute(stale.values(status="RESOLVED"))
    await session.commit()
    return await _view(session, actor.tenant_id, shipment)


@router.post("/shipments/{shipment_id}/reality/check")
async def check_reality(
    shipment_id: uuid.UUID, actor: Actor = Depends(get_actor),
    session: AsyncSession = Depends(get_session),
) -> dict:
    require_editor(actor)
    return await run_reality_check(session, actor, shipment_id)


@router.get("/shipments/{shipment_id}/reality")
async def get_reality(
    shipment_id: uuid.UUID, actor: Actor = Depends(get_actor),
    session: AsyncSession = Depends(get_session),
) -> dict:
    shipment = await owned_shipment(session, actor, shipment_id)
    return await _view(session, actor.tenant_id, shipment)


@router.get("/alerts")
async def list_alerts(
    severity: str | None = None, status: str | None = None,
    actor: Actor = Depends(get_actor), session: AsyncSession = Depends(get_session),
) -> dict:
    stmt = (select(RealityAlert, Shipment.bl_no)
            .join(Shipment, Shipment.id == RealityAlert.shipment_id)
            .where(RealityAlert.tenant_id == actor.tenant_id))
    if severity:
        stmt = stmt.where(RealityAlert.severity == severity.lower())
    if status:
        stmt = stmt.where(RealityAlert.status == status.upper())
    else:  # 해소된 경보는 status=RESOLVED 로 따로 요청할 때만
        stmt = stmt.where(RealityAlert.status != "RESOLVED")
    rank = case(*[(RealityAlert.severity == k, v) for k, v in _SEVERITY_RANK.items()], else_=9)
    rows = await session.execute(stmt.order_by(rank, RealityAlert.last_seen_at.desc()))
    return {"alerts": [_alert_json(a, bl_no) for a, bl_no in rows]}


@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: uuid.UUID, actor: Actor = Depends(get_actor),
    session: AsyncSession = Depends(get_session),
) -> dict:
    require_editor(actor)
    alert = await session.scalar(select(RealityAlert).where(
        RealityAlert.id == alert_id, RealityAlert.tenant_id == actor.tenant_id))
    if alert is None:
        raise HTTPException(status_code=404, detail="경보를 찾을 수 없습니다.")
    before = alert.status
    alert.status, alert.acknowledged_by, alert.acknowledged_at = "ACKNOWLEDGED", actor.user_id, func.now()
    session.add(audit(actor, "REALITY_ALERT_ACK", "reality_alert", alert.id, alert.shipment_id,
                       {"rule_id": alert.rule_id, "before": before}))
    await session.commit()
    await session.refresh(alert)
    bl_no = await session.scalar(select(Shipment.bl_no).where(Shipment.id == alert.shipment_id))
    return _alert_json(alert, bl_no)


class WhitelistInput(BaseModel):
    rule_id: str = Field(min_length=1)
    call_sign: str | None = None
    reason: str = Field(min_length=1, max_length=500)


def _whitelist_json(w: RealityWhitelist) -> dict:
    return {"id": str(w.id), "rule_id": w.rule_id, "call_sign": w.call_sign, "reason": w.reason,
            "created_by": str(w.created_by), "created_at": w.created_at.isoformat()}


@router.get("/reality/whitelist")
async def list_whitelist(
    actor: Actor = Depends(get_actor), session: AsyncSession = Depends(get_session),
) -> dict:
    rows = await session.scalars(select(RealityWhitelist).where(
        RealityWhitelist.tenant_id == actor.tenant_id).order_by(RealityWhitelist.created_at.desc()))
    return {"whitelist": [_whitelist_json(w) for w in rows]}


@router.post("/reality/whitelist", status_code=201)
async def add_whitelist(
    body: WhitelistInput, actor: Actor = Depends(get_actor),
    session: AsyncSession = Depends(get_session),
) -> dict:
    require_editor(actor)
    entry = RealityWhitelist(tenant_id=actor.tenant_id, created_by=actor.user_id, **body.model_dump())
    session.add(entry)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail="이미 등록된 화이트리스트입니다.") from exc
    stmt = update(RealityAlert).where(
        RealityAlert.tenant_id == actor.tenant_id, RealityAlert.rule_id == body.rule_id,
        RealityAlert.status.in_(("OPEN", "ACKNOWLEDGED")),
    )
    if body.call_sign:  # 경보는 call_sign 을 직접 갖지 않아 근거 이벤트로 판별한다
        stmt = stmt.where(select(RealityEvent.id).where(
            RealityEvent.id == any_(RealityAlert.reality_event_ids),
            RealityEvent.call_sign == body.call_sign,
        ).exists())
    flipped = (await session.execute(stmt.values(status="WHITELISTED"))).rowcount
    session.add(audit(actor, "REALITY_WHITELIST_ADD", "reality_whitelist", entry.id,
                       after={**body.model_dump(), "alerts_flipped": flipped}))
    await session.commit()
    await session.refresh(entry)
    return {**_whitelist_json(entry), "alerts_flipped": flipped}


@router.delete("/reality/whitelist/{whitelist_id}")
async def delete_whitelist(
    whitelist_id: uuid.UUID, actor: Actor = Depends(get_actor),
    session: AsyncSession = Depends(get_session),
) -> dict:
    require_editor(actor)
    entry = await session.scalar(select(RealityWhitelist).where(
        RealityWhitelist.id == whitelist_id, RealityWhitelist.tenant_id == actor.tenant_id))
    if entry is None:
        raise HTTPException(status_code=404, detail="화이트리스트를 찾을 수 없습니다.")
    session.add(audit(actor, "REALITY_WHITELIST_DELETE", "reality_whitelist", entry.id,
                       after={"rule_id": entry.rule_id, "call_sign": entry.call_sign}))
    await session.delete(entry)
    await session.flush()
    # 이 항목 때문에만 WHITELISTED 였던 경보는 OPEN 으로 되돌린다 (남은 항목으로 재평가)
    remaining = (await session.scalars(select(RealityWhitelist).where(
        RealityWhitelist.tenant_id == actor.tenant_id, RealityWhitelist.rule_id == entry.rule_id))).all()
    held = (await session.scalars(select(RealityAlert).where(
        RealityAlert.tenant_id == actor.tenant_id, RealityAlert.rule_id == entry.rule_id,
        RealityAlert.status == "WHITELISTED"))).all()
    # 경보별 조회(N+1) 대신 근거 이벤트의 call_sign 을 한 번에 가져온다
    sign_of = dict((await session.execute(select(RealityEvent.id, RealityEvent.call_sign).where(
        RealityEvent.id.in_({i for a in held for i in a.reality_event_ids})))).all())
    for a in held:
        signs = {sign_of[i] for i in a.reality_event_ids if i in sign_of} or {None}
        if not any(w.call_sign is None or w.call_sign in signs for w in remaining):
            a.status = "OPEN"
    await session.commit()
    return {"deleted": str(whitelist_id)}
