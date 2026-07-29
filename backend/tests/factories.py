"""Seed helpers for DB-backed unit tests (SQLite in-memory).

FK targets are created for the joins the code under test actually performs;
SQLite does not enforce FK constraints, so only referenced rows are needed.
"""

import itertools
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deposit_request import DepositRequest
from app.models.enums import CurrencyCode, RequestStatus, TrancheStatus, UserRole
from app.models.masters import Customer, Supplier, User, Vertical
from app.models.tranche import PaymentTranche

_counter = itertools.count(1)


def _next() -> int:
    return next(_counter)


async def make_user(session: AsyncSession, role: UserRole = UserRole.MERCHANDISER) -> User:
    n = _next()
    user = User(
        id=uuid.uuid4(),
        email=f"user{n}@example.com",
        full_name=f"Test User {n}",
        role=role,
    )
    session.add(user)
    await session.flush()
    return user


async def make_supplier(session: AsyncSession) -> Supplier:
    n = _next()
    supplier = Supplier(id=uuid.uuid4(), supplier_code=f"SUP-{n:04d}", name=f"Supplier {n}")
    session.add(supplier)
    await session.flush()
    return supplier


async def make_customer(session: AsyncSession) -> Customer:
    n = _next()
    customer = Customer(id=uuid.uuid4(), name=f"Customer {n}")
    session.add(customer)
    await session.flush()
    return customer


async def make_vertical(session: AsyncSession) -> Vertical:
    n = _next()
    vertical = Vertical(id=uuid.uuid4(), name=f"Vertical {n}")
    session.add(vertical)
    await session.flush()
    return vertical


async def make_request(
    session: AsyncSession,
    *,
    supplier: Supplier,
    customer: Customer,
    created_by: User | None = None,
    vertical: Vertical | None = None,
    deposit_amount: Decimal = Decimal("1000.00"),
    total_invoice: Decimal = Decimal("10000.00"),
    currency: CurrencyCode = CurrencyCode.USD,
    status: RequestStatus = RequestStatus.PENDING_PAYMENT,
    is_locked: bool = False,
    created_at: datetime | None = None,
) -> DepositRequest:
    n = _next()
    request = DepositRequest(
        id=uuid.uuid4(),
        request_number=f"Dep-2099-{n:04d}",
        supplier_id=supplier.id,
        customer_id=customer.id,
        vertical_id=vertical.id if vertical else None,
        currency=currency,
        deposit_amount=deposit_amount,
        total_supplier_invoice_amount=total_invoice,
        current_status=status,
        is_locked=is_locked,
        created_by=created_by.id if created_by else None,
    )
    if created_at is not None:
        request.created_at = created_at
    session.add(request)
    await session.flush()
    return request


async def make_tranche(
    session: AsyncSession,
    request: DepositRequest,
    *,
    number: int = 1,
    amount: Decimal = Decimal("1000.00"),
    status: TrancheStatus = TrancheStatus.UNPAID,
    paid_by: User | None = None,
) -> PaymentTranche:
    tranche = PaymentTranche(
        id=uuid.uuid4(),
        deposit_request_id=request.id,
        tranche_number=number,
        amount=amount,
        tentative_payment_date=None,
        status=status,
        paid_at=datetime.now(timezone.utc) if status == TrancheStatus.PAID else None,
        paid_by=paid_by.id if paid_by else None,
    )
    session.add(tranche)
    await session.flush()
    return tranche
