"""Tranche workflow: merchandiser edit rights, Accounts payments, TT copies,
paid-tranche locking, request completion and audit events."""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.exceptions import (
    AuthorizationError,
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.models.audit import AuditLog
from app.models.enums import RequestStatus, TrancheStatus, UserRole
from app.schemas.tranche import TrancheUpdate
from app.services.tranche_service import TrancheService
from tests.factories import (
    make_customer,
    make_request,
    make_supplier,
    make_tranche,
    make_user,
)

pytestmark = pytest.mark.asyncio


async def _setup(db_session, *, tranche_amounts=("1000.00",)):
    merch = await make_user(db_session, UserRole.MERCHANDISER)
    accounts = await make_user(db_session, UserRole.ACCOUNTS_TEAM)
    supplier = await make_supplier(db_session)
    customer = await make_customer(db_session)
    total = sum(Decimal(a) for a in tranche_amounts)
    request = await make_request(
        db_session, supplier=supplier, customer=customer, created_by=merch,
        deposit_amount=total,
    )
    tranches = []
    for i, amount in enumerate(tranche_amounts, start=1):
        tranches.append(
            await make_tranche(db_session, request, number=i, amount=Decimal(amount))
        )
    return merch, accounts, request, tranches


async def _with_tt(db_session, *tranches):
    """pay_tranche requires a TT copy (change note C6) — attach one directly
    so tests can exercise the payment paths beyond that gate."""
    for t in tranches:
        t.tt_copy_url = f"https://drive.test/tt-{t.id}.pdf"
    await db_session.flush()


async def _audit_rows(db_session, entity_name, entity_id):
    result = await db_session.execute(
        select(AuditLog).where(
            AuditLog.entity_name == entity_name, AuditLog.entity_id == entity_id
        )
    )
    return list(result.scalars().all())


# ── Merchandiser edit rights ──────────────────────────────────────────────────


async def test_owner_can_edit_unpaid_tranche(db_session):
    merch, _, request, (tranche,) = await _setup(db_session)
    svc = TrancheService(db_session)
    updated = await svc.update_tranche(
        request.id, tranche.id,
        TrancheUpdate(amount=Decimal("1500.00"), tentative_payment_date=date(2026, 9, 1)),
        merch.id, UserRole.MERCHANDISER,
    )
    assert updated.amount == Decimal("1500.00")
    assert updated.tentative_payment_date == date(2026, 9, 1)
    # deposit_amount tracks the tranche sum
    assert Decimal(str(request.deposit_amount)) == Decimal("1500.00")
    # per-field audit rows recorded
    logs = await _audit_rows(db_session, "payment_tranches", tranche.id)
    assert {log.field_name for log in logs} == {"amount", "tentative_payment_date"}


async def test_non_owner_merchandiser_cannot_edit(db_session):
    _, _, request, (tranche,) = await _setup(db_session)
    other = await make_user(db_session, UserRole.MERCHANDISER)
    svc = TrancheService(db_session)
    with pytest.raises(AuthorizationError):
        await svc.update_tranche(
            request.id, tranche.id, TrancheUpdate(amount=Decimal("1.00")),
            other.id, UserRole.MERCHANDISER,
        )


async def test_accounts_role_cannot_edit_tranche(db_session):
    _, accounts, request, (tranche,) = await _setup(db_session)
    svc = TrancheService(db_session)
    with pytest.raises(AuthorizationError):
        await svc.update_tranche(
            request.id, tranche.id, TrancheUpdate(amount=Decimal("1.00")),
            accounts.id, UserRole.ACCOUNTS_TEAM,
        )


async def test_paid_tranche_is_immutable(db_session):
    merch, accounts, request, (tranche,) = await _setup(db_session)
    await _with_tt(db_session, tranche)
    svc = TrancheService(db_session)
    await svc.pay_tranche(request.id, tranche.id, accounts.id, UserRole.ACCOUNTS_TEAM)
    with pytest.raises(ConflictError):
        await svc.update_tranche(
            request.id, tranche.id, TrancheUpdate(amount=Decimal("2.00")),
            merch.id, UserRole.SUPER_ADMIN,
        )


async def test_edit_cannot_exceed_invoice_total(db_session):
    merch, _, request, (t1, t2) = await _setup(
        db_session, tranche_amounts=("4000.00", "4000.00")
    )
    svc = TrancheService(db_session)
    # 4000 + 7000 > 10000 invoice total
    with pytest.raises(ValidationError, match="cannot exceed"):
        await svc.update_tranche(
            request.id, t2.id, TrancheUpdate(amount=Decimal("7000.00")),
            merch.id, UserRole.MERCHANDISER,
        )


async def test_edit_unknown_tranche_404s(db_session):
    merch, _, request, _ = await _setup(db_session)
    svc = TrancheService(db_session)
    with pytest.raises(NotFoundError):
        await svc.update_tranche(
            request.id, uuid.uuid4(), TrancheUpdate(amount=Decimal("1.00")),
            merch.id, UserRole.MERCHANDISER,
        )


# ── Accounts tranche payments ─────────────────────────────────────────────────


async def test_pay_partial_tranche_keeps_request_open(db_session):
    _, accounts, request, (t1, t2) = await _setup(
        db_session, tranche_amounts=("600.00", "400.00")
    )
    await _with_tt(db_session, t1)
    svc = TrancheService(db_session)
    paid = await svc.pay_tranche(request.id, t1.id, accounts.id, UserRole.ACCOUNTS_TEAM)
    assert paid.status == TrancheStatus.PAID
    assert paid.paid_by == accounts.id
    assert paid.paid_at is not None
    # Request still pending with an unpaid tranche outstanding
    assert request.current_status == RequestStatus.PENDING_PAYMENT
    assert request.is_locked is False


async def test_paying_final_tranche_completes_and_locks_request(db_session):
    _, accounts, request, (t1, t2) = await _setup(
        db_session, tranche_amounts=("600.00", "400.00")
    )
    await _with_tt(db_session, t1, t2)
    svc = TrancheService(db_session)
    await svc.pay_tranche(request.id, t1.id, accounts.id, UserRole.ACCOUNTS_TEAM)
    await svc.pay_tranche(request.id, t2.id, accounts.id, UserRole.ACCOUNTS_TEAM)
    assert request.current_status == RequestStatus.PAYMENT_PROCESSED
    assert request.is_locked is True
    logs = await _audit_rows(db_session, "deposit_requests", request.id)
    assert any(log.new_value == RequestStatus.PAYMENT_PROCESSED.value for log in logs)


async def test_double_payment_rejected(db_session):
    _, accounts, request, (t1, t2) = await _setup(
        db_session, tranche_amounts=("600.00", "400.00")
    )
    await _with_tt(db_session, t1)
    svc = TrancheService(db_session)
    await svc.pay_tranche(request.id, t1.id, accounts.id, UserRole.ACCOUNTS_TEAM)
    with pytest.raises(ConflictError, match="already paid"):
        await svc.pay_tranche(request.id, t1.id, accounts.id, UserRole.ACCOUNTS_TEAM)


async def test_merchandiser_cannot_pay_tranche(db_session):
    merch, _, request, (tranche,) = await _setup(db_session)
    svc = TrancheService(db_session)
    with pytest.raises(AuthorizationError):
        await svc.pay_tranche(request.id, tranche.id, merch.id, UserRole.MERCHANDISER)


async def test_cannot_pay_tranche_on_held_request(db_session):
    _, accounts, request, (tranche,) = await _setup(db_session)
    await _with_tt(db_session, tranche)
    request.current_status = RequestStatus.HOLD_BY_ACCOUNTS
    await db_session.flush()
    svc = TrancheService(db_session)
    with pytest.raises(ConflictError, match="pending payment"):
        await svc.pay_tranche(request.id, tranche.id, accounts.id, UserRole.ACCOUNTS_TEAM)


async def test_pay_tranche_without_tt_copy_rejected(db_session):
    """C6: a tranche must never become PAID without its TT copy."""
    _, accounts, request, (tranche,) = await _setup(db_session)
    svc = TrancheService(db_session)
    with pytest.raises(ConflictError, match="TT copy"):
        await svc.pay_tranche(request.id, tranche.id, accounts.id, UserRole.ACCOUNTS_TEAM)
    assert tranche.status == TrancheStatus.UNPAID
    assert request.current_status == RequestStatus.PENDING_PAYMENT


# ── TT copy upload behaviour ──────────────────────────────────────────────────


async def test_tt_upload_on_unpaid_tranche_auto_pays(db_session):
    _, accounts, request, (tranche,) = await _setup(db_session)
    svc = TrancheService(db_session)
    updated, auto_paid = await svc.attach_tt_copy(
        request.id, tranche.id,
        tt_copy_url="https://drive.test/x", tt_copy_file_id="f1",
        tt_copy_filename="TT_Dep-2099-0001_T1.pdf",
        user_id=accounts.id, role=UserRole.ACCOUNTS_TEAM,
    )
    assert auto_paid is True
    assert updated.status == TrancheStatus.PAID
    assert updated.tt_copy_url == "https://drive.test/x"
    # Single tranche paid → request completed
    assert request.current_status == RequestStatus.PAYMENT_PROCESSED


async def test_duplicate_tt_upload_rejected(db_session):
    _, accounts, request, (tranche,) = await _setup(db_session)
    svc = TrancheService(db_session)
    await svc.attach_tt_copy(
        request.id, tranche.id,
        tt_copy_url="https://drive.test/x", tt_copy_file_id="f1",
        tt_copy_filename="a.pdf",
        user_id=accounts.id, role=UserRole.ACCOUNTS_TEAM,
    )
    with pytest.raises(ConflictError, match="already attached"):
        await svc.attach_tt_copy(
            request.id, tranche.id,
            tt_copy_url="https://drive.test/y", tt_copy_file_id="f2",
            tt_copy_filename="b.pdf",
            user_id=accounts.id, role=UserRole.ACCOUNTS_TEAM,
        )


async def test_super_admin_may_replace_tt_copy(db_session):
    _, accounts, request, (tranche,) = await _setup(db_session)
    admin = await make_user(db_session, UserRole.SUPER_ADMIN)
    svc = TrancheService(db_session)
    await svc.attach_tt_copy(
        request.id, tranche.id,
        tt_copy_url="https://drive.test/x", tt_copy_file_id="f1",
        tt_copy_filename="a.pdf",
        user_id=accounts.id, role=UserRole.ACCOUNTS_TEAM,
    )
    updated, auto_paid = await svc.attach_tt_copy(
        request.id, tranche.id,
        tt_copy_url="https://drive.test/y", tt_copy_file_id="f2",
        tt_copy_filename="b.pdf",
        user_id=admin.id, role=UserRole.SUPER_ADMIN,
    )
    assert auto_paid is False
    assert updated.tt_copy_url == "https://drive.test/y"
