"""One-time analytics-permissions reset (9 Sep 2026).

The 4 Sep decision opened every analytics section to every role via
DEFAULT_PERMISSIONS — but a previously saved `analytics_permissions` row in
system_config overrides the defaults, so servers configured under the old
scheme still hid sections (client report: Accounts could not see the
By Merchandiser tab). Delete the stored row once; the new all-open defaults
apply, and the Super Admin toggles keep working (saving them recreates the
row).

Revision ID: 0036
Revises: 0035
"""

from alembic import op

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DELETE FROM system_config WHERE config_key = 'analytics_permissions'")


def downgrade() -> None:
    # The previous stored value is unknown — nothing to restore. The admin
    # permission screen can recreate any restriction.
    pass
