"""Cost of Fund rate 18% -> 12% (aligned to client's sheet, verified 2026-07-10).

Guarded: only rewrites the value if it is still the old default, so a
client-customised rate is never clobbered.

Revision ID: 0017
Revises: 0016
Create Date: 2026-07-10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE system_config SET config_value = '0.12' "
            "WHERE config_key = 'cost_of_fund_rate' AND config_value = '0.18'"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE system_config SET config_value = '0.18' "
            "WHERE config_key = 'cost_of_fund_rate' AND config_value = '0.12'"
        )
    )
