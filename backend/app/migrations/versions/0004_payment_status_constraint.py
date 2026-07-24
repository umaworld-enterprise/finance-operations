"""Add CHECK constraint on payment_details.payment_status.

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-30
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_VALID = ("processed", "rejected", "hold")


def upgrade() -> None:
    # Null out any existing free-text values that don't match the new enum
    op.execute(
        f"UPDATE payment_details SET payment_status = NULL "
        f"WHERE payment_status IS NOT NULL AND payment_status NOT IN {_VALID}"
    )
    op.create_check_constraint(
        "ck_payment_status",
        "payment_details",
        "payment_status IS NULL OR payment_status IN ('processed', 'rejected', 'hold')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_payment_status", "payment_details", type_="check")
