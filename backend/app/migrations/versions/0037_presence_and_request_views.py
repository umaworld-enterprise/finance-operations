"""Away summary + seen/unseen red dot for Accounts (23 Sep 2026).

Two executive requests, one schema change:

* ``users.last_seen_at`` — presence heartbeat written while the app tab is
  visible. The gap between it and "now" on return IS the away window, which
  the pop-up uses to count the requests that arrived meanwhile.
* ``users.unseen_since`` — the baseline for the red dot. Seeded to NOW() so
  the roll-out does not light up every historical file; a request never
  opened by the user only counts as unseen when it changed after this.
* ``request_views`` — when each user last OPENED each request. A file shows
  the dot while its latest activity is newer than that row.

Revision ID: 0037
Revises: 0036
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "unseen_since",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "request_views",
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
        sa.Column(
            "deposit_request_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("deposit_requests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "viewed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("user_id", "deposit_request_id", name="uq_request_views_user_request"),
    )
    op.create_index("idx_request_views_user", "request_views", ["user_id", "viewed_at"])


def downgrade() -> None:
    op.drop_index("idx_request_views_user", table_name="request_views")
    op.drop_table("request_views")
    op.drop_column("users", "unseen_since")
    op.drop_column("users", "last_seen_at")
