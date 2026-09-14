"""Reject Tranche workflow (Aug 2026).

Breaks the touched-lock deadlock: once Accounts interact with a request the
merchandiser's tranches freeze, so a wrong tranche amount had no way out.
Accounts can now REJECT a tranche with a mandatory reason — the tranche stays
visible for record-keeping (red disabled card) but its amount stops counting
toward the request total, and the merchandiser regains the ability to add
replacement tranches until the sum matches again.

Adds the 'rejected' label to the tranche_status enum plus the rejection
audit columns.

Revision ID: 0024
Revises: 0023
Create Date: 2026-08-02
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0024"
down_revision: Union[str, None] = "0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    # ALTER TYPE cannot run inside an open transaction (same pattern as 0013).
    conn.execute(sa.text("COMMIT"))
    conn.execute(sa.text("ALTER TYPE tranche_status ADD VALUE IF NOT EXISTS 'rejected'"))

    op.add_column("payment_tranches", sa.Column("rejection_reason", sa.Text(), nullable=True))
    op.add_column(
        "payment_tranches",
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "payment_tranches",
        sa.Column("rejected_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_payment_tranches_rejected_by_users",
        "payment_tranches", "users", ["rejected_by"], ["id"],
    )


def downgrade() -> None:
    # PostgreSQL cannot remove enum values — 'rejected' stays in the type.
    op.drop_constraint(
        "fk_payment_tranches_rejected_by_users", "payment_tranches", type_="foreignkey"
    )
    op.drop_column("payment_tranches", "rejected_by")
    op.drop_column("payment_tranches", "rejected_at")
    op.drop_column("payment_tranches", "rejection_reason")
