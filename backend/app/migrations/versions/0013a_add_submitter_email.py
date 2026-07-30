"""Add deposit_requests.submitter_email — missing from migration history.

The column has existed on the ORM model (models/deposit_request.py) and in
production since the public-form feature shipped, but was only ever added to
the live Supabase database directly (never through Alembic) — so a fresh
database following the migration chain in order never gets it, and 0014's
index creation on this column fails with UndefinedColumnError. This migration
closes that gap.

Revision ID: 0013a
Revises: 0013
Create Date: 2026-07-30
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013a"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "deposit_requests",
        sa.Column("submitter_email", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("deposit_requests", "submitter_email")
