"""Async SQLAlchemy engine and session factory."""

import uuid
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=settings.app_debug,
    pool_size=10,
    max_overflow=20,
    # pre_ping costs one extra round trip per checkout; behind pgbouncer the
    # connections it validates are pooled server-side anyway. Recycle instead.
    pool_pre_ping=False,
    pool_recycle=300,
    # Supabase's transaction pooler (pgbouncer) reuses backend connections
    # across sessions and does not support cached/named prepared statements.
    # Disable asyncpg's statement cache, disable SQLAlchemy's prepared-statement
    # cache, and randomize prepared-statement names so they never collide.
    connect_args={
        "statement_cache_size": 0,
        "prepared_statement_cache_size": 0,
        "prepared_statement_name_func": lambda: f"__asyncpg_{uuid.uuid4()}__",
        "timeout": 10,
        "command_timeout": 30,
    },
)

AsyncSessionFactory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async database session."""
    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
