"""Align file_remarks with the 4 Aug rework — idempotent.

Migration 0025 was amended in place during development (amount columns,
split_targets JSON, remark nullable, two-category CHECK), but at least one
environment had already run the ORIGINAL 0025 and recorded it as applied —
its table lacks the new columns (UndefinedColumnError: old_amount on
INSERT). This migration reconciles ANY state to the final schema:

- DBs that ran the original 0025: gain the three columns, remark relaxed,
  categories normalised, CHECK replaced.
- DBs that ran the amended 0025 (or fresh DBs): every statement no-ops.

Revision ID: 0027
Revises: 0026
Create Date: 2026-08-07
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0027"
down_revision: Union[str, None] = "0026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE file_remarks ADD COLUMN IF NOT EXISTS old_amount NUMERIC(18, 2)")
    op.execute("ALTER TABLE file_remarks ADD COLUMN IF NOT EXISTS new_amount NUMERIC(18, 2)")
    op.execute("ALTER TABLE file_remarks ADD COLUMN IF NOT EXISTS split_targets JSON")
    # Remark became optional (no error if already nullable).
    op.execute("ALTER TABLE file_remarks ALTER COLUMN remark DROP NOT NULL")
    # Normalise any rows created under the original three-category scheme so
    # the tighter CHECK below can be applied.
    op.execute(
        "UPDATE file_remarks SET category = 'invoice_amount_change' "
        "WHERE category IN ('invoice_number_change', 'other')"
    )
    op.execute("ALTER TABLE file_remarks DROP CONSTRAINT IF EXISTS ck_file_remarks_category")
    op.execute(
        "ALTER TABLE file_remarks ADD CONSTRAINT ck_file_remarks_category "
        "CHECK (category IN ('invoice_split', 'invoice_amount_change'))"
    )


def downgrade() -> None:
    # Best-effort: restore the original three-category CHECK. The added
    # columns are kept (dropping them would destroy data) and remark stays
    # nullable — stated here rather than pretending to a clean reversal.
    op.execute("ALTER TABLE file_remarks DROP CONSTRAINT IF EXISTS ck_file_remarks_category")
    op.execute(
        "ALTER TABLE file_remarks ADD CONSTRAINT ck_file_remarks_category "
        "CHECK (category IN ('invoice_number_change', 'invoice_split', 'other'))"
    )
