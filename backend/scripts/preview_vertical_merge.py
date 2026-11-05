"""Dry-run the vertical master clean-up (migration 0040).

Reports exactly what the merge WILL do against the live database — how many
requests and projections move, which projections would be summed, which
verticals disappear, and anything the mapping does not cover — and changes
nothing. Run this before `alembic upgrade head`.

    python scripts/preview_vertical_merge.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from app.core.database import AsyncSessionFactory  # noqa: E402
from app.domain.vertical_mapping import (  # noqa: E402
    CANONICAL_VERTICALS,
    RETIRED_VERTICALS,
    VERTICAL_MERGE_MAP,
    canonical_for,
)


async def main() -> int:
    async with AsyncSessionFactory() as s:
        rows = (await s.execute(text(
            "SELECT v.id, v.name, v.is_active,"
            "  (SELECT COUNT(*) FROM deposit_requests d WHERE d.vertical_id = v.id) AS reqs,"
            "  (SELECT COUNT(*) FROM projections p WHERE p.vertical_id = v.id) AS projs "
            "FROM verticals v ORDER BY LOWER(v.name)"
        ))).fetchall()

        print(f"\n{len(rows)} verticals in the database\n")
        print(f"{'EXISTING':<34} {'→ CANONICAL':<20} {'REQUESTS':>9} {'PROJ':>6}")
        print("-" * 74)

        moving_reqs = moving_projs = 0
        unmapped: list[tuple[str, int, int]] = []
        by_target: dict[str, list[str]] = {}

        for _id, name, _active, reqs, projs in rows:
            target = canonical_for(name)
            if target is None:
                unmapped.append((name, reqs, projs))
                print(f"{name:<34} {'— not in mapping —':<20} {reqs:>9} {projs:>6}")
                continue
            by_target.setdefault(target, []).append(name)
            same = name.strip().casefold() == target.casefold()
            if not same:
                moving_reqs += reqs
                moving_projs += projs
            print(f"{name:<34} {('(stays) ' + target) if same else ('→ ' + target):<20} {reqs:>9} {projs:>6}")

        # Projection clashes: two sources holding the same period for one target.
        print("\nProjection periods that would be SUMMED on merge:")
        clashes = (await s.execute(text(
            "SELECT v.name, p.year, p.month, COUNT(*) "
            "FROM projections p JOIN verticals v ON v.id = p.vertical_id "
            "GROUP BY v.name, p.year, p.month"
        ))).fetchall()
        grouped: dict[tuple[str, int, int], int] = {}
        for vname, year, month, _n in clashes:
            target = canonical_for(vname)
            if target is None:
                continue
            grouped[(target, year, month)] = grouped.get((target, year, month), 0) + 1
        summed = {k: v for k, v in grouped.items() if v > 1}
        if summed:
            for (target, year, month), n in sorted(summed.items()):
                print(f"  {target} {year}-{month:02d}: {n} rows → 1 (amounts added together)")
        else:
            print("  none")

        created = [c for c in CANONICAL_VERTICALS
                   if not any(c.casefold() == r[1].strip().casefold() for r in rows)]
        print(f"\nWill be CREATED: {', '.join(created) if created else 'none'}")

        retired_present = [
            r for r in rows
            if any(r[1].strip().casefold() == k.casefold() for k in RETIRED_VERTICALS)
        ]
        for _id, name, _a, reqs, projs in retired_present:
            print(f"Will be DELETED: {name} "
                  f"({reqs} requests, {projs} projections → {RETIRED_VERTICALS[next(k for k in RETIRED_VERTICALS if k.casefold() == name.strip().casefold())]})")

        print(f"\nTotals: {moving_reqs} requests and {moving_projs} projections change vertical.")
        print(f"        {len(rows)} verticals → "
              f"{len(set(by_target) | set(created))} canonical"
              f"{f' + {len(unmapped)} left untouched' if unmapped else ''}.")
        if unmapped:
            print("\n  NOT in the mapping (deliberately left alone — tell the developer")
            print("  if any of these should also be merged):")
            for name, reqs, projs in unmapped:
                print(f"    • {name}  ({reqs} requests, {projs} projections)")
        print("\nNothing was changed. Run `alembic upgrade head` to apply.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
