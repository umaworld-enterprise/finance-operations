"""Alembic environment configuration for async SQLAlchemy."""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

# Import Base and all models so Alembic autogenerate can detect them
from app.models import Base  # noqa: F401 — triggers all model imports

config = context.config
fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    import os
    from dotenv import load_dotenv
    load_dotenv()  # ensure .env is read before os.getenv
    # Prefer direct connection for migrations — bypasses PgBouncer transaction pooler
    # which is incompatible with asyncpg prepared statements used during setup.
    return (
        os.getenv("MIGRATION_DATABASE_URL")
        or os.getenv("DATABASE_URL")
        or ""
    )


def run_migrations_offline() -> None:
    """Run migrations without a live DB connection (generates SQL script)."""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:  # type: ignore[no-untyped-def]
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    config_section = config.get_section(config.config_ini_section, {})
    config_section["sqlalchemy.url"] = get_url()

    connectable = async_engine_from_config(
        config_section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
