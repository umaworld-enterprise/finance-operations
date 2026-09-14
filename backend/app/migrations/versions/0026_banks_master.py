"""Bank name master (Aug 2026).

Bank on the per-tranche payment details becomes a dropdown driven by this
master, scoped to the request's currency at render time: the master stores
bank NAMES only (DBS, Citi, SCB, …) and the form composes the stored value
as '{name} ({currency})'. Dropdown-only by client decision — no free-text
fallback; the service validates saves against the active list.

Seeds the three initial banks: DBS, Citi, SCB.

Revision ID: 0026
Revises: 0025
Create Date: 2026-08-04
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0026"
down_revision: Union[str, None] = "0025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "banks_master",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.execute(
        "INSERT INTO banks_master (name, sort_order) VALUES "
        "('DBS', 1), ('Citi', 2), ('SCB', 3)"
    )


def downgrade() -> None:
    op.drop_table("banks_master")
