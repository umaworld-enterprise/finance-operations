"""Add fixed_deposit_amount to suppliers and payment_terms to deposit_requests.

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-30
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # CR1: Fixed deposit amount per supplier (nullable — only set for specific suppliers)
    op.add_column(
        "suppliers",
        sa.Column("fixed_deposit_amount", sa.Numeric(18, 2), nullable=True),
    )
    # CR10: Payment terms on deposit request
    op.add_column(
        "deposit_requests",
        sa.Column("payment_terms", sa.String(50), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("deposit_requests", "payment_terms")
    op.drop_column("suppliers", "fixed_deposit_amount")
