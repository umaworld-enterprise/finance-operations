"""Add users.ai_access_enabled — missing from migration history.

Same class of gap as 0013a (submitter_email): the column exists on the ORM
model and has been live on Supabase production (added directly to the
database, never through Alembic), so a fresh database following the
migration chain in order never got it — every query that selects a full
User row (e.g. login) then fails with UndefinedColumnError.

Revision ID: 0020
Revises: 0019
Create Date: 2026-07-30
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: Union[str, None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("ai_access_enabled", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("users", "ai_access_enabled")
