"""
Seed script — populates master data for a fresh installation.

Usage:
    python -m scripts.seed

Requires DATABASE_URL in environment (or .env file).
"""

import asyncio
import os
import sys
from datetime import date

# Allow running from backend/ directory
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.models.enums import CurrencyCode, UserRole
from app.models.masters import Customer, Supplier, SystemConfig, User, Vertical

settings = get_settings()


# ── Seed data definitions ─────────────────────────────────────────────────────

VERTICALS = [
    "Frozen",
    "Hardware - Raw Material",
    "Hardware - Building Material",
    "Hardware - Engine & Generator",
    "White Goods",
    "Textile",
    "Food",
    "Sundry",
    "Automobile",
    "Agriculture",
    "Machinery",
    "Commodities",
]

# Customers — extend this list with actual values from the business
CUSTOMERS = [
    "Customer A",
    "Customer B",
    "Customer C",
]

# Sample suppliers — replace with actual supplier list
SUPPLIERS = [
    {"supplier_code": "SUP-001", "name": "Supplier Alpha Co.", "country": "China"},
    {"supplier_code": "SUP-002", "name": "Supplier Beta Ltd.", "country": "India"},
    {"supplier_code": "SUP-003", "name": "Supplier Gamma GmbH", "country": "Germany"},
]

SYSTEM_CONFIG = [
    {
        "config_key": "etd_grace_days",
        "config_value": "10",
        "description": "Number of grace days added to estimated ETD before overdue calculation",
    },
    {
        "config_key": "cost_of_fund_rate",
        "config_value": "0.12",
        "description": "Annualised cost of fund rate (0.12 = 12% p.a., per client sheet 2026-07-10)",
    },
    {
        "config_key": "cost_of_fund_grace_days",
        "config_value": "30",
        "description": "Unused since 2026-07-10 CoF alignment (accrual runs from Est ETD)",
    },
]

# Bootstrap Super Admin — update email to match actual admin Gmail
BOOTSTRAP_SUPER_ADMIN = {
    "email": "admin@sunshine.com",
    "full_name": "System Administrator",
    "role": UserRole.SUPER_ADMIN,
    "is_active": True,
}


# ── Seed logic ────────────────────────────────────────────────────────────────

async def seed() -> None:
    engine = create_async_engine(settings.database_url, echo=False)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as session:
        print("Seeding verticals...")
        for name in VERTICALS:
            stmt = insert(Vertical).values(name=name, is_active=True).on_conflict_do_nothing(index_elements=["name"])
            await session.execute(stmt)

        print("Seeding customers...")
        for name in CUSTOMERS:
            stmt = insert(Customer).values(name=name, is_active=True).on_conflict_do_nothing(index_elements=["name"])
            await session.execute(stmt)

        print("Seeding suppliers...")
        for supplier in SUPPLIERS:
            stmt = insert(Supplier).values(**supplier, is_active=True).on_conflict_do_nothing(index_elements=["supplier_code"])
            await session.execute(stmt)

        print("Seeding system config...")
        for cfg in SYSTEM_CONFIG:
            stmt = insert(SystemConfig).values(**cfg).on_conflict_do_update(
                index_elements=["config_key"],
                set_={"config_value": cfg["config_value"], "description": cfg["description"]},
            )
            await session.execute(stmt)

        print("Seeding bootstrap super admin...")
        stmt = insert(User).values(**BOOTSTRAP_SUPER_ADMIN).on_conflict_do_nothing(index_elements=["email"])
        await session.execute(stmt)

        await session.commit()

    await engine.dispose()
    print("Seed complete.")


if __name__ == "__main__":
    asyncio.run(seed())
