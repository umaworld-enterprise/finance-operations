"""Notifications, push subscriptions, and TT copy fields on payment_details.

- notifications: in-app bell rows (also the dedupe ledger for push/email —
  one payment_processed row per deposit request).
- push_subscriptions: Web Push endpoints per user.
- payment_details: tt_copy_url / tt_copy_file_id / tt_copy_filename — the
  Google Drive link for the bank TT copy document.

Revision ID: 0015
Revises: 0014
Create Date: 2026-07-09
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("url", sa.String(500), nullable=True),
        sa.Column("attachment_url", sa.String(1024), nullable=True),
        sa.Column("deposit_request_id", sa.UUID(as_uuid=True), sa.ForeignKey("deposit_requests.id"), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_notifications_user_read_created "
        "ON notifications (user_id, is_read, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_notifications_request_type "
        "ON notifications (deposit_request_id, type)"
    )

    op.create_table(
        "push_subscriptions",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False, unique=True),
        sa.Column("p256dh", sa.Text(), nullable=False),
        sa.Column("auth", sa.Text(), nullable=False),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_push_subscriptions_user ON push_subscriptions (user_id)"
    )

    op.add_column("payment_details", sa.Column("tt_copy_url", sa.String(1024), nullable=True))
    op.add_column("payment_details", sa.Column("tt_copy_file_id", sa.String(128), nullable=True))
    op.add_column("payment_details", sa.Column("tt_copy_filename", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("payment_details", "tt_copy_filename")
    op.drop_column("payment_details", "tt_copy_file_id")
    op.drop_column("payment_details", "tt_copy_url")
    op.drop_table("push_subscriptions")
    op.drop_table("notifications")
