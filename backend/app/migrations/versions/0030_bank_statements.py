"""Banking module (Aug 2026): bank statements + AI-extracted transactions.

Super-admin-only module — upload a bank statement PDF (Citi Asia Account
Statement layout first), pages are rendered to images and extracted via the
configured AI vision provider, and a dashboard reads the stored rows.
Standalone from the Advance Payment module (no FK links to requests).

Revision ID: 0030
Revises: 0029
Create Date: 2026-08-12
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0030"
down_revision: Union[str, None] = "0029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bank_statements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("bank_name", sa.String(100), nullable=False),
        sa.Column("account_number", sa.String(50), nullable=True),
        sa.Column("account_title", sa.String(200), nullable=True),
        sa.Column("currency", sa.String(10), nullable=True),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("beginning_balance", sa.Numeric(18, 2), nullable=True),
        sa.Column("ending_balance", sa.Numeric(18, 2), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("original_filename", sa.String(300), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="processing"),
        sa.Column("extraction_note", sa.Text(), nullable=True),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint(
            "account_number", "period_start", "period_end",
            name="uq_bank_statement_account_period",
        ),
    )
    op.create_index("idx_bank_statements_status", "bank_statements", ["status"])

    op.create_table(
        "bank_transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("statement_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("bank_statements.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("txn_date", sa.Date(), nullable=True),
        sa.Column("category", sa.String(200), nullable=True),
        sa.Column("reference", sa.String(200), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("debit", sa.Numeric(18, 2), nullable=True),
        sa.Column("credit", sa.Numeric(18, 2), nullable=True),
    )
    op.create_index("idx_bank_transactions_statement", "bank_transactions", ["statement_id"])
    op.create_index("idx_bank_transactions_date", "bank_transactions", ["txn_date"])

    op.create_table(
        "bank_daily_balances",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("statement_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("bank_statements.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("balance_date", sa.Date(), nullable=False),
        sa.Column("closing_balance", sa.Numeric(18, 2), nullable=False),
        sa.UniqueConstraint("statement_id", "balance_date", name="uq_bank_daily_balance"),
    )
    op.create_index("idx_bank_daily_balances_statement", "bank_daily_balances", ["statement_id"])


def downgrade() -> None:
    op.drop_table("bank_daily_balances")
    op.drop_table("bank_transactions")
    op.drop_table("bank_statements")
