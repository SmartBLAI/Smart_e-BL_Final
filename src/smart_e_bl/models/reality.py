"""F6 현실 대조 영속화 (migrations/versions/0003_reality.py)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ARRAY, Boolean, DateTime, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from smart_e_bl.models.base import Base, created_at, uuid_pk


def _fk(table: str, *, cascade: bool = True, nullable: bool = False) -> Mapped[Any]:
    return mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{table}.id", ondelete="CASCADE" if cascade else "SET NULL"),
        nullable=nullable,
    )


class RealityRun(Base):
    __tablename__ = "reality_run"

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = _fk("tenant")
    shipment_id: Mapped[uuid.UUID] = _fk("shipment")
    adapter: Mapped[str] = mapped_column(Text, nullable=False)
    records: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    matched: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    match: Mapped[dict | None] = mapped_column(JSONB)
    verdict: Mapped[dict | None] = mapped_column(JSONB)
    catalog_fingerprint: Mapped[str | None] = mapped_column(Text)
    ok: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at()


class RealityEvent(Base):
    __tablename__ = "reality_event"

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = _fk("tenant")
    shipment_id: Mapped[uuid.UUID] = _fk("shipment")
    source: Mapped[str] = mapped_column(Text, nullable=False)
    call_sign: Mapped[str] = mapped_column(Text, nullable=False)
    voyage_key: Mapped[str] = mapped_column(Text, nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    raw_code: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    facility_code: Mapped[str | None] = mapped_column(Text)
    facility_name: Mapped[str | None] = mapped_column(Text)
    fetched_at: Mapped[datetime] = created_at()


class RealityAlert(Base):
    __tablename__ = "reality_alert"

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = _fk("tenant")
    shipment_id: Mapped[uuid.UUID] = _fk("shipment")
    rule_id: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    observed: Mapped[dict | None] = mapped_column(JSONB)
    document_fields: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    reality_event_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    catalog_fingerprint: Mapped[str | None] = mapped_column(Text)
    adapter: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="OPEN")
    dedupe_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    first_seen_at: Mapped[datetime] = created_at()
    last_seen_at: Mapped[datetime] = created_at()
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RealityWhitelist(Base):
    __tablename__ = "reality_whitelist"

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = _fk("tenant")
    rule_id: Mapped[str] = mapped_column(Text, nullable=False)
    call_sign: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = created_at()
