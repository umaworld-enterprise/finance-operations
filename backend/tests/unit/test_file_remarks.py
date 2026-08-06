"""File Remarks module (CIO batch 2, Aug 2026): raise on own (even locked)
requests with category-specific fields, Open → Resolved lifecycle, role
scoping, and both notifications."""

import pytest
import pytest_asyncio
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import delete, select

from app.core.exceptions import AuthorizationError, ConflictError
from app.models.audit import AuditLog
from app.models.deposit_request import DepositRequest
from app.models.enums import RequestStatus, UserRole
from app.models.file_remark import FileRemark
from app.models.masters import Customer, Supplier, User
from app.models.notification import Notification
from app.schemas.file_remark import FileRemarkCreate
from app.services.file_remark_service import FileRemarkService
from app.services.notification_service import (
    TYPE_FILE_REMARK_RAISED,
    TYPE_FILE_REMARK_RESOLVED,
    notify_file_remark_raised,
    notify_file_remark_resolved,
)
from tests.factories import make_customer, make_request, make_supplier, make_user

@pytest_asyncio.fixture(autouse=True)
async def _wipe_committed_rows(db_session):
    """The notification tests commit (own-session entry points) — wipe."""
    yield
    for model in (Notification, FileRemark, DepositRequest, User, Supplier, Customer):
        await db_session.execute(delete(model))
    await db_session.commit()


async def _setup(db_session):
    merch = await make_user(db_session, UserRole.MERCHANDISER)
    accounts = await make_user(db_session, UserRole.ACCOUNTS_TEAM)
    supplier = await make_supplier(db_session)
    customer = await make_customer(db_session)
    # Locked, processed request — the exact case the module exists for.
    request = await make_request(
        db_session, supplier=supplier, customer=customer, created_by=merch,
        status=RequestStatus.PAYMENT_PROCESSED, is_locked=True,
    )
    return merch, accounts, request


def _payload(request, category="invoice_number_change", **extra):
    defaults = {"old_file_number": "INV-OLD-1", "new_file_number": "INV-NEW-1"}
    if category == "invoice_split":
        defaults = {"new_file_number": "INV-NEW-1, INV-NEW-2"}
    if category == "other":
        defaults = {}
    defaults.update(extra)
    return FileRemarkCreate(
        deposit_request_id=request.id,
        category=category,
        remark="Please move the full deposit.",
        **defaults,
    )


# ── Category-specific field validation (schema) ───────────────────────────────


def test_invoice_number_change_requires_both_file_numbers():
    from uuid import uuid4

    with pytest.raises(PydanticValidationError, match="Old file number"):
        FileRemarkCreate(
            deposit_request_id=uuid4(), category="invoice_number_change",
            new_file_number="N-1", remark="r",
        )
    with pytest.raises(PydanticValidationError, match="New file number"):
        FileRemarkCreate(
            deposit_request_id=uuid4(), category="invoice_number_change",
            old_file_number="O-1", remark="r",
        )


def test_invoice_split_requires_target_file_numbers():
    from uuid import uuid4

    with pytest.raises(PydanticValidationError, match="splits to"):
        FileRemarkCreate(deposit_request_id=uuid4(), category="invoice_split", remark="r")
    # "other" needs the remark only.
    FileRemarkCreate(deposit_request_id=uuid4(), category="other", remark="r")


# ── Create / resolve lifecycle ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_merchandiser_raises_remark_on_own_locked_request(db_session):
    merch, _, request = await _setup(db_session)
    svc = FileRemarkService(db_session)
    remark = await svc.create(_payload(request), merch.id, UserRole.MERCHANDISER)
    assert remark.status == "open"
    assert remark.old_file_number == "INV-OLD-1"
    assert remark.new_file_number == "INV-NEW-1"
    # Audit on the remark AND the request-level trail.
    for entity, entity_id in (("file_remarks", remark.id), ("deposit_requests", request.id)):
        rows = (
            await db_session.execute(
                select(AuditLog).where(
                    AuditLog.entity_name == entity, AuditLog.entity_id == entity_id
                )
            )
        ).scalars().all()
        assert rows, f"missing audit row for {entity}"


@pytest.mark.asyncio
async def test_non_owner_and_ineligible_roles_blocked(db_session):
    merch, _, request = await _setup(db_session)
    other = await make_user(db_session, UserRole.MERCHANDISER)
    hom = await make_user(db_session, UserRole.HEAD_OF_MERCHANDISER)
    svc = FileRemarkService(db_session)
    with pytest.raises(AuthorizationError, match="own requests"):
        await svc.create(_payload(request), other.id, UserRole.MERCHANDISER)
    with pytest.raises(AuthorizationError):
        await svc.create(_payload(request), hom.id, UserRole.HEAD_OF_MERCHANDISER)


@pytest.mark.asyncio
async def test_resolve_flow_and_double_resolve_conflict(db_session):
    merch, accounts, request = await _setup(db_session)
    svc = FileRemarkService(db_session)
    remark = await svc.create(_payload(request), merch.id, UserRole.MERCHANDISER)

    with pytest.raises(AuthorizationError):
        await svc.resolve(remark.id, merch.id, UserRole.MERCHANDISER, "self-resolve")

    resolved = await svc.resolve(
        remark.id, accounts.id, UserRole.ACCOUNTS_TEAM, "Invoice number updated."
    )
    assert resolved.status == "resolved"
    assert resolved.resolved_by == accounts.id
    assert resolved.response_note == "Invoice number updated."
    with pytest.raises(ConflictError, match="already resolved"):
        await svc.resolve(remark.id, accounts.id, UserRole.ACCOUNTS_TEAM)


@pytest.mark.asyncio
async def test_list_scoping_and_filters(db_session):
    merch, accounts, request = await _setup(db_session)
    other = await make_user(db_session, UserRole.MERCHANDISER)
    supplier2 = await make_supplier(db_session)
    customer2 = await make_customer(db_session)
    other_req = await make_request(
        db_session, supplier=supplier2, customer=customer2, created_by=other
    )
    svc = FileRemarkService(db_session)
    mine = await svc.create(_payload(request), merch.id, UserRole.MERCHANDISER)
    theirs = await svc.create(
        _payload(other_req, category="other"), other.id, UserRole.MERCHANDISER
    )
    await svc.resolve(theirs.id, accounts.id, UserRole.ACCOUNTS_TEAM)

    own = await svc.list(merch.id, UserRole.MERCHANDISER)
    assert {r.id for r in own} == {mine.id}
    assert own[0].request_number == request.request_number

    all_rows = await svc.list(accounts.id, UserRole.ACCOUNTS_TEAM)
    assert {r.id for r in all_rows} == {mine.id, theirs.id}
    open_rows = await svc.list(accounts.id, UserRole.ACCOUNTS_TEAM, status="open")
    assert {r.id for r in open_rows} == {mine.id}


# ── Notifications ─────────────────────────────────────────────────────────────


def _patch_factory(engine, monkeypatch):
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr("app.core.database.AsyncSessionFactory", factory)


@pytest.mark.asyncio
async def test_raised_fans_out_to_accounts(db_session, engine, monkeypatch):
    merch, accounts, request = await _setup(db_session)
    accounts2 = await make_user(db_session, UserRole.ACCOUNTS_TEAM)
    svc = FileRemarkService(db_session)
    remark = await svc.create(_payload(request), merch.id, UserRole.MERCHANDISER)
    await db_session.commit()
    _patch_factory(engine, monkeypatch)

    await notify_file_remark_raised(remark.id)

    rows = (
        await db_session.execute(
            select(Notification).where(Notification.type == TYPE_FILE_REMARK_RAISED)
        )
    ).scalars().all()
    assert {n.user_id for n in rows} == {accounts.id, accounts2.id}
    body = rows[0].body
    assert "Invoice number change" in body
    assert request.request_number in body
    assert "INV-OLD-1" in body and "INV-NEW-1" in body


@pytest.mark.asyncio
async def test_resolved_notifies_the_raiser_with_response(db_session, engine, monkeypatch):
    merch, accounts, request = await _setup(db_session)
    svc = FileRemarkService(db_session)
    remark = await svc.create(_payload(request), merch.id, UserRole.MERCHANDISER)
    await svc.resolve(remark.id, accounts.id, UserRole.ACCOUNTS_TEAM, "Done — number updated.")
    await db_session.commit()
    _patch_factory(engine, monkeypatch)

    await notify_file_remark_resolved(remark.id)

    rows = (
        await db_session.execute(
            select(Notification).where(Notification.type == TYPE_FILE_REMARK_RESOLVED)
        )
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].user_id == merch.id
    assert "Done — number updated." in rows[0].body
