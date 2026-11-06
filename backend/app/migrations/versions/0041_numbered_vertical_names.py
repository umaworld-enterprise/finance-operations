"""Numbered vertical names (6 Nov 2026, client request).

The 12 canonical verticals now carry the sheet's ordinal in the stored name:
"Commodity" becomes "01.Commodity". The numbering is part of the name, so it
shows wherever the vertical shows — the request form, the tables, every
export — and the list endpoint, which sorts on LOWER(name), falls into the
client's intended order for free.

This is a RENAME ONLY. No request, projection or vertical id changes hands,
so nothing needs journalling and the downgrade simply strips the prefix off
again.

Deliberately separate from 0040: staging has already applied the merge with
clean names, and keeping the rename in its own revision means 0040's journal
— and therefore its downgrade — is untouched. On a server where 0040 has yet
to run (production), the two apply back to back and land in the same place.

Revision ID: 0041
Revises: 0040
"""

import sqlalchemy as sa
from alembic import op

from app.domain.vertical_mapping import CANONICAL_VERTICALS, numbered_name

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None


def _rename(conn, frm: str, to: str) -> None:
    """Rename one vertical, unless the destination name is already taken —
    the table has a UNIQUE index on LOWER(name), and failing the whole deploy
    over a name someone typed by hand would be the worse outcome."""
    taken = conn.execute(
        sa.text("SELECT 1 FROM verticals WHERE LOWER(name) = LOWER(:n)"), {"n": to}
    ).fetchone()
    if taken:
        return
    conn.execute(
        sa.text("UPDATE verticals SET name = :to WHERE LOWER(name) = LOWER(:frm)"),
        {"to": to, "frm": frm},
    )


def upgrade() -> None:
    conn = op.get_bind()
    for bare in CANONICAL_VERTICALS:
        _rename(conn, bare, numbered_name(bare))


def downgrade() -> None:
    conn = op.get_bind()
    for bare in CANONICAL_VERTICALS:
        _rename(conn, numbered_name(bare), bare)
