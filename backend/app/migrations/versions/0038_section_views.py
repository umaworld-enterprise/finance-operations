"""Sidebar "new since you last looked" counts (29 Sep 2026).

``section_views`` records when each user last OPENED each sidebar section
(accounts / hom / file_remarks / merchandiser). The badge counts what has
arrived or changed in that section since — visiting the page stamps the row
and clears the badge.

No row yet means the user has never opened the section: the count then falls
back to ``users.unseen_since`` (added in 0037), so the roll-out does not show
a badge for the entire history.

Revision ID: 0038
Revises: 0037
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "section_views",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("section", sa.String(40), nullable=False),
        sa.Column(
            "viewed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("user_id", "section", name="uq_section_views_user_section"),
    )
    op.create_index("idx_section_views_user", "section_views", ["user_id"])


def downgrade() -> None:
    op.drop_index("idx_section_views_user", table_name="section_views")
    op.drop_table("section_views")
