"""Per-tranche accounts remarks (Aug 2026 follow-up).

Accounts must record a remark on each tranche alongside the payment date and
bank — all three (plus the TT copy) are required before the tranche can be
marked paid. Nullable: existing tranches predate the field.

Revision ID: 0023
Revises: 0022
Create Date: 2026-08-01
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0023"
down_revision: Union[str, None] = "0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("payment_tranches", sa.Column("accounts_remarks", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("payment_tranches", "accounts_remarks")
