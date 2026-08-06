"""File Remarks module (CIO batch 2, Aug 2026).

A tracked Open → Resolved communication channel from merchandisers to the
Accounts team that bypasses the Adjust Invoices module for the time being:
invoice-number changes (whole deposit moves to another file) and invoice
splits are raised as structured remarks — Accounts get notified, act
manually, and resolve with an optional response. Moves no money.

Revision ID: 0025
Revises: 0024
Create Date: 2026-08-04
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0025"
down_revision: Union[str, None] = "0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "file_remarks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("deposit_request_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("deposit_requests.id"), nullable=False),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("old_file_number", sa.String(200), nullable=True),
        sa.Column("new_file_number", sa.String(200), nullable=True),
        sa.Column("remark", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("resolved_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("response_note", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "category IN ('invoice_number_change', 'invoice_split', 'other')",
            name="ck_file_remarks_category",
        ),
        sa.CheckConstraint(
            "status IN ('open', 'resolved')",
            name="ck_file_remarks_status",
        ),
    )
    op.create_index("idx_file_remarks_status", "file_remarks", ["status"])
    op.create_index("idx_file_remarks_request", "file_remarks", ["deposit_request_id"])
    op.create_index("idx_file_remarks_created_by", "file_remarks", ["created_by"])


def downgrade() -> None:
    op.drop_table("file_remarks")
