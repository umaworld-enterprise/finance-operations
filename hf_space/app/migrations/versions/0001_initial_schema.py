"""Initial schema — all tables and indexes.

Revision ID: 0001
Revises:
Create Date: 2026-06-20
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _exec(sql: str) -> None:
    """Execute a single DDL statement via simple query (no prepared statement)."""
    op.execute(sa.text(sql).execution_options(no_parameters=True))


def upgrade() -> None:
    # ── Enum types (DO block = idempotent; PostgreSQL has no CREATE TYPE IF NOT EXISTS) ──
    _exec("""
        DO $$ BEGIN
            CREATE TYPE user_role AS ENUM (
                'super_admin', 'finance_admin', 'accounts_team', 'merchandiser'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
    """)
    _exec("""
        DO $$ BEGIN
            CREATE TYPE request_status AS ENUM (
                'pending_payment', 'hold_by_merchandiser', 'hold_by_accounts',
                'payment_processed', 'cancelled_by_merchandiser',
                'cancelled_by_accounts', 'reopened'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
    """)
    _exec("""
        DO $$ BEGIN
            CREATE TYPE currency_code AS ENUM (
                'USD', 'EUR', 'GBP', 'AED', 'INR', 'CNY', 'JPY', 'SGD', 'OTHER'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
    """)
    _exec("""
        DO $$ BEGIN
            CREATE TYPE submission_source AS ENUM (
                'google_form', 'google_sheet_sync', 'in_app'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
    """)
    _exec("""
        DO $$ BEGIN
            CREATE TYPE sync_status AS ENUM (
                'success', 'failed', 'pending', 'retrying'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
    """)
    _exec("""
        DO $$ BEGIN
            CREATE TYPE merchandiser_action_type AS ENUM (
                'hold', 'cancel', 'resume'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
    """)
    _exec("""
        DO $$ BEGIN
            CREATE TYPE accounts_action_type AS ENUM (
                'hold', 'cancel', 'reopen'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
    """)
    _exec("""
        DO $$ BEGIN
            CREATE TYPE audit_action AS ENUM (
                'CREATE', 'UPDATE', 'DELETE', 'STATUS_CHANGE'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
    """)

    # ── Tables (CREATE TABLE IF NOT EXISTS IS valid PostgreSQL syntax) ──────────
    _exec("""
        CREATE TABLE IF NOT EXISTS verticals (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name        VARCHAR(100) NOT NULL UNIQUE,
            is_active   BOOLEAN NOT NULL DEFAULT TRUE,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    _exec("""
        CREATE TABLE IF NOT EXISTS customers (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name        VARCHAR(200) NOT NULL UNIQUE,
            is_active   BOOLEAN NOT NULL DEFAULT TRUE,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    _exec("""
        CREATE TABLE IF NOT EXISTS suppliers (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            supplier_code   VARCHAR(50) NOT NULL UNIQUE,
            name            VARCHAR(200) NOT NULL,
            country         VARCHAR(100),
            is_active       BOOLEAN NOT NULL DEFAULT TRUE,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    _exec("""
        CREATE TABLE IF NOT EXISTS users (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            supabase_uid    UUID UNIQUE,
            email           VARCHAR(255) NOT NULL UNIQUE,
            full_name       VARCHAR(200) NOT NULL,
            role            user_role NOT NULL,
            is_active       BOOLEAN NOT NULL DEFAULT TRUE,
            last_login_at   TIMESTAMPTZ,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    _exec("""
        CREATE TABLE IF NOT EXISTS system_config (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            config_key      VARCHAR(100) NOT NULL UNIQUE,
            config_value    TEXT NOT NULL,
            description     TEXT,
            updated_by      UUID REFERENCES users(id),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    _exec("""
        CREATE TABLE IF NOT EXISTS defaulted_suppliers (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            supplier_id         UUID NOT NULL REFERENCES suppliers(id),
            outstanding_amount  NUMERIC(18,2) NOT NULL,
            currency            currency_code NOT NULL DEFAULT 'USD',
            default_reason      TEXT NOT NULL,
            flagged_date        DATE NOT NULL,
            flagged_by          UUID NOT NULL REFERENCES users(id),
            resolved_date       DATE,
            resolved_by         UUID REFERENCES users(id),
            is_active           BOOLEAN NOT NULL DEFAULT TRUE,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_defaulted_supplier_active UNIQUE (supplier_id, is_active)
        )
    """)
    _exec("""
        CREATE TABLE IF NOT EXISTS deposit_requests (
            id                              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            request_number                  VARCHAR(30) NOT NULL UNIQUE,
            supplier_id                     UUID NOT NULL REFERENCES suppliers(id),
            customer_id                     UUID NOT NULL REFERENCES customers(id),
            vertical_id                     UUID NOT NULL REFERENCES verticals(id),
            supplier_invoice_number         VARCHAR(100),
            sunshine_invoice_number         VARCHAR(100),
            currency                        currency_code NOT NULL,
            exchange_rate                   NUMERIC(10,6),
            deposit_amount                  NUMERIC(18,2) NOT NULL,
            deposit_percentage              NUMERIC(5,2) NOT NULL,
            total_supplier_invoice_amount   NUMERIC(18,2) NOT NULL,
            estimated_shipment_date         DATE NOT NULL,
            estimated_etd                   DATE,
            remarks                         TEXT,
            submission_source               submission_source NOT NULL DEFAULT 'in_app',
            current_status                  request_status NOT NULL DEFAULT 'pending_payment',
            is_locked                       BOOLEAN NOT NULL DEFAULT FALSE,
            is_deleted                      BOOLEAN NOT NULL DEFAULT FALSE,
            deleted_by                      UUID REFERENCES users(id),
            deleted_at                      TIMESTAMPTZ,
            created_by                      UUID NOT NULL REFERENCES users(id),
            created_at                      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at                      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    _exec("CREATE INDEX IF NOT EXISTS idx_deposit_requests_status     ON deposit_requests(current_status)")
    _exec("CREATE INDEX IF NOT EXISTS idx_deposit_requests_supplier   ON deposit_requests(supplier_id)")
    _exec("CREATE INDEX IF NOT EXISTS idx_deposit_requests_created_by ON deposit_requests(created_by)")
    _exec("CREATE INDEX IF NOT EXISTS idx_deposit_requests_created_at ON deposit_requests(created_at DESC)")
    _exec("CREATE INDEX IF NOT EXISTS idx_deposit_requests_is_deleted ON deposit_requests(is_deleted)")
    _exec("""
        CREATE TABLE IF NOT EXISTS payment_details (
            id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            deposit_request_id       UUID NOT NULL UNIQUE REFERENCES deposit_requests(id),
            payment_date             DATE,
            bank                     VARCHAR(200),
            payment_reference_number VARCHAR(200),
            payment_status           VARCHAR(50),
            ship_date                DATE,
            accounts_remarks         TEXT,
            updated_by               UUID REFERENCES users(id),
            updated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    _exec("""
        CREATE TABLE IF NOT EXISTS status_history (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            deposit_request_id  UUID NOT NULL REFERENCES deposit_requests(id),
            old_status          request_status,
            new_status          request_status NOT NULL,
            remarks             TEXT,
            changed_by          UUID NOT NULL REFERENCES users(id),
            changed_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    _exec("CREATE INDEX IF NOT EXISTS idx_status_history_request ON status_history(deposit_request_id, changed_at DESC)")
    _exec("""
        CREATE TABLE IF NOT EXISTS merchandiser_actions (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            deposit_request_id  UUID NOT NULL REFERENCES deposit_requests(id),
            action_type         merchandiser_action_type NOT NULL,
            remarks             TEXT,
            performed_by        UUID NOT NULL REFERENCES users(id),
            performed_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    _exec("""
        CREATE TABLE IF NOT EXISTS accounts_actions (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            deposit_request_id  UUID NOT NULL REFERENCES deposit_requests(id),
            action_type         accounts_action_type NOT NULL,
            remarks             TEXT,
            performed_by        UUID NOT NULL REFERENCES users(id),
            performed_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    _exec("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            entity_name VARCHAR(100) NOT NULL,
            entity_id   UUID NOT NULL,
            field_name  VARCHAR(100),
            old_value   TEXT,
            new_value   TEXT,
            action      audit_action NOT NULL,
            changed_by  UUID NOT NULL REFERENCES users(id),
            changed_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            ip_address  INET,
            user_agent  TEXT
        )
    """)
    _exec("CREATE INDEX IF NOT EXISTS idx_audit_logs_entity ON audit_logs(entity_name, entity_id, changed_at DESC)")
    _exec("CREATE INDEX IF NOT EXISTS idx_audit_logs_user   ON audit_logs(changed_by, changed_at DESC)")
    _exec("""
        CREATE TABLE IF NOT EXISTS google_form_submissions (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            google_response_id  VARCHAR(200) UNIQUE,
            submitted_by_email  VARCHAR(255),
            submitted_at        TIMESTAMPTZ,
            raw_payload_json    JSONB NOT NULL,
            processed           BOOLEAN NOT NULL DEFAULT FALSE,
            deposit_request_id  UUID REFERENCES deposit_requests(id),
            error_message       TEXT,
            retry_count         INTEGER NOT NULL DEFAULT 0,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    _exec("""
        CREATE TABLE IF NOT EXISTS sync_logs (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            source_type      submission_source NOT NULL,
            source_reference VARCHAR(300),
            sync_status      sync_status NOT NULL,
            records_synced   INTEGER DEFAULT 0,
            error_message    TEXT,
            synced_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    _exec("""
        CREATE TABLE IF NOT EXISTS analytics_snapshots (
            id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            deposit_request_id      UUID NOT NULL UNIQUE REFERENCES deposit_requests(id),
            grace_etd               DATE,
            etd_grace_overdue_days  INTEGER,
            payment_to_ship_days    INTEGER,
            payment_to_request_days INTEGER,
            actual_etd_overdue_days INTEGER,
            cost_of_fund_applicable BOOLEAN,
            cost_of_fund_amount     NUMERIC(18,2),
            default_status          VARCHAR(50),
            calculated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    # ── updated_at trigger ────────────────────────────────────────────────────
    _exec("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)
    for table in ["verticals", "customers", "suppliers", "users", "defaulted_suppliers", "deposit_requests"]:
        _exec(f"""
            CREATE OR REPLACE TRIGGER set_updated_at
            BEFORE UPDATE ON {table}
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
        """)


def downgrade() -> None:
    for table in ["verticals", "customers", "suppliers", "users", "defaulted_suppliers", "deposit_requests"]:
        _exec(f"DROP TRIGGER IF EXISTS set_updated_at ON {table}")
    _exec("DROP FUNCTION IF EXISTS update_updated_at_column()")
    for table in [
        "analytics_snapshots", "sync_logs", "google_form_submissions",
        "audit_logs", "accounts_actions", "merchandiser_actions",
        "status_history", "payment_details", "deposit_requests",
        "defaulted_suppliers", "system_config", "users",
        "suppliers", "customers", "verticals",
    ]:
        _exec(f"DROP TABLE IF EXISTS {table}")
    for typ in [
        "audit_action", "accounts_action_type", "merchandiser_action_type",
        "sync_status", "submission_source", "currency_code", "request_status", "user_role",
    ]:
        _exec(f"DROP TYPE IF EXISTS {typ}")
