"""Per-tranche payment details (Aug 2026 change batch, item 3).

Accounts now record payment details per tranche — Payment Date, Bank and
Payment Reference Number (reference optional) — and a tranche can only be
marked paid once its TT copy AND its payment details are in. The TT upload no
longer auto-pays. Nullable columns: existing tranches (paid or unpaid)
legitimately predate this data.

Revision ID: 0022
Revises: 0021
Create Date: 2026-08-01
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: Union[str, None] = "0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("payment_tranches", sa.Column("payment_date", sa.Date(), nullable=True))
    op.add_column("payment_tranches", sa.Column("bank", sa.String(200), nullable=True))
    op.add_column(
        "payment_tranches",
        sa.Column("payment_reference_number", sa.String(200), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("payment_tranches", "payment_reference_number")
    op.drop_column("payment_tranches", "bank")
    op.drop_column("payment_tranches", "payment_date")
