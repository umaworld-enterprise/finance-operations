-- ============================================================
-- Advance Deposit Tracker — Supabase Row Level Security Policies
-- Run this in the Supabase SQL editor AFTER running Alembic migrations
-- ============================================================

-- Enable RLS on all core tables
ALTER TABLE users                   ENABLE ROW LEVEL SECURITY;
ALTER TABLE deposit_requests        ENABLE ROW LEVEL SECURITY;
ALTER TABLE payment_details         ENABLE ROW LEVEL SECURITY;
ALTER TABLE status_history          ENABLE ROW LEVEL SECURITY;
ALTER TABLE merchandiser_actions    ENABLE ROW LEVEL SECURITY;
ALTER TABLE accounts_actions        ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs              ENABLE ROW LEVEL SECURITY;
ALTER TABLE analytics_snapshots     ENABLE ROW LEVEL SECURITY;
ALTER TABLE google_form_submissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE sync_logs               ENABLE ROW LEVEL SECURITY;
ALTER TABLE defaulted_suppliers     ENABLE ROW LEVEL SECURITY;

-- Master tables are read-only for authenticated users; write gated by API layer
ALTER TABLE verticals  ENABLE ROW LEVEL SECURITY;
ALTER TABLE customers  ENABLE ROW LEVEL SECURITY;
ALTER TABLE suppliers  ENABLE ROW LEVEL SECURITY;
ALTER TABLE system_config ENABLE ROW LEVEL SECURITY;

-- ── Helper: resolve supabase_uid → app user row ──────────────────────────────
-- NOTE: Supabase locks the auth schema; helpers live in public instead.

CREATE OR REPLACE FUNCTION public.app_role()
RETURNS TEXT AS $$
  SELECT role::TEXT FROM users WHERE supabase_uid = auth.uid() AND is_active = TRUE LIMIT 1;
$$ LANGUAGE sql STABLE SECURITY DEFINER;

CREATE OR REPLACE FUNCTION public.app_user_id()
RETURNS UUID AS $$
  SELECT id FROM users WHERE supabase_uid = auth.uid() AND is_active = TRUE LIMIT 1;
$$ LANGUAGE sql STABLE SECURITY DEFINER;

-- ── USERS ────────────────────────────────────────────────────────────────────

-- Any authenticated team member can read user list (needed for assignment dropdowns)
CREATE POLICY "users_select_authenticated"
  ON users FOR SELECT
  USING (auth.uid() IS NOT NULL);

-- Only super_admin can insert/update/delete users
CREATE POLICY "users_write_super_admin"
  ON users FOR ALL
  USING (app_role() = 'super_admin')
  WITH CHECK (app_role() = 'super_admin');

-- ── DEPOSIT REQUESTS ─────────────────────────────────────────────────────────

-- Super admin and finance_admin see all; accounts_team sees all; merchandiser sees own only
CREATE POLICY "deposit_requests_select"
  ON deposit_requests FOR SELECT
  USING (
    app_role() IN ('super_admin', 'finance_admin', 'accounts_team')
    OR (app_role() = 'merchandiser' AND created_by = app_user_id())
  );

-- Merchandiser can create; super_admin can also create
CREATE POLICY "deposit_requests_insert"
  ON deposit_requests FOR INSERT
  WITH CHECK (
    app_role() IN ('merchandiser', 'super_admin')
    AND created_by = app_user_id()
  );

-- Pre-lock: merchandiser can update own; accounts and super_admin can update any
CREATE POLICY "deposit_requests_update"
  ON deposit_requests FOR UPDATE
  USING (
    (NOT is_locked AND app_role() = 'merchandiser' AND created_by = app_user_id())
    OR (NOT is_locked AND app_role() IN ('accounts_team', 'super_admin'))
    OR (is_locked AND app_role() = 'super_admin')
  );

-- Soft delete: super_admin only (actual hard delete disabled at API layer too)
CREATE POLICY "deposit_requests_delete"
  ON deposit_requests FOR DELETE
  USING (app_role() = 'super_admin');

-- ── PAYMENT DETAILS ──────────────────────────────────────────────────────────

CREATE POLICY "payment_details_select"
  ON payment_details FOR SELECT
  USING (
    app_role() IN ('super_admin', 'finance_admin', 'accounts_team')
  );

CREATE POLICY "payment_details_write"
  ON payment_details FOR ALL
  USING (app_role() IN ('accounts_team', 'super_admin'))
  WITH CHECK (app_role() IN ('accounts_team', 'super_admin'));

-- ── STATUS HISTORY ───────────────────────────────────────────────────────────

CREATE POLICY "status_history_select"
  ON status_history FOR SELECT
  USING (
    app_role() IN ('super_admin', 'finance_admin', 'accounts_team')
    OR EXISTS (
      SELECT 1 FROM deposit_requests dr
      WHERE dr.id = status_history.deposit_request_id
        AND dr.created_by = app_user_id()
    )
  );

-- Insert via service layer only (service role bypasses RLS)
CREATE POLICY "status_history_insert_service"
  ON status_history FOR INSERT
  WITH CHECK (app_role() IN ('super_admin', 'accounts_team', 'merchandiser', 'finance_admin'));

-- ── MERCHANDISER ACTIONS ─────────────────────────────────────────────────────

CREATE POLICY "merchandiser_actions_select"
  ON merchandiser_actions FOR SELECT
  USING (app_role() IN ('super_admin', 'finance_admin', 'accounts_team', 'merchandiser'));

CREATE POLICY "merchandiser_actions_insert"
  ON merchandiser_actions FOR INSERT
  WITH CHECK (app_role() IN ('merchandiser', 'super_admin'));

-- ── ACCOUNTS ACTIONS ─────────────────────────────────────────────────────────

CREATE POLICY "accounts_actions_select"
  ON accounts_actions FOR SELECT
  USING (app_role() IN ('super_admin', 'finance_admin', 'accounts_team'));

CREATE POLICY "accounts_actions_insert"
  ON accounts_actions FOR INSERT
  WITH CHECK (app_role() IN ('accounts_team', 'super_admin'));

-- ── AUDIT LOGS ───────────────────────────────────────────────────────────────

CREATE POLICY "audit_logs_select"
  ON audit_logs FOR SELECT
  USING (app_role() IN ('super_admin', 'finance_admin'));

-- Restrict direct inserts to super_admin only until backend is wired up.
-- Backend writes audit logs via service role key (bypasses RLS entirely).
CREATE POLICY "audit_logs_insert_restricted"
  ON audit_logs FOR INSERT
  WITH CHECK (app_role() = 'super_admin');

-- ── ANALYTICS SNAPSHOTS ──────────────────────────────────────────────────────

CREATE POLICY "analytics_snapshots_select"
  ON analytics_snapshots FOR SELECT
  USING (
    app_role() IN ('super_admin', 'finance_admin', 'accounts_team', 'merchandiser')
  );

-- Upserted by service role (APScheduler job uses service key)
CREATE POLICY "analytics_snapshots_write_service"
  ON analytics_snapshots FOR ALL
  USING (app_role() IN ('super_admin', 'finance_admin'))
  WITH CHECK (app_role() IN ('super_admin', 'finance_admin'));

-- ── DEFAULTED SUPPLIERS ──────────────────────────────────────────────────────

-- All can read (used for real-time supplier validation in the form)
CREATE POLICY "defaulted_suppliers_select"
  ON defaulted_suppliers FOR SELECT
  USING (auth.uid() IS NOT NULL);

-- Finance admin and super admin manage flags
CREATE POLICY "defaulted_suppliers_write"
  ON defaulted_suppliers FOR ALL
  USING (app_role() IN ('finance_admin', 'super_admin'))
  WITH CHECK (app_role() IN ('finance_admin', 'super_admin'));

-- ── GOOGLE FORM SUBMISSIONS ──────────────────────────────────────────────────

CREATE POLICY "google_form_submissions_select"
  ON google_form_submissions FOR SELECT
  USING (app_role() IN ('super_admin', 'finance_admin'));

-- Insert handled by webhook endpoint using service role — no client insert needed

-- ── SYNC LOGS ────────────────────────────────────────────────────────────────

CREATE POLICY "sync_logs_select"
  ON sync_logs FOR SELECT
  USING (app_role() IN ('super_admin', 'finance_admin'));

-- ── MASTER TABLES (read-only via RLS; writes through API only) ───────────────

CREATE POLICY "verticals_select"
  ON verticals FOR SELECT USING (auth.uid() IS NOT NULL);

CREATE POLICY "customers_select"
  ON customers FOR SELECT USING (auth.uid() IS NOT NULL);

CREATE POLICY "suppliers_select"
  ON suppliers FOR SELECT USING (auth.uid() IS NOT NULL);

CREATE POLICY "system_config_select"
  ON system_config FOR SELECT
  USING (app_role() IN ('super_admin'));

-- ============================================================
-- Grant service role bypass for all tables (used by FastAPI)
-- The service role already bypasses RLS by default in Supabase.
-- These grants ensure the anon/authenticated roles are scoped correctly.
-- ============================================================

GRANT SELECT ON ALL TABLES IN SCHEMA public TO authenticated;
GRANT USAGE ON SCHEMA public TO authenticated;
