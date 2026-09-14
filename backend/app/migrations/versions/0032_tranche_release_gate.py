"""Tranche release gate (19 Aug 2026).

From Tranche 2 onwards a tranche is a FUTURE payment: it stays "Yet to be
Released" until the merchandiser explicitly releases it, and Accounts cannot
mark it paid before that. Adds released_at / released_by to payment_tranches.

Backfill: every EXISTING tranche is marked released (released_at =
created_at) so in-flight payments keep flowing — the gate applies only to
tranches created after this deploy. Tranche 1 is auto-released at creation
by the application.

Revision ID: 0032
Revises: 0031
Create Date: 2026-08-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0032"
down_revision: Union[str, None] = "0031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "payment_tranches",
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "payment_tranches",
        sa.Column(
            "released_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
    )
    op.execute("UPDATE payment_tranches SET released_at = created_at")


def downgrade() -> None:
    op.drop_column("payment_tranches", "released_by")
    op.drop_column("payment_tranches", "released_at")
