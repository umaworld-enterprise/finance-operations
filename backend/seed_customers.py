"""Seed real customer names directly into the database."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

CUSTOMERS = [
    "Brazzavile",
    "Cotonou",
    "Lome",
    "Mali",
    "Point Noire",
    "Abidjan",
    "Dicam",
    "Fronext",
    "Fabfer",
    "Fizzen",
    "Cabinda",
    "SKTN",
    "Mozambique",
    "Umesh",
    "Sar Saidu",
    "Boka Bathily",
    "Bangui",
    "Agrova",
    "Lubumbashi",
    "Kishore Ghana",
]


async def seed() -> None:
    from app.core.database import AsyncSessionFactory
    from sqlalchemy import text

    # ── Step 1: insert new customers ─────────────────────────────────────────
    async with AsyncSessionFactory() as session:
        result = await session.execute(text("SELECT name FROM customers"))
        existing = {row[0] for row in result.fetchall()}

        to_insert = [c for c in CUSTOMERS if c not in existing]

        if not to_insert:
            print("All customers already present.")
        else:
            for name in to_insert:
                await session.execute(
                    text("INSERT INTO customers (name, is_active) VALUES (:name, true)"),
                    {"name": name},
                )
                print(f"  + {name}")
            await session.commit()
            print(f"\nInserted {len(to_insert)} customers.")

    # ── Step 2: remove placeholder seeds (skip if still referenced) ──────────
    placeholders = ["Customer A", "Customer B", "Customer C"]
    async with AsyncSessionFactory() as session:
        for ph in placeholders:
            try:
                await session.execute(
                    text("DELETE FROM customers WHERE name = :name"),
                    {"name": ph},
                )
                await session.commit()
                print(f"  - removed placeholder: {ph}")
            except Exception:
                await session.rollback()
                print(f"  ~ skipped placeholder (still in use): {ph}")


if __name__ == "__main__":
    asyncio.run(seed())
