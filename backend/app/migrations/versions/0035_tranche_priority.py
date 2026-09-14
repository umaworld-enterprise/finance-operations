"""Priority of Tranche Payment (5 Sep 2026).

``payment_tranches.priority`` — 'normal' (default) or 'high'. Chosen by the
merchandiser per tranche; displayed as a badge in the Accounts queue and the
merchandiser's pending list WITHOUT changing any ordering.

Revision ID: 0035
Revises: 0034
"""

import sqlalchemy as sa
from alembic import op

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "payment_tranches",
        sa.Column("priority", sa.String(10), nullable=False, server_default="normal"),
    )
    op.create_check_constraint(
        "ck_tranche_priority", "payment_tranches", "priority IN ('normal', 'high')"
    )


def downgrade() -> None:
    op.drop_constraint("ck_tranche_priority", "payment_tranches", type_="check")
    op.drop_column("payment_tranches", "priority")
