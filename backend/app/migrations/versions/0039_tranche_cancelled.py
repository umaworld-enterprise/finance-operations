"""Merchandiser can CANCEL a tranche (5 Nov 2026).

Delete already existed but removes the row entirely and is refused once
Accounts have touched the tranche. Cancel keeps the row visible with a
reason, drops it out of the payment queue and stops it counting toward the
deposit total — the same treatment a REJECTED tranche gets, but raised from
the merchandiser's side.

Adds 'cancelled' to the tranche_status enum. ALTER TYPE ... ADD VALUE cannot
run inside the migration's transaction, hence the autocommit block.

Revision ID: 0039
Revises: 0038
"""

from alembic import op

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE tranche_status ADD VALUE IF NOT EXISTS 'cancelled'")


def downgrade() -> None:
    # Postgres cannot drop a single enum value, so the type is rebuilt.
    # Cancelled tranches become REJECTED: both are non-counting, record-kept
    # states, so totals and ceilings are unaffected by the move.
    op.execute("UPDATE payment_tranches SET status = 'rejected' WHERE status = 'cancelled'")
    op.execute("ALTER TYPE tranche_status RENAME TO tranche_status_old")
    op.execute("CREATE TYPE tranche_status AS ENUM ('unpaid', 'paid', 'rejected')")
    op.execute(
        "ALTER TABLE payment_tranches "
        "ALTER COLUMN status TYPE tranche_status "
        "USING status::text::tranche_status"
    )
    op.execute("DROP TYPE tranche_status_old")
