"""Add head_of_merchandiser role, HoM request statuses, and auto-flagging columns.

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-04
"""
from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # ALTER TYPE cannot run inside an open transaction.
    # Commit the current Alembic-managed transaction first, then run them bare.
    conn.execute(sa.text("COMMIT"))
    conn.execute(sa.text("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'head_of_merchandiser'"))
    conn.execute(sa.text("ALTER TYPE request_status ADD VALUE IF NOT EXISTS 'pending_hom_approval'"))
    conn.execute(sa.text("ALTER TYPE request_status ADD VALUE IF NOT EXISTS 'rejected_by_hom'"))

    # Table DDL can now run in a fresh transaction
    op.alter_column(
        "defaulted_suppliers", "flagged_by",
        existing_type=sa.dialects.postgresql.UUID(as_uuid=True),
        nullable=True,
    )
    op.add_column(
        "defaulted_suppliers",
        sa.Column("is_auto_flagged", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("defaulted_suppliers", "is_auto_flagged")
    op.alter_column(
        "defaulted_suppliers", "flagged_by",
        existing_type=sa.dialects.postgresql.UUID(as_uuid=True),
        nullable=False,
    )
    # PostgreSQL does not support removing enum values.
