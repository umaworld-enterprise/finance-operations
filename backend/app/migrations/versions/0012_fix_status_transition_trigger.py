"""Add HOM transitions to the DB-level status transition trigger.

Migration 0010 added pending_hom_approval to the request_status enum and
Python-level transition rules, but the PostgreSQL trigger function
enforce_status_transition() was not updated. This migration replaces the
function body to allow the three HOM transitions.

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-06
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_UPGRADE_SQL = """
CREATE OR REPLACE FUNCTION enforce_status_transition()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  -- No-op if status is not changing
  IF OLD.current_status = NEW.current_status THEN
    RETURN NEW;
  END IF;

  -- Validate against the allowed transition table
  IF NOT (OLD.current_status::TEXT, NEW.current_status::TEXT) IN (
    ('pending_payment',         'hold_by_merchandiser'),
    ('pending_payment',         'cancelled_by_merchandiser'),
    ('pending_payment',         'hold_by_accounts'),
    ('pending_payment',         'payment_processed'),
    ('hold_by_merchandiser',    'pending_payment'),
    ('hold_by_merchandiser',    'cancelled_by_merchandiser'),
    ('hold_by_accounts',        'pending_payment'),
    ('hold_by_accounts',        'cancelled_by_accounts'),
    ('cancelled_by_accounts',   'reopened'),
    ('reopened',                'pending_payment'),
    ('pending_hom_approval',    'pending_payment'),
    ('pending_hom_approval',    'rejected_by_hom'),
    ('pending_hom_approval',    'cancelled_by_merchandiser')
  ) THEN
    RAISE EXCEPTION 'Invalid status transition: % → %', OLD.current_status, NEW.current_status
      USING ERRCODE = 'P0001';
  END IF;

  RETURN NEW;
END;
$$;
"""

# Downgrade restores the original 10-transition version (pre-HOM).
_DOWNGRADE_SQL = """
CREATE OR REPLACE FUNCTION enforce_status_transition()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  IF OLD.current_status = NEW.current_status THEN
    RETURN NEW;
  END IF;

  IF NOT (OLD.current_status::TEXT, NEW.current_status::TEXT) IN (
    ('pending_payment',        'hold_by_merchandiser'),
    ('pending_payment',        'cancelled_by_merchandiser'),
    ('pending_payment',        'hold_by_accounts'),
    ('pending_payment',        'payment_processed'),
    ('hold_by_merchandiser',   'pending_payment'),
    ('hold_by_merchandiser',   'cancelled_by_merchandiser'),
    ('hold_by_accounts',       'pending_payment'),
    ('hold_by_accounts',       'cancelled_by_accounts'),
    ('cancelled_by_accounts',  'reopened'),
    ('reopened',               'pending_payment')
  ) THEN
    RAISE EXCEPTION 'Invalid status transition: % → %', OLD.current_status, NEW.current_status
      USING ERRCODE = 'P0001';
  END IF;

  RETURN NEW;
END;
$$;
"""


def upgrade() -> None:
    op.get_bind().execute(sa.text(_UPGRADE_SQL))


def downgrade() -> None:
    op.get_bind().execute(sa.text(_DOWNGRADE_SQL))
