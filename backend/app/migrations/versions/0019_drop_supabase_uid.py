"""Drop users.supabase_uid — auth moved from Supabase to direct Google OAuth.

Users are now identified by their app-issued JWT `sub` (users.id) and matched
at login by email, so the external auth identifier is dead weight.

Revision ID: 0019
Revises: 0018
Create Date: 2026-07-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0019"
down_revision: Union[str, None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("users", "supabase_uid")


def downgrade() -> None:
    # Restores the column (and its uniqueness) but not the old Supabase UIDs —
    # those only existed in the external Supabase project.
    op.add_column("users", sa.Column("supabase_uid", UUID(as_uuid=True), nullable=True))
    op.create_unique_constraint("users_supabase_uid_key", "users", ["supabase_uid"])
