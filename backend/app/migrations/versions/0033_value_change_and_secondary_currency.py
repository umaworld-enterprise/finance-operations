"""Invoice Value Change remarks + tranche secondary currency (4 Sep 2026).

Two client changes in one deploy:

1. File Remarks gains a third category, ``invoice_value_change`` — the
   merchandiser proposes a revised invoice amount (stored in the new
   ``proposed_amount`` column); Accounts approve, then apply the final
   revised amount into ``new_amount`` as a separate step. The category CHECK
   constraint is widened accordingly.

2. ``payment_tranches`` gains optional ``secondary_currency`` /
   ``secondary_amount`` — Accounts-entered alongside the payment details.

Revision ID: 0033
Revises: 0032
"""

import sqlalchemy as sa
from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None

_OLD_CATEGORIES = "('invoice_split', 'invoice_amount_change')"
_NEW_CATEGORIES = "('invoice_split', 'invoice_amount_change', 'invoice_value_change')"


def upgrade() -> None:
    op.add_column(
        "file_remarks",
        sa.Column("proposed_amount", sa.Numeric(18, 2), nullable=True),
    )
    op.drop_constraint("ck_file_remarks_category", "file_remarks", type_="check")
    op.create_check_constraint(
        "ck_file_remarks_category", "file_remarks", f"category IN {_NEW_CATEGORIES}"
    )

    op.add_column(
        "payment_tranches",
        sa.Column("secondary_currency", sa.String(8), nullable=True),
    )
    op.add_column(
        "payment_tranches",
        sa.Column("secondary_amount", sa.Numeric(18, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("payment_tranches", "secondary_amount")
    op.drop_column("payment_tranches", "secondary_currency")

    # Rows of the new category cannot satisfy the old CHECK — remove them
    # before restoring it (they only exist if the feature was used).
    op.execute("DELETE FROM file_remarks WHERE category = 'invoice_value_change'")
    op.drop_constraint("ck_file_remarks_category", "file_remarks", type_="check")
    op.create_check_constraint(
        "ck_file_remarks_category", "file_remarks", f"category IN {_OLD_CATEGORIES}"
    )
    op.drop_column("file_remarks", "proposed_amount")
