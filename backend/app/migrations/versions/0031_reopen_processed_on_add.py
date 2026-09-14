"""Reopen a payment-processed request by adding a tranche (19 Aug 2026).

Adds the 'payment_processed' → 'pending_payment' transition, fired when the
merchandiser adds a tranche to a completed file: the request returns to the
payment queue for the additional amount (capped at the invoice total) and
completes again once the new tranches are paid. No new enum values.

Status rules live in three places and all change together with this
migration: app/models/enums.py (unchanged here), app/domain/rules/
status_transitions.py and the trigger function below.

Revision ID: 0031
Revises: 0030
Create Date: 2026-08-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0031"
down_revision: Union[str, None] = "0030"
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
    ('payment_processed',       'pending_payment'),
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

# Downgrade restores the 0028 function body (without the reopen transition).
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


def upgrade() -> None:
    op.get_bind().execute(sa.text(_TRIGGER_SQL))


def downgrade() -> None:
    op.get_bind().execute(sa.text(_DOWNGRADE_TRIGGER_SQL))
