"""Adjust Invoice notifications (change note B2/B3): raise → Accounts fan-out,
decision → back to the raising merchandiser with the reason."""

from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.audit import AuditLog
from app.models.deposit_request import DepositRequest
from app.models.enums import TrancheStatus, UserRole
from app.models.masters import Customer, Supplier, User
from app.models.notification import Notification
from app.models.tranche import InvoiceAdjustment, PaymentTranche
from app.schemas.tranche import AdjustmentCreate
from app.services.adjustment_service import AdjustmentService
from app.services.notification_service import (
    TYPE_ADJUSTMENT_DECIDED,
    TYPE_ADJUSTMENT_RECORDED,
    TYPE_ADJUSTMENT_REQUESTED,
    build_adjustment_notification_message,
    notify_adjustment_created,
    notify_adjustment_decided,
)
from tests.factories import (
    make_customer,
    make_request,
    make_supplier,
    make_tranche,
    make_user,
)


@pytest_asyncio.fixture(autouse=True)
async def _wipe_committed_rows(db_session):
    """These tests COMMIT (the notify entry points open their own sessions on
    the shared in-memory engine), so leftover rows would leak into later test
    modules — wipe everything this module seeds."""
    yield
    for model in (
        Notification, InvoiceAdjustment, PaymentTranche,
        DepositRequest, AuditLog, User, Supplier, Customer,
    ):
        await db_session.execute(delete(model))
    await db_session.commit()


# ── Message builder (pure) ────────────────────────────────────────────────────


def test_requested_message_names_route_and_reason():
    msg = build_adjustment_notification_message(
        TYPE_ADJUSTMENT_REQUESTED,
        amount="300.00",
        source_label="Tranche I",
        source_request_number="Dep-2026-0001",
        destination_label="Tranche II",
        destination_request_number="Dep-2026-0002",
        reason="Order cancelled",
    )
    assert msg["title"] == "Adjustment approval requested"
    for text in ("300.00", "Tranche I", "Dep-2026-0001", "Dep-2026-0002", "Order cancelled"):
        assert text in msg["body"]
    assert msg["url"] == "/adjust-invoices"


def test_decided_message_includes_decision_and_reason():
    msg = build_adjustment_notification_message(
        TYPE_ADJUSTMENT_DECIDED,
        amount="300.00",
        source_label="Tranche I",
        source_request_number="Dep-2026-0001",
        destination_label="Tranche II",
        destination_request_number="Dep-2026-0002",
        reason="Not justified",
        decision="rejected",
    )
    assert msg["title"] == "Adjustment rejected"
    assert "rejected" in msg["body"]
    assert "Not justified" in msg["body"]


# ── Delivery (DB-backed, own-session entry points) ────────────────────────────


async def _seed(db_session):
    merch = await make_user(db_session, UserRole.MERCHANDISER)
    accounts1 = await make_user(db_session, UserRole.ACCOUNTS_TEAM)
    accounts2 = await make_user(db_session, UserRole.ACCOUNTS_TEAM)
    supplier = await make_supplier(db_session)
    customer = await make_customer(db_session)
    req_a = await make_request(db_session, supplier=supplier, customer=customer)
    req_b = await make_request(db_session, supplier=supplier, customer=customer)
    paid = await make_tranche(
        db_session, req_a, amount=Decimal("1000.00"), status=TrancheStatus.PAID
    )
    unpaid = await make_tranche(db_session, req_b, amount=Decimal("800.00"))
    return merch, accounts1, accounts2, paid, unpaid


def _patch_factory(engine, monkeypatch):
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr("app.core.database.AsyncSessionFactory", factory)


@pytest.mark.asyncio
async def test_requested_fans_out_to_accounts_team(db_session, engine, monkeypatch):
    merch, accounts1, accounts2, paid, unpaid = await _seed(db_session)
    svc = AdjustmentService(db_session)
    adj = await svc.create(
        AdjustmentCreate(
            source_tranche_id=paid.id,
            destination_tranche_id=unpaid.id,
            amount=Decimal("300.00"),
            reason="Order cancelled",
        ),
        merch.id, UserRole.MERCHANDISER,
    )
    await db_session.commit()
    _patch_factory(engine, monkeypatch)

    await notify_adjustment_created(adj.id)

    rows = (
        await db_session.execute(
            select(Notification).where(Notification.type == TYPE_ADJUSTMENT_REQUESTED)
        )
    ).scalars().all()
    assert {n.user_id for n in rows} == {accounts1.id, accounts2.id}
    assert all("Order cancelled" in n.body for n in rows)


@pytest.mark.asyncio
async def test_recorded_excludes_the_acting_accounts_user(db_session, engine, monkeypatch):
    merch, accounts1, accounts2, paid, unpaid = await _seed(db_session)
    svc = AdjustmentService(db_session)
    adj = await svc.create(
        AdjustmentCreate(
            source_tranche_id=paid.id,
            destination_tranche_id=unpaid.id,
            amount=Decimal("100.00"),
        ),
        accounts1.id, UserRole.ACCOUNTS_TEAM,
    )
    await db_session.commit()
    _patch_factory(engine, monkeypatch)

    await notify_adjustment_created(adj.id)

    rows = (
        await db_session.execute(
            select(Notification).where(Notification.type == TYPE_ADJUSTMENT_RECORDED)
        )
    ).scalars().all()
    assert {n.user_id for n in rows} == {accounts2.id}


@pytest.mark.asyncio
async def test_decision_notifies_the_raising_merchandiser(db_session, engine, monkeypatch):
    merch, accounts1, _, paid, unpaid = await _seed(db_session)
    svc = AdjustmentService(db_session)
    adj = await svc.create(
        AdjustmentCreate(
            source_tranche_id=paid.id,
            destination_tranche_id=unpaid.id,
            amount=Decimal("300.00"),
            reason="Order cancelled",
        ),
        merch.id, UserRole.MERCHANDISER,
    )
    await svc.reject(adj.id, accounts1.id, UserRole.ACCOUNTS_TEAM, "Not justified")
    await db_session.commit()
    _patch_factory(engine, monkeypatch)

    await notify_adjustment_decided(adj.id, "rejected", "Not justified")

    rows = (
        await db_session.execute(
            select(Notification).where(Notification.type == TYPE_ADJUSTMENT_DECIDED)
        )
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].user_id == merch.id
    assert "rejected" in rows[0].body
    assert "Not justified" in rows[0].body
