"""HoM approve/reject: mandatory reason (422 without it) and merchandiser
notification on decision, per the 14 July 2026 process change note (C3/C4)."""

import types
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.dependencies import CurrentUser, get_current_user
from app.main import app
from app.models.deposit_request import DepositRequest
from app.models.enums import UserRole
from app.models.masters import Customer, Supplier, User
from app.models.notification import Notification
from app.services.notification_service import (
    TYPE_HOM_APPROVED,
    TYPE_HOM_REJECTED,
    build_hom_decision_message,
    notify_hom_decision,
)
from tests.factories import make_customer, make_request, make_supplier, make_user


@pytest_asyncio.fixture(autouse=True)
async def _wipe_committed_rows(db_session):
    """The notify tests COMMIT (notify_hom_decision opens its own session on
    the shared in-memory engine) — wipe seeded rows so nothing leaks into
    later test modules."""
    yield
    for model in (Notification, DepositRequest, User, Supplier, Customer):
        await db_session.execute(delete(model))
    await db_session.commit()


# ── Message builder (pure) ────────────────────────────────────────────────────


def test_rejected_message_contains_request_number_and_reason():
    rid = uuid.uuid4()
    msg = build_hom_decision_message(
        TYPE_HOM_REJECTED, "Dep-2026-0004", rid, "Supplier terms not agreed"
    )
    assert msg["title"] == "Request rejected"
    assert "Dep-2026-0004" in msg["body"]
    assert "Supplier terms not agreed" in msg["body"]
    assert msg["url"] == f"/merchandiser/{rid}"


def test_approved_message_contains_request_number_and_reason():
    rid = uuid.uuid4()
    msg = build_hom_decision_message(
        TYPE_HOM_APPROVED, "Dep-2026-0005", rid, "Cleared with finance"
    )
    assert msg["title"] == "Request approved"
    assert "Dep-2026-0005" in msg["body"]
    assert "Cleared with finance" in msg["body"]
    assert msg["url"] == f"/merchandiser/{rid}"


# ── Mandatory remarks: 422 from both endpoints ────────────────────────────────


def _fake_hom_user() -> CurrentUser:
    return CurrentUser(
        types.SimpleNamespace(
            id=uuid.uuid4(),
            email="hom@example.com",
            full_name="Head of Merchandiser",
            role=UserRole.HEAD_OF_MERCHANDISER,
            onboarding_completed=True,
            secondary_email=None,
            department=None,
            font_size="default",
        )
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ["hom-approve", "hom-reject"])
@pytest.mark.parametrize("body", [{}, {"remarks": ""}, {"remarks": None}])
async def test_hom_decision_without_remarks_is_422(client, endpoint, body):
    app.dependency_overrides[get_current_user] = _fake_hom_user
    try:
        resp = await client.post(f"/api/v1/requests/{uuid.uuid4()}/{endpoint}", json=body)
        assert resp.status_code == 422
    finally:
        app.dependency_overrides.pop(get_current_user, None)


# ── Rejection writes a Notification row for the raising merchandiser ─────────


@pytest.mark.asyncio
async def test_hom_rejection_notifies_raising_merchandiser(
    db_session: AsyncSession, engine, monkeypatch
):
    merch = await make_user(db_session, role=UserRole.MERCHANDISER)
    supplier = await make_supplier(db_session)
    customer = await make_customer(db_session)
    request = await make_request(
        db_session, supplier=supplier, customer=customer, created_by=merch
    )
    await db_session.commit()

    # notify_hom_decision opens its own session — point the app factory at the
    # test engine (StaticPool shares the in-memory DB).
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr("app.core.database.AsyncSessionFactory", factory)

    await notify_hom_decision(request.id, "rejected", "Prices not agreed with supplier")

    rows = (
        await db_session.execute(
            select(Notification).where(Notification.deposit_request_id == request.id)
        )
    ).scalars().all()
    assert len(rows) == 1
    note = rows[0]
    assert note.user_id == merch.id
    assert note.type == TYPE_HOM_REJECTED
    assert "Prices not agreed with supplier" in note.body
    assert request.request_number in note.body
    assert note.url == f"/merchandiser/{request.id}"


@pytest.mark.asyncio
async def test_hom_approval_notifies_raising_merchandiser(
    db_session: AsyncSession, engine, monkeypatch
):
    merch = await make_user(db_session, role=UserRole.MERCHANDISER)
    supplier = await make_supplier(db_session)
    customer = await make_customer(db_session)
    request = await make_request(
        db_session, supplier=supplier, customer=customer, created_by=merch
    )
    await db_session.commit()

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr("app.core.database.AsyncSessionFactory", factory)

    await notify_hom_decision(request.id, "approved", "Cleared with finance")

    rows = (
        await db_session.execute(
            select(Notification).where(Notification.deposit_request_id == request.id)
        )
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].user_id == merch.id
    assert rows[0].type == TYPE_HOM_APPROVED
    assert "Cleared with finance" in rows[0].body
