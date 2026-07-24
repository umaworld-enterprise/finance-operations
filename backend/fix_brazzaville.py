import asyncio
import sys
sys.path.insert(0, ".")

async def fix():
    from app.core.database import AsyncSessionFactory
    from sqlalchemy import text
    async with AsyncSessionFactory() as session:
        result = await session.execute(
            text("UPDATE customers SET name = :new WHERE name = :old"),
            {"new": "Brazzaville", "old": "Brazzavile"},
        )
        await session.commit()
        print(f"Rows updated: {result.rowcount}")

asyncio.run(fix())
