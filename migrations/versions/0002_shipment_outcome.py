"""S10 persistent bank-document purchase outcome feedback.

Revision ID: 0002_shipment_outcome
Revises: 0001_baseline
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0002_shipment_outcome"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE shipment_outcome (
            id uuid PRIMARY KEY DEFAULT uuidv7(),
            tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
            shipment_id uuid NOT NULL UNIQUE REFERENCES shipment(id) ON DELETE CASCADE,
            decision text NOT NULL CHECK (decision IN
                ('PENDING', 'APPROVED', 'AMENDMENT', 'REJECTED')),
            reason text NOT NULL CHECK (reason IN
                ('UNKNOWN', 'DOCUMENT_MISMATCH', 'LC_DISCREPANCY',
                 'LATE_PRESENTATION', 'OTHER')),
            memo text NOT NULL DEFAULT '',
            decided_on date NOT NULL,
            source text NOT NULL DEFAULT 'USER_INPUT'
                CHECK (source = 'USER_INPUT'),
            recorded_by uuid NOT NULL REFERENCES app_user(id) ON DELETE RESTRICT,
            recorded_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        );
    """)
    op.execute("""
        CREATE INDEX shipment_outcome_tenant_decision_idx
          ON shipment_outcome (tenant_id, decision, updated_at DESC);
    """)
    op.execute("""
        CREATE TRIGGER shipment_outcome_set_updated_at
          BEFORE UPDATE ON shipment_outcome FOR EACH ROW
          EXECUTE FUNCTION set_updated_at();
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS shipment_outcome")
