"""Backfill enum labels that exist in Python enums but not in migration 0001.

Migration 0001 creates enums with CREATE TYPE ... EXCEPTION WHEN duplicate_object,
so on the original Supabase DB (where fuller types already existed) it silently
skipped them. A fresh environment built purely from migrations would be missing
'public_form' (submission_source) and 'LOGIN'/'AI_QUERY' (audit_action), breaking
the public form and /auth/me. ADD VALUE IF NOT EXISTS is a no-op on databases
that already have the labels.

Revision ID: 0013
Revises: 0012
Create Date: 2026-07-06
"""
from alembic import op
import sqlalchemy as sa

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    # ALTER TYPE cannot run inside an open transaction.
    conn.execute(sa.text("COMMIT"))
    conn.execute(sa.text("ALTER TYPE submission_source ADD VALUE IF NOT EXISTS 'public_form'"))
    conn.execute(sa.text("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'LOGIN'"))
    conn.execute(sa.text("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'AI_QUERY'"))


def downgrade() -> None:
    # PostgreSQL does not support removing enum values.
    pass
