"""Re-run supplier dedup preferring is_active=TRUE rows as canonical.

Migration 0006 selected the canonical row purely by oldest created_at,
which may have kept an is_active=FALSE row and deleted the active one.
This migration drops and recreates the unique index, then repeats the
dedup with active rows preferred over inactive ones of the same name.

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-02
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the index created by 0006 so we can safely re-dedup.
    op.execute("DROP INDEX IF EXISTS uq_suppliers_name_ci")

    # Choose canonical row: prefer is_active=TRUE, then oldest created_at.
    # Re-point FKs on deposit_requests before deleting dupes.
    op.execute("""
        WITH canonical AS (
            SELECT DISTINCT ON (LOWER(name)) id, name
            FROM suppliers
            ORDER BY LOWER(name),
                     (CASE WHEN is_active THEN 0 ELSE 1 END) ASC,
                     created_at ASC NULLS LAST
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

    # Clean up defaulted_suppliers rows that reference about-to-be-deleted dupes.
    op.execute("""
        WITH canonical AS (
            SELECT DISTINCT ON (LOWER(name)) id
            FROM suppliers
            ORDER BY LOWER(name),
                     (CASE WHEN is_active THEN 0 ELSE 1 END) ASC,
                     created_at ASC NULLS LAST
        )
        DELETE FROM defaulted_suppliers
        WHERE supplier_id NOT IN (SELECT id FROM canonical)
    """)

    # Delete the non-canonical supplier rows.
    op.execute("""
        WITH canonical AS (
            SELECT DISTINCT ON (LOWER(name)) id
            FROM suppliers
            ORDER BY LOWER(name),
                     (CASE WHEN is_active THEN 0 ELSE 1 END) ASC,
                     created_at ASC NULLS LAST
        )
        DELETE FROM suppliers WHERE id NOT IN (SELECT id FROM canonical)
    """)

    # Recreate the unique index.
    op.execute(
        "CREATE UNIQUE INDEX uq_suppliers_name_ci ON suppliers (LOWER(name))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_suppliers_name_ci")
