"""Request-level rejection by Accounts (UAT change note Aug 2026, items 12/17/18).

Adds the 'rejected_by_accounts' request status — a terminal state entered by
Accounts with a mandatory reason — plus the 'reject' accounts action type,
and rebuilds enforce_status_transition() to allow the two new transitions
(from pending_payment and from hold_by_accounts).

Status rules live in three places and all change together with this
migration: app/models/enums.py, app/domain/rules/status_transitions.py and
the trigger function below.

Revision ID: 0028
Revises: 0027
Create Date: 2026-08-08
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0028"
down_revision: Union[str, None] = "0027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TRIGGER_SQL = """
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
    ('pending_payment',         'rejected_by_accounts'),
    ('hold_by_merchandiser',    'pending_payment'),
    ('hold_by_merchandiser',    'cancelled_by_merchandiser'),
    ('hold_by_accounts',        'pending_payment'),
    ('hold_by_accounts',        'cancelled_by_accounts'),
    ('hold_by_accounts',        'rejected_by_accounts'),
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

# Downgrade restores the 0012 function body (without the two new transitions).
_DOWNGRADE_TRIGGER_SQL = """
CREATE OR REPLACE FUNCTION enforce_status_transition()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  IF OLD.current_status = NEW.current_status THEN
    RETURN NEW;
  END IF;

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


def upgrade() -> None:
    conn = op.get_bind()
    # ALTER TYPE ... ADD VALUE cannot run inside an open transaction
    # (pattern from 0013); IF NOT EXISTS makes re-runs safe.
    conn.execute(sa.text("COMMIT"))
    conn.execute(sa.text(
        "ALTER TYPE request_status ADD VALUE IF NOT EXISTS 'rejected_by_accounts'"
    ))
    conn.execute(sa.text(
        "ALTER TYPE accounts_action_type ADD VALUE IF NOT EXISTS 'reject'"
    ))
    conn.execute(sa.text(_TRIGGER_SQL))


def downgrade() -> None:
    # PostgreSQL cannot remove enum values — 'rejected_by_accounts' and
    # 'reject' remain as harmless unused labels. The trigger reverts, so the
    # transitions become impossible again.
    op.get_bind().execute(sa.text(_DOWNGRADE_TRIGGER_SQL))
