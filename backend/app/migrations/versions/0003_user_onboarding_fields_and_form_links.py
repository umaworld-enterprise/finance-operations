"""Add onboarding fields to users table and create form_links table.

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add onboarding columns to users
    op.add_column("users", sa.Column("secondary_email", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("department", sa.String(100), nullable=True))
    op.add_column("users", sa.Column("onboarding_completed", sa.Boolean(), nullable=False, server_default="false"))

    # Super admins skip onboarding — mark them as already completed
    op.execute("UPDATE users SET onboarding_completed = TRUE WHERE role = 'super_admin'")

    # Create form_links table
    op.create_table(
        "form_links",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("slug", sa.String(100), nullable=False, unique=True),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_by", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # Seed the default form link
    op.execute("INSERT INTO form_links (slug, label) VALUES ('default', 'Default Public Form')")


def downgrade() -> None:
    op.drop_table("form_links")
    op.drop_column("users", "onboarding_completed")
    op.drop_column("users", "department")
    op.drop_column("users", "secondary_email")
