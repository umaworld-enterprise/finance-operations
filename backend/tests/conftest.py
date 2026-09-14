"""Shared test fixtures."""

import uuid

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from app.core.database import get_db_session
from app.main import app
from app.models.base import Base

# Use in-memory SQLite for unit tests (faster, no external deps)
TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


# SQLite compatibility shims — production runs PostgreSQL only.
@compiles(INET, "sqlite")
def _compile_inet_sqlite(element, compiler, **kw):
    return "VARCHAR(45)"


# Without this, PG's UUID renders as an unknown "UUID" type, which SQLite
# gives NUMERIC affinity — an all-digit hex like the dev user's
# 00000000…0001 then collapses into INTEGER 1 and breaks UUID round-trips.
@compiles(PGUUID, "sqlite")
def _compile_pg_uuid_sqlite(element, compiler, **kw):
    return "CHAR(32)"


@pytest_asyncio.fixture(scope="session")
async def engine():
    eng = create_async_engine(TEST_DB_URL, echo=False)

    # Models default their PKs to PostgreSQL's gen_random_uuid(); provide it.
    # Undashed hex to match how SQLAlchemy's Uuid type binds values on SQLite.
    @event.listens_for(eng.sync_engine, "connect")
    def _register_sqlite_functions(dbapi_conn, _record):
        dbapi_conn.create_function("gen_random_uuid", 0, lambda: uuid.uuid4().hex)

    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db_session(engine):
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(db_session):
    async def override_db():
        yield db_session

    app.dependency_overrides[get_db_session] = override_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
