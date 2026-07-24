"""Add payment_terms_master table, widen deposit_requests.payment_terms to 200 chars, seed 34 canonical terms.

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-04
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CANONICAL_TERMS = [
    "Against BL",
    "Against BL after dispatch",
    "Against BL after Shipment",
    "Against BL Copy after loading",
    "Against Documents",
    "Against Readiness",
    "After Loading",
    "After Shipment",
    "At Arrival",
    "Before Arrival",
    "Before Delivery",
    "Before Dispatch",
    "Before Loading",
    "Before Production",
    "Before Shipment",
    "By TT",
    "DAP",
    "In Advance",
    "LC",
    "On Sample Confirmation",
    "One week before arrival",
    "10 days before arrival",
    "15 Days before arrival",
    "15 Days after arrival",
    "90 Days from BL",
    "180 Days from BL",
    "Within 7 Days of BL",
    "Within 7 Days of Signing Contract",
    "Within 10 Days of BL",
    "Within 15 Days of BL",
    "Within 20 Days of BL",
    "Within 30 Days of BL",
    "30 Days from Onboard date of BL",
    "Cash against scanned documents",
]


def upgrade() -> None:
    op.create_table(
        "payment_terms_master",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("uq_payment_terms_label_ci", "payment_terms_master", [sa.text("LOWER(label)")], unique=True)

    # Widen deposit_requests.payment_terms from VARCHAR(50) → VARCHAR(200)
    op.alter_column("deposit_requests", "payment_terms", type_=sa.String(200), existing_nullable=True)

    # Seed the 34 canonical terms
    for i, term in enumerate(CANONICAL_TERMS):
        op.execute(
            sa.text(
                "INSERT INTO payment_terms_master (label, sort_order) VALUES (:label, :sort_order)"
            ).bindparams(label=term, sort_order=i)
        )


def downgrade() -> None:
    op.drop_index("uq_payment_terms_label_ci", table_name="payment_terms_master")
    op.drop_table("payment_terms_master")
    op.alter_column("deposit_requests", "payment_terms", type_=sa.String(50), existing_nullable=True)
