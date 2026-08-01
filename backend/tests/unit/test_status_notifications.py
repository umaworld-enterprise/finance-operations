"""Status-change and request-created notifications (Aug 2026 batch, item 1.2).

These entry points open their own sessions, so the tests commit — the autouse
wipe fixture clears everything afterwards (shared in-memory engine)."""

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.deposit_request import DepositRequest
from app.models.enums import RequestStatus, UserRole
from app.models.masters import Customer, Supplier, User
from app.models.notification import Notification
from app.services.notification_service import (
    TYPE_REQUEST_CREATED,
    TYPE_REQUEST_PENDING_HOM,
    TYPE_STATUS_CHANGED,
    build_status_change_message,
    notify_request_created,
    notify_status_change,
)
from tests.factories import make_customer, make_request, make_supplier, make_user


@pytest_asyncio.fixture(autouse=True)
async def _wipe_committed_rows(db_session):
    yield
    for model in (Notification, DepositRequest, User, Supplier, Customer):
        await db_session.execute(delete(model))
    await db_session.commit()


# ── Message builder (pure) ────────────────────────────────────────────────────


def test_merchandiser_hold_message_targets_accounts_view():
    msg = build_status_change_message(
        "hold_by_merchandiser", "Dep-2026-0007", "rid", True, remarks="supplier delay"
    )
    assert msg["title"] == "Request on hold"
    assert "the merchandiser" in msg["body"]
    assert "supplier delay" in msg["body"]
    assert msg["url"] == "/accounts/rid"


def test_accounts_cancel_message_targets_merchandiser_view():
    msg = build_status_change_message("cancelled_by_accounts", "Dep-2026-0007", "rid", False)
    assert msg["title"] == "Request cancelled"
    assert "the Accounts team" in msg["body"]
    assert msg["url"] == "/merchandiser/rid"


def test_resume_message_says_back_in_queue():
    msg = build_status_change_message("pending_payment", "Dep-2026-0008", "rid", False)
    assert msg["title"] == "Request resumed"
    assert "payment queue" in msg["body"]


# ── Delivery ──────────────────────────────────────────────────────────────────


async def _seed(db_session, *, status=RequestStatus.PENDING_PAYMENT):
    merch = await make_user(db_session, UserRole.MERCHANDISER)
    accounts1 = await make_user(db_session, UserRole.ACCOUNTS_TEAM)
    accounts2 = await make_user(db_session, UserRole.ACCOUNTS_TEAM)
    hom = await make_user(db_session, UserRole.HEAD_OF_MERCHANDISER)
    supplier = await make_supplier(db_session)
    customer = await make_customer(db_session)
    request = await make_request(
        db_session, supplier=supplier, customer=customer, created_by=merch, status=status
    )
    await db_session.commit()
    return merch, accounts1, accounts2, hom, request


def _patch_factory(engine, monkeypatch):
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr("app.core.database.AsyncSessionFactory", factory)


async def _rows(db_session, type_):
    return (
        await db_session.execute(select(Notification).where(Notification.type == type_))
    ).scalars().all()


@pytest.mark.asyncio
async def test_new_pending_request_notifies_accounts_team(db_session, engine, monkeypatch):
    merch, accounts1, accounts2, hom, request = await _seed(db_session)
    _patch_factory(engine, monkeypatch)

    await notify_request_created(request.id)

    rows = await _rows(db_session, TYPE_REQUEST_CREATED)
    assert {n.user_id for n in rows} == {accounts1.id, accounts2.id}
    assert all(request.request_number in n.body for n in rows)
    assert all(n.url == f"/accounts/{request.id}" for n in rows)
    # HoM got nothing — the request is not awaiting approval.
    assert await _rows(db_session, TYPE_REQUEST_PENDING_HOM) == []


@pytest.mark.asyncio
async def test_flagged_request_notifies_hom_users(db_session, engine, monkeypatch):
    merch, accounts1, accounts2, hom, request = await _seed(
        db_session, status=RequestStatus.PENDING_HOM_APPROVAL
    )
    _patch_factory(engine, monkeypatch)

    await notify_request_created(request.id)

    rows = await _rows(db_session, TYPE_REQUEST_PENDING_HOM)
    assert {n.user_id for n in rows} == {hom.id}
    assert "approval" in rows[0].body.lower()
    assert rows[0].url == f"/hom/{request.id}"
    assert await _rows(db_session, TYPE_REQUEST_CREATED) == []


@pytest.mark.asyncio
async def test_merchandiser_hold_fans_out_to_accounts(db_session, engine, monkeypatch):
    merch, accounts1, accounts2, _, request = await _seed(db_session)
    _patch_factory(engine, monkeypatch)

    await notify_status_change(
        request.id, "hold_by_merchandiser", UserRole.MERCHANDISER.value, "supplier delay"
    )

    rows = await _rows(db_session, TYPE_STATUS_CHANGED)
    assert {n.user_id for n in rows} == {accounts1.id, accounts2.id}
    assert all("supplier delay" in n.body for n in rows)


@pytest.mark.asyncio
async def test_accounts_cancel_notifies_raising_merchandiser(db_session, engine, monkeypatch):
    merch, _, _, _, request = await _seed(db_session)
    _patch_factory(engine, monkeypatch)

    await notify_status_change(
        request.id, "cancelled_by_accounts", UserRole.ACCOUNTS_TEAM.value, "duplicate order"
    )

    rows = await _rows(db_session, TYPE_STATUS_CHANGED)
    assert len(rows) == 1
    assert rows[0].user_id == merch.id
    assert "cancelled" in rows[0].body
    assert "duplicate order" in rows[0].body
    assert rows[0].url == f"/merchandiser/{request.id}"


@pytest.mark.asyncio
async def test_accounts_reopen_notifies_raising_merchandiser(db_session, engine, monkeypatch):
    merch, _, _, _, request = await _seed(db_session)
    _patch_factory(engine, monkeypatch)

    await notify_status_change(request.id, "reopened", UserRole.ACCOUNTS_TEAM.value, None)

    rows = await _rows(db_session, TYPE_STATUS_CHANGED)
    assert [n.user_id for n in rows] == [merch.id]
    assert "reopened" in rows[0].body
