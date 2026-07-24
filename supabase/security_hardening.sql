-- =============================================================================
-- Security Hardening + Analytics Recalculation
-- Run in Supabase SQL Editor (Dashboard → SQL Editor → New query)
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 0. Analytics Recalculation Function
--    Called by the frontend via supabase.rpc("recalculate_analytics").
--    SECURITY DEFINER so it can write to analytics_snapshots regardless of RLS.
--    Reads cost_of_fund_rate and etd_grace_days from system_config table
--    (falls back to 18% and 7 days if not configured).
-- -----------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION recalculate_analytics()
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
  v_rate        NUMERIC;
  v_grace_days  INTEGER;
  rec           RECORD;
  v_grace_etd             DATE;
  v_overdue_days          INTEGER;
  v_payment_to_ship       INTEGER;
  v_payment_to_request    INTEGER;
  v_actual_etd_overdue    INTEGER;
  v_cost_applicable       BOOLEAN;
  v_cost_amount           NUMERIC;
  v_default_status        TEXT;
BEGIN
  -- Load configurable values (fall back to safe defaults)
  SELECT config_value::NUMERIC INTO v_rate
    FROM system_config WHERE config_key = 'cost_of_fund_rate' LIMIT 1;
  SELECT config_value::INTEGER INTO v_grace_days
    FROM system_config WHERE config_key = 'etd_grace_days' LIMIT 1;

  v_rate       := COALESCE(v_rate, 0.18);
  v_grace_days := COALESCE(v_grace_days, 7);

  FOR rec IN
    SELECT
      dr.id,
      dr.deposit_amount,
      dr.estimated_etd,
      dr.created_at::DATE AS request_date,
      dr.current_status,
      pd.payment_date,
      pd.ship_date
    FROM deposit_requests dr
    LEFT JOIN payment_details pd ON pd.deposit_request_id = dr.id
    WHERE dr.is_deleted = FALSE
  LOOP
    -- grace_etd: estimated_etd + configured grace days
    v_grace_etd := CASE
      WHEN rec.estimated_etd IS NOT NULL
        THEN rec.estimated_etd + (v_grace_days || ' days')::INTERVAL
      ELSE NULL
    END;

    -- etd_grace_overdue_days: days past grace_etd (0 if not overdue)
    v_overdue_days := CASE
      WHEN v_grace_etd IS NULL THEN 0
      WHEN rec.ship_date IS NOT NULL THEN GREATEST(0, rec.ship_date - v_grace_etd)
      ELSE GREATEST(0, CURRENT_DATE - v_grace_etd)
    END;

    -- payment_to_ship_days: how long from payment to ship
    v_payment_to_ship := CASE
      WHEN rec.payment_date IS NOT NULL AND rec.ship_date IS NOT NULL
        THEN rec.ship_date - rec.payment_date
      ELSE NULL
    END;

    -- payment_to_request_days: how long accounts took to pay after request
    v_payment_to_request := CASE
      WHEN rec.payment_date IS NOT NULL
        THEN rec.payment_date - rec.request_date
      ELSE NULL
    END;

    -- actual_etd_overdue: ship date vs original etd (no grace)
    v_actual_etd_overdue := CASE
      WHEN rec.ship_date IS NOT NULL AND rec.estimated_etd IS NOT NULL
        THEN rec.ship_date - rec.estimated_etd
      ELSE NULL
    END;

    -- cost of fund: only when payment processed and ship date known
    IF rec.current_status = 'payment_processed' AND v_payment_to_ship IS NOT NULL AND v_payment_to_ship > 0 THEN
      v_cost_applicable := TRUE;
      v_cost_amount     := ROUND(rec.deposit_amount * v_rate * v_payment_to_ship / 365.0, 2);
    ELSE
      v_cost_applicable := FALSE;
      v_cost_amount     := 0;
    END IF;

    -- default_status classification
    v_default_status := CASE
      WHEN v_overdue_days > 14 THEN 'critical'
      WHEN v_overdue_days > 0  THEN 'delayed'
      WHEN rec.current_status = 'payment_processed' THEN 'on_time'
      ELSE 'pending'
    END;

    INSERT INTO analytics_snapshots (
      deposit_request_id,
      grace_etd,
      etd_grace_overdue_days,
      payment_to_ship_days,
      payment_to_request_days,
      actual_etd_overdue_days,
      cost_of_fund_applicable,
      cost_of_fund_amount,
      default_status,
      calculated_at
    ) VALUES (
      rec.id,
      v_grace_etd,
      v_overdue_days,
      v_payment_to_ship,
      v_payment_to_request,
      v_actual_etd_overdue,
      v_cost_applicable,
      v_cost_amount,
      v_default_status,
      NOW()
    )
    ON CONFLICT (deposit_request_id) DO UPDATE SET
      grace_etd               = EXCLUDED.grace_etd,
      etd_grace_overdue_days  = EXCLUDED.etd_grace_overdue_days,
      payment_to_ship_days    = EXCLUDED.payment_to_ship_days,
      payment_to_request_days = EXCLUDED.payment_to_request_days,
      actual_etd_overdue_days = EXCLUDED.actual_etd_overdue_days,
      cost_of_fund_applicable = EXCLUDED.cost_of_fund_applicable,
      cost_of_fund_amount     = EXCLUDED.cost_of_fund_amount,
      default_status          = EXCLUDED.default_status,
      calculated_at           = EXCLUDED.calculated_at;
  END LOOP;
END;
$$;

-- Allow any authenticated user to trigger recalculation
-- (RLS on deposit_requests still limits what data they can affect indirectly)
GRANT EXECUTE ON FUNCTION recalculate_analytics() TO authenticated;

-- -----------------------------------------------------------------------------
-- 1. Request Number Sequence
--    Replaces Math.random() on the frontend with a collision-free DB sequence.
--    Frontend calls: supabase.rpc("next_request_number")
-- -----------------------------------------------------------------------------

CREATE SEQUENCE IF NOT EXISTS deposit_request_seq START 1;

CREATE OR REPLACE FUNCTION next_request_number()
RETURNS TEXT
LANGUAGE sql
SECURITY DEFINER
AS $$
  SELECT 'ADT-' || EXTRACT(YEAR FROM NOW())::TEXT || '-' || LPAD(nextval('deposit_request_seq')::TEXT, 5, '0');
$$;

-- Grant execute to authenticated users (RLS on deposit_requests still controls insert)
GRANT EXECUTE ON FUNCTION next_request_number() TO authenticated;


-- -----------------------------------------------------------------------------
-- 2. Status Transition Trigger
--    Enforces the valid state machine at the database level.
--    Invalid transitions raise an exception and abort the write, regardless
--    of whether the request came from the frontend or backend.
-- -----------------------------------------------------------------------------

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
    -- HOM workflow (added migration 0012)
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

-- Drop and recreate to avoid duplicate trigger errors on re-run
DROP TRIGGER IF EXISTS trg_enforce_status_transition ON deposit_requests;

CREATE TRIGGER trg_enforce_status_transition
  BEFORE UPDATE OF current_status ON deposit_requests
  FOR EACH ROW
  EXECUTE FUNCTION enforce_status_transition();


-- -----------------------------------------------------------------------------
-- 3. Audit Logs RLS Policy Update
--    (Idempotent version — safe to run if rls_policies.sql was already applied)
-- -----------------------------------------------------------------------------

DROP POLICY IF EXISTS "audit_logs_insert_service" ON audit_logs;
DROP POLICY IF EXISTS "audit_logs_insert_restricted" ON audit_logs;

CREATE POLICY "audit_logs_insert_restricted"
  ON audit_logs FOR INSERT
  WITH CHECK (app_role() = 'super_admin');
