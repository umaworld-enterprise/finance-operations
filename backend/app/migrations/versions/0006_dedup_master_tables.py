"""Deduplicate suppliers/customers/verticals and add case-insensitive unique index.

For each table: keep the oldest row (by created_at) per name, re-point all
deposit_request FKs to the canonical row, delete duplicates, then add a
case-insensitive unique index to prevent future duplicates.

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-30
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Suppliers ──────────────────────────────────────────────────────────────
    # Re-point deposit_requests.supplier_id to canonical (oldest) row.
    # canonical CTE must SELECT name so the dupes CTE can join on it.
    op.execute("""
        WITH canonical AS (
            SELECT DISTINCT ON (LOWER(name)) id, name
            FROM suppliers
            ORDER BY LOWER(name), created_at ASC NULLS LAST
        ),
        dupes AS (
            SELECT s.id AS dupe_id, c.id AS canonical_id
            FROM suppliers s
            JOIN canonical c ON LOWER(s.name) = LOWER(c.name) AND s.id <> c.id
        )
        UPDATE deposit_requests
        SET supplier_id = d.canonical_id
        FROM dupes d
        WHERE deposit_requests.supplier_id = d.dupe_id
    """)
    # Remove defaulted_supplier rows for dupe supplier IDs before deleting the rows
    op.execute("""
        WITH canonical AS (
            SELECT DISTINCT ON (LOWER(name)) id
            FROM suppliers
            ORDER BY LOWER(name), created_at ASC NULLS LAST
        )
        DELETE FROM defaulted_suppliers
        WHERE supplier_id NOT IN (SELECT id FROM canonical)
    """)
    # Delete duplicate supplier rows
    op.execute("""
        WITH canonical AS (
            SELECT DISTINCT ON (LOWER(name)) id
            FROM suppliers
            ORDER BY LOWER(name), created_at ASC NULLS LAST
        )
        DELETE FROM suppliers WHERE id NOT IN (SELECT id FROM canonical)
    """)
    op.execute(
        "CREATE UNIQUE INDEX uq_suppliers_name_ci ON suppliers (LOWER(name))"
    )

    # ── Customers ─────────────────────────────────────────────────────────────
    op.execute("""
        WITH canonical AS (
            SELECT DISTINCT ON (LOWER(name)) id, name
            FROM customers
            ORDER BY LOWER(name), created_at ASC NULLS LAST
        ),
        dupes AS (
            SELECT c.id AS dupe_id, can.id AS canonical_id
            FROM customers c
            JOIN canonical can ON LOWER(c.name) = LOWER(can.name) AND c.id <> can.id
        )
        UPDATE deposit_requests
        SET customer_id = d.canonical_id
        FROM dupes d
        WHERE deposit_requests.customer_id = d.dupe_id
    """)
    op.execute("""
        WITH canonical AS (
            SELECT DISTINCT ON (LOWER(name)) id
            FROM customers
            ORDER BY LOWER(name), created_at ASC NULLS LAST
        )
        DELETE FROM customers WHERE id NOT IN (SELECT id FROM canonical)
    """)
    op.execute(
        "CREATE UNIQUE INDEX uq_customers_name_ci ON customers (LOWER(name))"
    )

    # ── Verticals ─────────────────────────────────────────────────────────────
    op.execute("""
        WITH canonical AS (
            SELECT DISTINCT ON (LOWER(name)) id, name
            FROM verticals
            ORDER BY LOWER(name), created_at ASC NULLS LAST
        ),
        dupes AS (
            SELECT v.id AS dupe_id, can.id AS canonical_id
            FROM verticals v
            JOIN canonical can ON LOWER(v.name) = LOWER(can.name) AND v.id <> can.id
        )
        UPDATE deposit_requests
        SET vertical_id = d.canonical_id
        FROM dupes d
        WHERE deposit_requests.vertical_id = d.dupe_id
    """)
    op.execute("""
        WITH canonical AS (
            SELECT DISTINCT ON (LOWER(name)) id
            FROM verticals
            ORDER BY LOWER(name), created_at ASC NULLS LAST
        )
        DELETE FROM verticals WHERE id NOT IN (SELECT id FROM canonical)
    """)
    op.execute(
        "CREATE UNIQUE INDEX uq_verticals_name_ci ON verticals (LOWER(name))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_verticals_name_ci")
    op.execute("DROP INDEX IF EXISTS uq_customers_name_ci")
    op.execute("DROP INDEX IF EXISTS uq_suppliers_name_ci")
