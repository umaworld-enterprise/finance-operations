"""Seed real supplier names from the vendor master CSV into the suppliers table."""
import asyncio
import json
import os
import sys

sys.path.insert(0, ".")

VENDORS_JSON = os.path.join(os.environ.get("TEMP", "/tmp"), "vendors.json")

# Placeholder names created during initial seed — safe to remove if unreferenced
PLACEHOLDER_NAMES = {"Supplier Alpha Co.", "Supplier Beta Ltd.", "Supplier Gamma GmbH"}


async def seed():
    from app.core.database import AsyncSessionFactory
    from sqlalchemy import text

    with open(VENDORS_JSON, encoding="utf-8-sig") as f:
        vendors = json.load(f)

    print(f"Loaded {len(vendors)} vendors from JSON")

    async with AsyncSessionFactory() as session:
        # Find current highest supplier code number
        result = await session.execute(
            text("SELECT supplier_code FROM suppliers ORDER BY supplier_code DESC")
        )
        codes = [r[0] for r in result.fetchall()]
        max_num = 0
        for code in codes:
            try:
                num = int(code.split("-")[-1])
                max_num = max(max_num, num)
            except ValueError:
                pass

        inserted = 0
        skipped = 0
        counter = max_num + 1

        for v in vendors:
            name = v["name"].strip()
            country = v["country"].strip() or None

            existing = await session.execute(
                text("SELECT id FROM suppliers WHERE name = :name"),
                {"name": name},
            )
            if existing.fetchone():
                skipped += 1
                continue

            supplier_code = f"SUP-{counter:03d}"
            await session.execute(
                text("""
                    INSERT INTO suppliers (supplier_code, name, country, is_active, created_at, updated_at)
                    VALUES (:code, :name, :country, true, NOW(), NOW())
                """),
                {"code": supplier_code, "name": name, "country": country},
            )
            inserted += 1
            counter += 1

        await session.commit()
        print(f"Inserted: {inserted}, Skipped (already exist): {skipped}")

    # Remove placeholders if they have no deposit_requests referencing them
    async with AsyncSessionFactory() as session:
        removed = 0
        for placeholder in PLACEHOLDER_NAMES:
            ref = await session.execute(
                text("""
                    SELECT COUNT(*) FROM deposit_requests dr
                    JOIN suppliers s ON s.id = dr.supplier_id
                    WHERE s.name = :name
                """),
                {"name": placeholder},
            )
            count = ref.scalar()
            if count == 0:
                await session.execute(
                    text("DELETE FROM suppliers WHERE name = :name"),
                    {"name": placeholder},
                )
                removed += 1
                print(f"  Removed placeholder: {placeholder}")
            else:
                print(f"  Kept placeholder '{placeholder}' — has {count} linked request(s)")
        await session.commit()
        print(f"Removed {removed} placeholder(s)")


asyncio.run(seed())
