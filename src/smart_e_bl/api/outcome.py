"""S10 사용자가 직접 입력한 수출서류 매입 결과. AI 예측으로 채우지 않는다."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from smart_e_bl.api.security import Actor, audit, get_actor, owned_shipment, require_editor
from smart_e_bl.db import get_session
from smart_e_bl.models import ShipmentOutcome

router = APIRouter(prefix="/api/v1", tags=["outcome"])


class OutcomeInput(BaseModel):
    """A result explicitly confirmed by a user; never an AI prediction."""
    decision: Literal["PENDING", "APPROVED", "AMENDMENT", "REJECTED"]
    reason: Literal["UNKNOWN", "DOCUMENT_MISMATCH", "LC_DISCREPANCY", "LATE_PRESENTATION", "OTHER"]
    memo: str = Field(default="", max_length=1500)
    decided_on: date


class OutcomeView(OutcomeInput):
    shipment_id: uuid.UUID
    source: Literal["USER_INPUT"]
    recorded_by: uuid.UUID
    recorded_at: datetime
    updated_at: datetime


def _outcome_view(record: ShipmentOutcome) -> OutcomeView:
    return OutcomeView(
        shipment_id=record.shipment_id,
        decision=record.decision, reason=record.reason, memo=record.memo,
        decided_on=record.decided_on, source="USER_INPUT",
        recorded_by=record.recorded_by, recorded_at=record.recorded_at,
        updated_at=record.updated_at,
    )


@router.get(
    "/shipments/{shipment_id}/outcome", response_model=OutcomeView,
    responses={204: {"description": "아직 기록된 결과가 없음"}},
)
async def get_outcome(
    shipment_id: uuid.UUID,
    actor: Actor = Depends(get_actor),
    session: AsyncSession = Depends(get_session),
) -> OutcomeView | Response:
    await owned_shipment(session, actor, shipment_id)
    result = await session.scalar(select(ShipmentOutcome).where(
        ShipmentOutcome.shipment_id == shipment_id,
        ShipmentOutcome.tenant_id == actor.tenant_id,
    ))
    if result is None:
        # 아직 입력 전은 정상 상태 — 404 로 내면 브라우저 콘솔에 오류로 찍힌다.
        return Response(status_code=204)
    return _outcome_view(result)


@router.put("/shipments/{shipment_id}/outcome", response_model=OutcomeView)
async def save_outcome(
    shipment_id: uuid.UUID, body: OutcomeInput,
    actor: Actor = Depends(get_actor),
    session: AsyncSession = Depends(get_session),
) -> OutcomeView:
    require_editor(actor)
    await owned_shipment(session, actor, shipment_id)
    existing = await session.scalar(select(ShipmentOutcome).where(
        ShipmentOutcome.shipment_id == shipment_id,
        ShipmentOutcome.tenant_id == actor.tenant_id,
    ).with_for_update())
    before = {
        "decision": existing.decision, "reason": existing.reason,
        "memo": existing.memo, "decided_on": existing.decided_on.isoformat(),
    } if existing else None
    if existing is None:
        existing = ShipmentOutcome(
            tenant_id=actor.tenant_id, shipment_id=shipment_id,
            recorded_by=actor.user_id, source="USER_INPUT",
            **body.model_dump(),
        )
        session.add(existing)
    else:
        for key, value in body.model_dump().items():
            setattr(existing, key, value)
        # Preserve initial reporter and recorded_at for audit integrity.
    try:
        await session.flush()
        session.add(audit(
            actor, "OUTCOME_CONFIRM", "shipment", existing.id, shipment_id, before=before,
            after={**body.model_dump(exclude={"decided_on"}),
                   "decided_on": body.decided_on.isoformat(), "source": "USER_INPUT"},
        ))
        await session.commit()
        await session.refresh(existing)
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail="결과 저장이 DB 제약과 충돌합니다.") from exc
    return _outcome_view(existing)
