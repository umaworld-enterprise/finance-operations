"""One-time migration: add ai_access_enabled column to users table."""
import asyncio, sys
sys.path.insert(0, ".")

async def run():
    from app.core.database import AsyncSessionFactory
    from sqlalchemy import text
    async with AsyncSessionFactory() as session:
        await session.execute(text("""
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS ai_access_enabled BOOLEAN NOT NULL DEFAULT FALSE
        """))
        await session.commit()
        print("Migration complete: users.ai_access_enabled added.")

asyncio.run(run())
