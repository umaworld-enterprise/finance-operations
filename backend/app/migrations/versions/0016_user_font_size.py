"""Per-user font size preference (accessibility).

Revision ID: 0016
Revises: 0015
Create Date: 2026-07-09
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("font_size", sa.String(16), nullable=False, server_default="default"),
    )


def downgrade() -> None:
    op.drop_column("users", "font_size")
