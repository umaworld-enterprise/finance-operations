"""Add indexes for hot-path lookups found in the performance audit.

- merchandiser_actions.deposit_request_id / accounts_actions.deposit_request_id:
  selectinloaded on every request detail fetch — currently seq-scans.
- deposit_requests.customer_id / vertical_id: list filters with no index.
- deposit_requests.submitter_email: used in the merchandiser list OR-clause.

Revision ID: 0014
Revises: 0013a
Create Date: 2026-07-06
"""
from alembic import op

revision = "0014"
down_revision = "0013a"
branch_labels = None
depends_on = None

_INDEXES = [
    ("idx_merchandiser_actions_request", "merchandiser_actions", "deposit_request_id"),
    ("idx_accounts_actions_request", "accounts_actions", "deposit_request_id"),
    ("idx_deposit_requests_customer", "deposit_requests", "customer_id"),
    ("idx_deposit_requests_vertical", "deposit_requests", "vertical_id"),
    ("idx_deposit_requests_submitter_email", "deposit_requests", "submitter_email"),
]


def upgrade() -> None:
    for name, table, column in _INDEXES:
        op.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({column})")


def downgrade() -> None:
    for name, _table, _column in _INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {name}")
