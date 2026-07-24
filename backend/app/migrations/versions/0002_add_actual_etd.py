"""Add actual_etd column to payment_details.

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("payment_details", sa.Column("actual_etd", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("payment_details", "actual_etd")
