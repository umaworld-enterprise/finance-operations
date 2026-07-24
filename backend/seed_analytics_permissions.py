"""Seed default analytics_permissions into system_config."""
import asyncio
import json
import os

import asyncpg

# asyncpg wants a plain postgresql:// DSN (no +asyncpg driver, no SQLAlchemy query params).
_RAW_DSN = os.environ.get("MIGRATION_DATABASE_URL") or os.environ.get("DATABASE_URL") or ""
DSN = _RAW_DSN.replace("postgresql+asyncpg://", "postgresql://").split("?")[0]

DEFAULT = {
    "overdue_kpis":    ["finance_admin", "accounts_team"],
    "shipment_kpis":   ["finance_admin", "accounts_team", "merchandiser"],
    "delay_buckets":   ["finance_admin"],
    "by_merchandiser": ["finance_admin"],
    "by_vertical":     ["finance_admin", "accounts_team"],
    "by_customer":     ["finance_admin", "accounts_team"],
}


async def seed():
    if not DSN:
        raise SystemExit("Set MIGRATION_DATABASE_URL (or DATABASE_URL) in the environment first.")
    conn = await asyncpg.connect(DSN)
    await conn.execute("""
        INSERT INTO system_config (id, config_key, config_value, description, updated_at)
        VALUES (gen_random_uuid(), 'analytics_permissions', $1, 'Analytics section access by role', NOW())
        ON CONFLICT (config_key) DO NOTHING
    """, json.dumps(DEFAULT))
    await conn.close()
    print("Seeded analytics_permissions into system_config.")

asyncio.run(seed())
