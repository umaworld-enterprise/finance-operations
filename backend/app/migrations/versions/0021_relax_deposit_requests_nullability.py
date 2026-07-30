"""Relax deposit_requests NOT NULL constraints that don't match the ORM model.

0001's raw-SQL CREATE TABLE declared vertical_id, deposit_percentage, and
estimated_shipment_date as NOT NULL, but the ORM model (and real production
data on Supabase) has always treated them as nullable — e.g. a vertical is
optional, and estimated_shipment_date is filled in later in the workflow.
A fresh database following the migration chain rejects rows Supabase already
has (UndefinedColumnError's sibling: NotNullViolation).

Revision ID: 0021
Revises: 0020
Create Date: 2026-07-30
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0021"
down_revision: Union[str, None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLUMNS = ["vertical_id", "deposit_percentage", "estimated_shipment_date"]


def upgrade() -> None:
    for column in _COLUMNS:
        op.alter_column("deposit_requests", column, nullable=True)


def downgrade() -> None:
    for column in _COLUMNS:
        op.alter_column("deposit_requests", column, nullable=False)
