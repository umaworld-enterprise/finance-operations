"""Projections module (4 Sep 2026).

1. ``verticals.assigned_user_id`` — a vertical belongs to at most ONE user
   (a user may hold many verticals). Drives the projection form's vertical
   list; nothing else in the system reads it.
2. ``projections`` — one row per (vertical, year, month): the merchandiser's
   projected amounts in USD / EUR / CNY, collected from the 25th to the end
   of the previous month. ``submitted_by`` records who actually entered it
   (the merchandiser, or the Super Admin on their behalf after the deadline).

Revision ID: 0034
Revises: 0033
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "verticals",
        sa.Column(
            "assigned_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
    )
    op.create_index("idx_verticals_assigned_user", "verticals", ["assigned_user_id"])

    op.create_table(
        "projections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("vertical_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("verticals.id"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=False),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("month", sa.Integer, nullable=False),
        sa.Column("amount_usd", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("amount_eur", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("amount_cny", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("submitted_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("month BETWEEN 1 AND 12", name="ck_projections_month"),
        sa.UniqueConstraint("vertical_id", "year", "month", name="uq_projection_vertical_period"),
    )
    op.create_index("idx_projections_period", "projections", ["year", "month"])
    op.create_index("idx_projections_user", "projections", ["user_id"])


def downgrade() -> None:
    op.drop_table("projections")
    op.drop_index("idx_verticals_assigned_user", table_name="verticals")
    op.drop_column("verticals", "assigned_user_id")
