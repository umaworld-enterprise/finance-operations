"""Replace all payment terms with the canonical 33-term list.

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-06
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TERMS = [
    "10 days before arrival",
    "15 Days after arrival",
    "15 Days before arrival",
    "180 Days from BL",
    "30 Days from Onboard date of BL",
    "90 Days from BL",
    "After Loading",
    "After Shipment",
    "Against BL",
    "Against BL after dispatch",
    "Against BL after Shipment",
    "Against BL Copy after loading",
    "Against Documents",
    "Against Rediness",
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
    "Within 10 Days of BL",
    "Within 15 Days of BL",
    "Within 20 Days of BL",
    "Within 30 Days of BL",
    "Within 7 Days of BL",
    "Within 7 Days of Signing Contract",
]


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM payment_terms_master"))
    for i, term in enumerate(TERMS, start=1):
        conn.execute(
            sa.text(
                "INSERT INTO payment_terms_master (label, is_active, sort_order) "
                "VALUES (:label, TRUE, :sort_order)"
            ),
            {"label": term, "sort_order": i},
        )


def downgrade() -> None:
    op.get_bind().execute(sa.text("DELETE FROM payment_terms_master"))
