"""F6 현실 대조 영속화: 실행 이력·이벤트 스냅샷·경보·화이트리스트.

Revision ID: 0003_reality
Revises: 0002_shipment_outcome
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0003_reality"
down_revision: str | None = "0002_shipment_outcome"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 성공·실패 모든 점검을 남긴다 — 실패 연속 횟수가 어댑터 상태가 된다.
    op.execute("""
        CREATE TABLE reality_run (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
            shipment_id uuid NOT NULL REFERENCES shipment(id) ON DELETE CASCADE,
            adapter text NOT NULL,
            records int NOT NULL DEFAULT 0,
            matched boolean NOT NULL DEFAULT false,
            match jsonb,
            verdict jsonb,
            catalog_fingerprint text,
            ok boolean NOT NULL,
            error text,
            created_at timestamptz NOT NULL DEFAULT now()
        );
    """)
    op.execute("CREATE INDEX reality_run_ship_idx ON reality_run (tenant_id, shipment_id, created_at DESC);")
    op.execute("""
        CREATE TABLE reality_event (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
            shipment_id uuid NOT NULL REFERENCES shipment(id) ON DELETE CASCADE,
            source text NOT NULL,
            call_sign text NOT NULL,
            voyage_key text NOT NULL,
            seq int NOT NULL,
            event_type text NOT NULL,
            raw_code text,
            occurred_at timestamptz NOT NULL,
            facility_code text,
            facility_name text,
            fetched_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (shipment_id, source, voyage_key, seq)
        );
    """)
    op.execute("CREATE INDEX reality_event_tenant_idx ON reality_event (tenant_id, shipment_id);")
    op.execute("""
        CREATE TABLE reality_alert (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
            shipment_id uuid NOT NULL REFERENCES shipment(id) ON DELETE CASCADE,
            rule_id text NOT NULL,
            severity text NOT NULL CHECK (severity IN ('critical', 'warning', 'info')),
            title text NOT NULL,
            message text NOT NULL,
            observed jsonb,
            document_fields text[] NOT NULL DEFAULT '{}',
            reality_event_ids uuid[] NOT NULL DEFAULT '{}',
            catalog_fingerprint text,
            adapter text NOT NULL,
            status text NOT NULL DEFAULT 'OPEN'
                CHECK (status IN ('OPEN', 'ACKNOWLEDGED', 'WHITELISTED', 'RESOLVED')),
            dedupe_key text NOT NULL UNIQUE,
            first_seen_at timestamptz NOT NULL DEFAULT now(),
            last_seen_at timestamptz NOT NULL DEFAULT now(),
            acknowledged_by uuid REFERENCES app_user(id) ON DELETE SET NULL,
            acknowledged_at timestamptz
        );
    """)
    op.execute("CREATE INDEX reality_alert_tenant_idx ON reality_alert (tenant_id, status, last_seen_at DESC);")
    op.execute("""
        CREATE TABLE reality_whitelist (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
            rule_id text NOT NULL,
            call_sign text,
            reason text NOT NULL,
            created_by uuid NOT NULL REFERENCES app_user(id) ON DELETE RESTRICT,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE NULLS NOT DISTINCT (tenant_id, rule_id, call_sign)
        );
    """)


def downgrade() -> None:
    for table in ("reality_whitelist", "reality_alert", "reality_event", "reality_run"):
        op.execute(f"DROP TABLE IF EXISTS {table}")
