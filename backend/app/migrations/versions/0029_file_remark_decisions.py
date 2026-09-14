"""File Remarks: Approve/Reject decisions (UAT change note Aug 2026, item 14).

Accounts decide each remark with Approve (processed) or Reject instead of a
single Resolve — the status CHECK widens to include the two decision values.
Existing 'resolved' rows stay valid (displayed as a legacy Resolved).

NOT amended into 0025 — migrations are never edited in place once any
environment may have run them (lesson recorded 7 Aug 2026).

Revision ID: 0029
Revises: 0028
Create Date: 2026-08-08
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0029"
down_revision: Union[str, None] = "0028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE file_remarks DROP CONSTRAINT IF EXISTS ck_file_remarks_status")
    op.execute(
        "ALTER TABLE file_remarks ADD CONSTRAINT ck_file_remarks_status "
        "CHECK (status IN ('open', 'approved', 'rejected', 'resolved'))"
    )


def downgrade() -> None:
    # Map decision rows back onto 'resolved' so the tighter CHECK can apply.
    op.execute(
        "UPDATE file_remarks SET status = 'resolved' "
        "WHERE status IN ('approved', 'rejected')"
    )
    op.execute("ALTER TABLE file_remarks DROP CONSTRAINT IF EXISTS ck_file_remarks_status")
    op.execute(
        "ALTER TABLE file_remarks ADD CONSTRAINT ck_file_remarks_status "
        "CHECK (status IN ('open', 'resolved'))"
    )
