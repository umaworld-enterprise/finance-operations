"""Vertical master clean-up (5 Nov 2026, client request).

26 accumulated categories collapse into the 12 canonical verticals defined
in ``app/domain/vertical_mapping.py``. Live data is repointed, not dropped:

  * every ``deposit_requests.vertical_id`` moves to its canonical vertical;
  * projections move too, and where a merge would put two projections on the
    same (vertical, year, month) — which the unique constraint forbids —
    their USD/EUR/CNY amounts are SUMMED into the survivor (client decision);
  * "Forwarder Expense" is retired: stragglers move to Sundry, then the row
    goes;
  * verticals not named in the mapping are left completely alone.

REVERSIBILITY: every change is journalled into ``vertical_merge_journal_0040``
(old vertical rows, every repointed request/projection, every merged-away
projection with its amounts, and the ids of verticals this migration
created). The downgrade replays that journal, so the merge is genuinely
undoable — including the summed projections.

GATED ON PRODUCTION ONLY: deploy.sh applies migrations automatically, so
on production this refuses to run unless VERTICAL_MERGE_CONFIRM=1 is set.
Staging and development apply it normally — testing the merge there is the
point. See the safety catch in upgrade().

Revision ID: 0040
Revises: 0039
"""

import json
import os

import sqlalchemy as sa
from alembic import op

from app.domain.vertical_mapping import (
    CANONICAL_VERTICALS,
    RETIRED_VERTICALS,
    VERTICAL_MERGE_MAP,
)

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None

JOURNAL = "vertical_merge_journal_0040"


def _journal(conn, kind: str, payload: dict) -> None:
    conn.execute(
        sa.text(f"INSERT INTO {JOURNAL} (kind, payload) VALUES (:k, CAST(:p AS JSONB))"),
        {"k": kind, "p": json.dumps(payload, default=str)},
    )


CONFIRM_ENV = "VERTICAL_MERGE_CONFIRM"


def upgrade() -> None:
    conn = op.get_bind()

    # SAFETY CATCH (5 Nov 2026), PRODUCTION ONLY. deploy.sh runs
    # `alembic upgrade head` automatically, so on production a routine deploy
    # would otherwise rewrite the vertical of every live request before
    # anyone had seen the dry run. Staging and development run it freely —
    # trying the merge there is the whole point of having a staging stack.
    # Refusing is the safe failure: the deploy stops and the previous
    # containers keep serving.
    app_env = os.getenv("APP_ENV", "development").strip().lower()
    confirmed = os.getenv(CONFIRM_ENV, "").strip().lower() in {"1", "true", "yes"}
    if app_env == "production" and not confirmed:
        raise RuntimeError(
            "Migration 0040 merges 26 verticals into 12 and REWRITES the "
            "vertical of every affected request and projection.\n"
            "On PRODUCTION it is held back until you confirm it deliberately:\n"
            "  1. Review the dry run:  python scripts/preview_vertical_merge.py\n"
            "  2. Take a database backup.\n"
            f"  3. Re-run the deploy with {CONFIRM_ENV}=1 set for the backend.\n"
            "Staging applies it automatically; every other migration is "
            "unaffected."
        )

    op.create_table(
        JOURNAL,
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("payload", sa.dialects.postgresql.JSONB, nullable=False),
    )

    # ── 1. Resolve or create the 12 canonical verticals ──────────────────
    # An existing row whose name already matches a canonical name is reused
    # (the unique index on LOWER(name) would reject a duplicate anyway).
    canonical_ids: dict[str, str] = {}
    for name in CANONICAL_VERTICALS:
        row = conn.execute(
            sa.text("SELECT id FROM verticals WHERE LOWER(name) = LOWER(:n)"), {"n": name}
        ).fetchone()
        if row:
            canonical_ids[name] = str(row[0])
            # Make sure a survivor is active and spelled canonically.
            conn.execute(
                sa.text("UPDATE verticals SET name = :n, is_active = TRUE WHERE id = :i"),
                {"n": name, "i": row[0]},
            )
        else:
            new_id = conn.execute(
                sa.text(
                    "INSERT INTO verticals (id, name, is_active) "
                    "VALUES (gen_random_uuid(), :n, TRUE) RETURNING id"
                ),
                {"n": name},
            ).scalar_one()
            canonical_ids[name] = str(new_id)
            _journal(conn, "created_vertical", {"id": str(new_id), "name": name})

    # ── 2. Merge every source vertical into its target ───────────────────
    for source, target in {**VERTICAL_MERGE_MAP, **RETIRED_VERTICALS}.items():
        src = conn.execute(
            sa.text(
                "SELECT id, name, is_active, assigned_user_id FROM verticals "
                "WHERE LOWER(name) = LOWER(:n)"
            ),
            {"n": source},
        ).fetchone()
        if src is None:
            continue                                  # not present on this server
        src_id = str(src[0])
        dst_id = canonical_ids[target]
        if src_id == dst_id:
            continue                                  # already the canonical row

        _journal(conn, "vertical", {
            "id": src_id, "name": src[1], "is_active": bool(src[2]),
            "assigned_user_id": str(src[3]) if src[3] else None,
        })

        # 2a. Requests — journal each one, then repoint.
        for (req_id,) in conn.execute(
            sa.text("SELECT id FROM deposit_requests WHERE vertical_id = :s"), {"s": src_id}
        ).fetchall():
            _journal(conn, "request", {"id": str(req_id), "old_vertical_id": src_id})
        conn.execute(
            sa.text("UPDATE deposit_requests SET vertical_id = :d WHERE vertical_id = :s"),
            {"d": dst_id, "s": src_id},
        )

        # 2b. Projections — a clash on (vertical, year, month) is summed into
        #     the survivor; the absorbed row is journalled in full so the
        #     downgrade can restore it and subtract again.
        for row in conn.execute(
            sa.text(
                "SELECT id, year, month, amount_usd, amount_eur, amount_cny, "
                "       user_id, submitted_by "
                "FROM projections WHERE vertical_id = :s"
            ),
            {"s": src_id},
        ).fetchall():
            clash = conn.execute(
                sa.text(
                    "SELECT id FROM projections "
                    "WHERE vertical_id = :d AND year = :y AND month = :m"
                ),
                {"d": dst_id, "y": row[1], "m": row[2]},
            ).fetchone()
            if clash:
                _journal(conn, "projection_absorbed", {
                    "id": str(row[0]), "into_id": str(clash[0]),
                    "old_vertical_id": src_id, "year": row[1], "month": row[2],
                    "amount_usd": str(row[3]), "amount_eur": str(row[4]),
                    "amount_cny": str(row[5]),
                    "user_id": str(row[6]), "submitted_by": str(row[7]),
                })
                conn.execute(
                    sa.text(
                        "UPDATE projections SET "
                        "  amount_usd = amount_usd + :u, "
                        "  amount_eur = amount_eur + :e, "
                        "  amount_cny = amount_cny + :c "
                        "WHERE id = :i"
                    ),
                    {"u": row[3], "e": row[4], "c": row[5], "i": clash[0]},
                )
                conn.execute(
                    sa.text("DELETE FROM projections WHERE id = :i"), {"i": row[0]}
                )
            else:
                _journal(conn, "projection", {
                    "id": str(row[0]), "old_vertical_id": src_id,
                })
                conn.execute(
                    sa.text("UPDATE projections SET vertical_id = :d WHERE id = :i"),
                    {"d": dst_id, "i": row[0]},
                )

        conn.execute(sa.text("DELETE FROM verticals WHERE id = :i"), {"i": src_id})


def downgrade() -> None:
    conn = op.get_bind()

    rows = conn.execute(
        sa.text(f"SELECT kind, payload FROM {JOURNAL} ORDER BY id DESC")
    ).fetchall()

    # Recreate the merged-away verticals first, with their original ids.
    for kind, p in rows:
        if kind == "vertical":
            conn.execute(
                sa.text(
                    "INSERT INTO verticals (id, name, is_active, assigned_user_id) "
                    "VALUES (CAST(:i AS UUID), :n, :a, CAST(:u AS UUID)) "
                    "ON CONFLICT (id) DO NOTHING"
                ),
                {"i": p["id"], "n": p["name"], "a": p["is_active"],
                 "u": p.get("assigned_user_id")},
            )

    for kind, p in rows:
        if kind == "request":
            conn.execute(
                sa.text(
                    "UPDATE deposit_requests SET vertical_id = CAST(:v AS UUID) WHERE id = CAST(:i AS UUID)"
                ),
                {"v": p["old_vertical_id"], "i": p["id"]},
            )
        elif kind == "projection":
            conn.execute(
                sa.text(
                    "UPDATE projections SET vertical_id = CAST(:v AS UUID) WHERE id = CAST(:i AS UUID)"
                ),
                {"v": p["old_vertical_id"], "i": p["id"]},
            )
        elif kind == "projection_absorbed":
            # Take the summed amounts back out, then restore the absorbed row.
            conn.execute(
                sa.text(
                    "UPDATE projections SET "
                    "  amount_usd = amount_usd - CAST(:u AS NUMERIC), "
                    "  amount_eur = amount_eur - CAST(:e AS NUMERIC), "
                    "  amount_cny = amount_cny - CAST(:c AS NUMERIC) "
                    "WHERE id = CAST(:i AS UUID)"
                ),
                {"u": p["amount_usd"], "e": p["amount_eur"], "c": p["amount_cny"],
                 "i": p["into_id"]},
            )
            conn.execute(
                sa.text(
                    "INSERT INTO projections (id, vertical_id, user_id, year, month, "
                    "  amount_usd, amount_eur, amount_cny, submitted_by) "
                    "VALUES (CAST(:i AS UUID), CAST(:v AS UUID), CAST(:usr AS UUID), :y, :m, "
                    "  CAST(:au AS NUMERIC), CAST(:ae AS NUMERIC), CAST(:ac AS NUMERIC), "
                    "  CAST(:sb AS UUID)) ON CONFLICT (id) DO NOTHING"
                ),
                {"i": p["id"], "v": p["old_vertical_id"], "usr": p["user_id"],
                 "y": p["year"], "m": p["month"], "au": p["amount_usd"],
                 "ae": p["amount_eur"], "ac": p["amount_cny"], "sb": p["submitted_by"]},
            )

    # Finally drop the verticals this migration invented (they can only be
    # unreferenced by now, since everything above was repointed back).
    for kind, p in rows:
        if kind == "created_vertical":
            conn.execute(
                sa.text("DELETE FROM verticals WHERE id = CAST(:i AS UUID)"), {"i": p["id"]}
            )

    op.drop_table(JOURNAL)
