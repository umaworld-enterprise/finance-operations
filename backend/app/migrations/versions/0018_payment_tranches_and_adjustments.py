"""Advance Payment Tranches and Invoice Adjustments.

- payment_tranches: one or more tranches per deposit request (Tranche I, II, …)
  with amount, tentative payment date, tranche-level paid state and TT copy.
- invoice_adjustments: additive, linked reallocations from a paid tranche to a
  tranche on another invoice of the same supplier. Carries an approval-ready
  status enum (created as 'completed' today — approval flow is an open
  business decision).
- Backfill: every existing request with a positive deposit_amount gets one
  legacy Tranche 1 covering the full requested amount. Requests already in
  payment_processed get the tranche marked paid, carrying over payment date /
  actor from payment_details where available. Historical payment_terms data
  stays untouched on deposit_requests (read-only compatibility).

Revision ID: 0018
Revises: 0017
Create Date: 2026-07-28
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE TYPE tranche_status AS ENUM ('unpaid', 'paid')")
    op.execute(
        "CREATE TYPE adjustment_status AS ENUM ('completed', 'pending_approval', 'rejected')"
    )

    op.create_table(
        "payment_tranches",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("deposit_request_id", sa.UUID(as_uuid=True), sa.ForeignKey("deposit_requests.id"), nullable=False),
        sa.Column("tranche_number", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("tentative_payment_date", sa.Date(), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM("unpaid", "paid", name="tranche_status", create_type=False),
            nullable=False,
            server_default="unpaid",
        ),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_by", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("tt_copy_url", sa.String(1024), nullable=True),
        sa.Column("tt_copy_file_id", sa.String(128), nullable=True),
        sa.Column("tt_copy_filename", sa.String(255), nullable=True),
        sa.Column("is_legacy", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("deposit_request_id", "tranche_number", name="uq_tranche_request_number"),
        sa.CheckConstraint("amount > 0", name="ck_tranche_amount_positive"),
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_payment_tranches_request ON payment_tranches (deposit_request_id)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_payment_tranches_status ON payment_tranches (status)")

    op.create_table(
        "invoice_adjustments",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("source_tranche_id", sa.UUID(as_uuid=True), sa.ForeignKey("payment_tranches.id"), nullable=False),
        sa.Column("destination_tranche_id", sa.UUID(as_uuid=True), sa.ForeignKey("payment_tranches.id"), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "completed", "pending_approval", "rejected",
                name="adjustment_status", create_type=False,
            ),
            nullable=False,
            server_default="completed",
        ),
        sa.Column("performed_by", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("amount > 0", name="ck_adjustment_amount_positive"),
        sa.CheckConstraint(
            "source_tranche_id != destination_tranche_id", name="ck_adjustment_distinct_tranches"
        ),
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_invoice_adjustments_source ON invoice_adjustments (source_tranche_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_invoice_adjustments_destination ON invoice_adjustments (destination_tranche_id)"
    )

    # ── Backfill: one legacy tranche per existing request ─────────────────────
    # Paid state mirrors the request-level model this migration replaces:
    # payment_processed → paid. paid_at prefers the recorded payment_date,
    # falling back to when the payment row was last touched. Requests with a
    # non-positive deposit_amount (none expected — the API enforces > 0) are
    # skipped rather than violating ck_tranche_amount_positive.
    op.execute(
        """
        INSERT INTO payment_tranches (
            deposit_request_id, tranche_number, amount, tentative_payment_date,
            status, paid_at, paid_by, is_legacy, created_at, updated_at
        )
        SELECT
            dr.id,
            1,
            dr.deposit_amount,
            NULL,
            CASE WHEN dr.current_status = 'payment_processed'
                 THEN 'paid'::tranche_status ELSE 'unpaid'::tranche_status END,
            CASE WHEN dr.current_status = 'payment_processed'
                 THEN COALESCE(pd.payment_date::timestamptz, pd.updated_at, dr.updated_at)
                 ELSE NULL END,
            CASE WHEN dr.current_status = 'payment_processed' THEN pd.updated_by ELSE NULL END,
            TRUE,
            now(),
            now()
        FROM deposit_requests dr
        LEFT JOIN payment_details pd ON pd.deposit_request_id = dr.id
        WHERE dr.deposit_amount > 0
        """
    )


def downgrade() -> None:
    op.drop_table("invoice_adjustments")
    op.drop_table("payment_tranches")
    op.execute("DROP TYPE IF EXISTS adjustment_status")
    op.execute("DROP TYPE IF EXISTS tranche_status")
