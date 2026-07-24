"""Add LOGIN and AI_QUERY values to audit_action enum."""
import asyncio
import os

import asyncpg

# asyncpg wants a plain postgresql:// DSN (no +asyncpg driver, no SQLAlchemy query params).
_RAW_DSN = os.environ.get("MIGRATION_DATABASE_URL") or os.environ.get("DATABASE_URL") or ""
DSN = _RAW_DSN.replace("postgresql+asyncpg://", "postgresql://").split("?")[0]


async def migrate():
    if not DSN:
        raise SystemExit("Set MIGRATION_DATABASE_URL (or DATABASE_URL) in the environment first.")
    conn = await asyncpg.connect(DSN)
    await conn.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'LOGIN'")
    await conn.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'AI_QUERY'")
    # Also add user_agent column if not present
    await conn.execute("""
        ALTER TABLE audit_logs
        ADD COLUMN IF NOT EXISTS user_agent TEXT
    """)
    await conn.close()
    print("Migration complete: LOGIN, AI_QUERY added; user_agent column ensured.")


asyncio.run(migrate())
