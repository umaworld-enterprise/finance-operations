"""Tranche workflow: merchandiser edit rights, Accounts payments, TT copies,
paid-tranche locking, request completion, audit events, and the pending-and-
untouched guard on merchandiser tranche changes (Aug 2026 batch, item 2.3)."""

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
from app.models.payment import PaymentDetails
from app.schemas.tranche import TranchePaymentDetailsUpdate, TrancheCreate, TrancheUpdate
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
    """Attach a TT copy directly (without payment details)."""
    for t in tranches:
        t.tt_copy_url = f"https://drive.test/tt-{t.id}.pdf"
    await db_session.flush()


async def _payable(db_session, *tranches):
    """pay_tranche requires the TT copy AND payment details (payment date +
    bank) — satisfy both so tests can exercise the payment paths beyond that
    gate. Reference number AND accounts remarks stay empty: both are optional
    (remarks reverted to optional 4 Aug 2026)."""
    for t in tranches:
        t.tt_copy_url = f"https://drive.test/tt-{t.id}.pdf"
        t.payment_date = date(2026, 8, 1)
        t.bank = "Test Bank"
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
    await _payable(db_session, tranche)
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
    await _payable(db_session, t1)
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
    await _payable(db_session, t1, t2)
    svc = TrancheService(db_session)
    await svc.pay_tranche(request.id, t1.id, accounts.id, UserRole.ACCOUNTS_TEAM)
    await svc.pay_tranche(request.id, t2.id, accounts.id, UserRole.ACCOUNTS_TEAM)
    assert request.current_status == RequestStatus.PAYMENT_PROCESSED
    assert request.is_locked is True
    logs = await _audit_rows(db_session, "deposit_requests", request.id)
    assert any(log.new_value == RequestStatus.PAYMENT_PROCESSED.value for log in logs)


async def test_final_tranche_pay_syncs_request_payment_details(db_session):
    """The request-level Payment Details form is gone (Aug 2026 follow-up) —
    analytics and reports read payment_details.payment_date/payment_status,
    so paying the FINAL tranche derives them: latest tranche payment date +
    'processed'."""
    from app.repositories.payment_repo import PaymentRepository

    _, accounts, request, (t1, t2) = await _setup(
        db_session, tranche_amounts=("600.00", "400.00")
    )
    await _payable(db_session, t1, t2)
    t2.payment_date = date(2026, 8, 5)  # later than t1's 2026-08-01
    await db_session.flush()

    svc = TrancheService(db_session)
    repo = PaymentRepository(db_session)
    await svc.pay_tranche(request.id, t1.id, accounts.id, UserRole.ACCOUNTS_TEAM)
    assert await repo.get_by_request_id(request.id) is None  # partial: no sync yet
    await svc.pay_tranche(request.id, t2.id, accounts.id, UserRole.ACCOUNTS_TEAM)

    payment = await repo.get_by_request_id(request.id)
    assert payment is not None
    assert payment.payment_date == date(2026, 8, 5)
    assert payment.payment_status == "processed"


async def test_payment_details_sync_updates_existing_partial_row(db_session):
    """A partial payment_details row (e.g. a pre-recorded ship date) is
    updated in place — never replaced — when the final tranche is paid."""
    from app.repositories.payment_repo import PaymentRepository

    _, accounts, request, (tranche,) = await _setup(db_session)
    await _payable(db_session, tranche)
    db_session.add(
        PaymentDetails(
            id=uuid.uuid4(),
            deposit_request_id=request.id,
            ship_date=date(2026, 8, 20),
        )
    )
    await db_session.flush()

    svc = TrancheService(db_session)
    await svc.pay_tranche(request.id, tranche.id, accounts.id, UserRole.ACCOUNTS_TEAM)

    payment = await PaymentRepository(db_session).get_by_request_id(request.id)
    assert payment.ship_date == date(2026, 8, 20)  # preserved
    assert payment.payment_date == date(2026, 8, 1)
    assert payment.payment_status == "processed"


async def test_double_payment_rejected(db_session):
    _, accounts, request, (t1, t2) = await _setup(
        db_session, tranche_amounts=("600.00", "400.00")
    )
    await _payable(db_session, t1)
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
    await _payable(db_session, tranche)
    request.current_status = RequestStatus.HOLD_BY_ACCOUNTS
    await db_session.flush()
    svc = TrancheService(db_session)
    with pytest.raises(ConflictError, match="pending payment"):
        await svc.pay_tranche(request.id, tranche.id, accounts.id, UserRole.ACCOUNTS_TEAM)


async def test_pay_tranche_without_tt_copy_rejected(db_session):
    """C6 (still in force): a tranche must never become PAID without its TT
    copy — the error names everything that is still missing."""
    _, accounts, request, (tranche,) = await _setup(db_session)
    svc = TrancheService(db_session)
    with pytest.raises(ConflictError, match="TT copy"):
        await svc.pay_tranche(request.id, tranche.id, accounts.id, UserRole.ACCOUNTS_TEAM)
    assert tranche.status == TrancheStatus.UNPAID
    assert request.current_status == RequestStatus.PENDING_PAYMENT


async def test_pay_tranche_without_payment_details_rejected(db_session):
    """Aug 2026, item 3.1: the TT copy alone is not enough — payment date and
    bank must also be recorded before Mark Paid."""
    _, accounts, request, (tranche,) = await _setup(db_session)
    await _with_tt(db_session, tranche)
    svc = TrancheService(db_session)
    with pytest.raises(ConflictError, match="payment date and bank"):
        await svc.pay_tranche(request.id, tranche.id, accounts.id, UserRole.ACCOUNTS_TEAM)
    assert tranche.status == TrancheStatus.UNPAID


async def test_pay_tranche_does_not_require_accounts_remarks(db_session):
    """4 Aug 2026: accounts remarks reverted to OPTIONAL — TT copy, payment
    date and bank are sufficient to mark a tranche paid."""
    _, accounts, request, (tranche,) = await _setup(db_session)
    await _payable(db_session, tranche)  # sets no accounts_remarks
    svc = TrancheService(db_session)
    paid = await svc.pay_tranche(request.id, tranche.id, accounts.id, UserRole.ACCOUNTS_TEAM)
    assert paid.status == TrancheStatus.PAID
    assert paid.accounts_remarks is None


async def test_pay_tranche_does_not_require_reference_number(db_session):
    """The payment reference number is optional (Aug 2026, item 3.2)."""
    _, accounts, request, (tranche,) = await _setup(db_session)
    await _payable(db_session, tranche)  # sets no reference number
    svc = TrancheService(db_session)
    paid = await svc.pay_tranche(request.id, tranche.id, accounts.id, UserRole.ACCOUNTS_TEAM)
    assert paid.status == TrancheStatus.PAID
    assert paid.payment_reference_number is None


# ── Reject Tranche workflow (Aug 2026 — breaks the touched-lock deadlock) ─────


async def test_reject_tranche_sets_record_and_drops_amount_from_totals(db_session):
    merch, accounts, request, (t1, t2) = await _setup(
        db_session, tranche_amounts=("600.00", "400.00")
    )
    svc = TrancheService(db_session)
    rejected = await svc.reject_tranche(
        request.id, t2.id, "Wrong amount entered", accounts.id, UserRole.ACCOUNTS_TEAM
    )
    assert rejected.status == TrancheStatus.REJECTED
    assert rejected.rejection_reason == "Wrong amount entered"
    assert rejected.rejected_by == accounts.id
    assert rejected.rejected_at is not None
    # The rejected amount stops counting toward the derived deposit_amount.
    assert Decimal(str(request.deposit_amount)) == Decimal("600.00")
    logs = await _audit_rows(db_session, "payment_tranches", t2.id)
    assert any("Wrong amount entered" in (log.new_value or "") for log in logs)


async def test_reject_requires_reason_and_valid_state(db_session):
    merch, accounts, request, (t1, t2) = await _setup(
        db_session, tranche_amounts=("600.00", "400.00")
    )
    svc = TrancheService(db_session)
    with pytest.raises(ValidationError, match="reason is mandatory"):
        await svc.reject_tranche(request.id, t2.id, "   ", accounts.id, UserRole.ACCOUNTS_TEAM)
    with pytest.raises(AuthorizationError):
        await svc.reject_tranche(request.id, t2.id, "r", merch.id, UserRole.MERCHANDISER)
    # Paid tranches are immutable — reallocation goes through Adjust Invoices.
    await _payable(db_session, t1)
    await svc.pay_tranche(request.id, t1.id, accounts.id, UserRole.ACCOUNTS_TEAM)
    with pytest.raises(ConflictError, match="already paid"):
        await svc.reject_tranche(request.id, t1.id, "r", accounts.id, UserRole.ACCOUNTS_TEAM)
    # Double rejection is a conflict.
    await svc.reject_tranche(request.id, t2.id, "r", accounts.id, UserRole.ACCOUNTS_TEAM)
    with pytest.raises(ConflictError, match="already rejected"):
        await svc.reject_tranche(request.id, t2.id, "r", accounts.id, UserRole.ACCOUNTS_TEAM)


async def test_rejected_tranche_is_fully_inert(db_session):
    merch, accounts, request, (t1, t2) = await _setup(
        db_session, tranche_amounts=("600.00", "400.00")
    )
    svc = TrancheService(db_session)
    await svc.reject_tranche(request.id, t2.id, "r", accounts.id, UserRole.ACCOUNTS_TEAM)

    with pytest.raises(ConflictError, match="rejected"):
        await svc.pay_tranche(request.id, t2.id, accounts.id, UserRole.ACCOUNTS_TEAM)
    with pytest.raises(ConflictError, match="rejected"):
        await svc.update_payment_details(
            request.id, t2.id, TranchePaymentDetailsUpdate(bank="HSBC"),
            accounts.id, UserRole.ACCOUNTS_TEAM,
        )
    with pytest.raises(ConflictError, match="rejected"):
        await svc.attach_tt_copy(
            request.id, t2.id,
            tt_copy_url="https://drive.test/x", tt_copy_file_id="f",
            tt_copy_filename="a.pdf",
            user_id=accounts.id, role=UserRole.ACCOUNTS_TEAM,
        )
    with pytest.raises(ConflictError, match="rejected"):
        await svc.update_tranche(
            request.id, t2.id, TrancheUpdate(amount=Decimal("1.00")),
            merch.id, UserRole.SUPER_ADMIN,
        )
    with pytest.raises(ConflictError, match="rejected"):
        await svc.delete_tranche(request.id, t2.id, merch.id, UserRole.SUPER_ADMIN)


async def test_rejection_unlocks_adding_replacement_tranches(db_session):
    """THE deadlock case: Accounts wrote request-wide (payment row) →
    merchandiser is frozen → Accounts reject the wrong tranche → merchandiser
    can ADD again, with the ceiling computed from live tranches only."""
    merch, accounts, request, (t1, t2) = await _setup(
        db_session, tranche_amounts=("600.00", "9000.00")
    )
    await _seed_bank(db_session)
    svc = TrancheService(db_session)
    # Request-wide accounts write — merchandiser frozen (19 Aug 2026: only
    # request-wide touches freeze everything; per-tranche details lock just
    # that tranche).
    await _add_payment_row(db_session, request)
    # Accounts also record details on t1 (locks t1 individually).
    await svc.update_payment_details(
        request.id, t1.id,
        TranchePaymentDetailsUpdate(payment_date=date(2026, 8, 1), bank="HSBC (USD)"),
        accounts.id, UserRole.ACCOUNTS_TEAM,
    )
    with pytest.raises(ConflictError, match="no longer be changed"):
        await svc.add_tranche(
            request.id,
            TrancheCreate(amount=Decimal("400.00"), tentative_payment_date=date(2026, 9, 1)),
            merch.id, UserRole.MERCHANDISER,
        )
    # Accounts reject the wrong tranche (9000) — adding unlocks.
    await svc.reject_tranche(request.id, t2.id, "wrong value", accounts.id, UserRole.ACCOUNTS_TEAM)
    added = await svc.add_tranche(
        request.id,
        TrancheCreate(amount=Decimal("9000.00"), tentative_payment_date=date(2026, 9, 1)),
        merch.id, UserRole.MERCHANDISER,
    )
    assert added.tranche_number == 3
    # Ceiling counts live tranches only: 600 + 9000 = 9600 ≤ 10000; another
    # 9000 would breach it.
    with pytest.raises(ValidationError, match="cannot exceed"):
        await svc.add_tranche(
            request.id,
            TrancheCreate(amount=Decimal("9000.00"), tentative_payment_date=date(2026, 9, 1)),
            merch.id, UserRole.MERCHANDISER,
        )
    # Edits of the remaining live tranche stay frozen (request-wide touch).
    with pytest.raises(ConflictError, match="no longer be changed"):
        await svc.update_tranche(
            request.id, t1.id, TrancheUpdate(amount=Decimal("500.00")),
            merch.id, UserRole.MERCHANDISER,
        )


async def test_paying_last_live_tranche_completes_despite_rejected_sibling(db_session):
    _, accounts, request, (t1, t2) = await _setup(
        db_session, tranche_amounts=("600.00", "400.00")
    )
    svc = TrancheService(db_session)
    await svc.reject_tranche(request.id, t2.id, "r", accounts.id, UserRole.ACCOUNTS_TEAM)
    await _payable(db_session, t1)
    await svc.pay_tranche(request.id, t1.id, accounts.id, UserRole.ACCOUNTS_TEAM)
    assert request.current_status == RequestStatus.PAYMENT_PROCESSED
    assert request.is_locked is True


# ── TT copy upload behaviour ──────────────────────────────────────────────────


async def test_tt_upload_no_longer_auto_pays(db_session):
    """Aug 2026, item 3.1 — DELIBERATE REVERSAL of July's C6 auto-pay: the
    upload only attaches the TT copy; status changes exclusively through the
    explicit pay action once payment details are also recorded."""
    _, accounts, request, (tranche,) = await _setup(db_session)
    svc = TrancheService(db_session)
    updated = await svc.attach_tt_copy(
        request.id, tranche.id,
        tt_copy_url="https://drive.test/x", tt_copy_file_id="f1",
        tt_copy_filename="TT_Dep-2099-0001_T1.pdf",
        user_id=accounts.id, role=UserRole.ACCOUNTS_TEAM,
    )
    assert updated.status == TrancheStatus.UNPAID
    assert updated.tt_copy_url == "https://drive.test/x"
    assert request.current_status == RequestStatus.PENDING_PAYMENT
    assert request.is_locked is False


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


# ── Pending-and-untouched guard on merchandiser tranche changes ───────────────


async def _add_payment_row(db_session, request):
    """Request-wide accounts write. Carries a ship_date so it registers as a
    touch — a bare row holding only a payment date no longer freezes anything
    (19 Aug 2026: that is what a reopened file keeps)."""
    db_session.add(
        PaymentDetails(
            id=uuid.uuid4(),
            deposit_request_id=request.id,
            ship_date=date(2026, 8, 1),
        )
    )
    await db_session.flush()


async def _seed_bank(db_session, name="HSBC"):
    """Bank master (Aug 2026): update_payment_details validates the bank
    against the active list, composed with the request currency."""
    from app.models.masters import BankMaster

    db_session.add(BankMaster(id=uuid.uuid4(), name=name))
    await db_session.flush()


async def test_edit_blocked_once_accounts_saved_payment_details(db_session):
    merch, _, request, (tranche,) = await _setup(db_session)
    await _add_payment_row(db_session, request)
    svc = TrancheService(db_session)
    with pytest.raises(ConflictError, match="no longer be changed"):
        await svc.update_tranche(
            request.id, tranche.id, TrancheUpdate(amount=Decimal("500.00")),
            merch.id, UserRole.MERCHANDISER,
        )


async def test_tt_copy_locks_only_that_tranche(db_session):
    """19 Aug 2026 relaxation: a TT copy on t1 locks t1 for the merchandiser,
    but its untouched sibling t2 stays editable."""
    merch, _, request, (t1, t2) = await _setup(
        db_session, tranche_amounts=("600.00", "400.00")
    )
    await _with_tt(db_session, t1)
    svc = TrancheService(db_session)
    with pytest.raises(ConflictError, match="started processing"):
        await svc.update_tranche(
            request.id, t1.id, TrancheUpdate(amount=Decimal("500.00")),
            merch.id, UserRole.MERCHANDISER,
        )
    with pytest.raises(ConflictError, match="started processing"):
        await svc.delete_tranche(request.id, t1.id, merch.id, UserRole.MERCHANDISER)
    updated = await svc.update_tranche(
        request.id, t2.id, TrancheUpdate(amount=Decimal("500.00")),
        merch.id, UserRole.MERCHANDISER,
    )
    assert updated.amount == Decimal("500.00")


async def test_add_tranche_reopens_processed_request(db_session):
    """19 Aug 2026: adding a tranche to a fully paid file reopens it — back
    to pending_payment, unlocked, completion marker stepped back — and it
    completes again once the new tranche is paid."""
    from sqlalchemy import select as sa_select

    merch, accounts, request, (t1,) = await _setup(db_session)
    svc = TrancheService(db_session)
    await _payable(db_session, t1)
    await svc.pay_tranche(request.id, t1.id, accounts.id, UserRole.ACCOUNTS_TEAM)
    assert request.current_status == RequestStatus.PAYMENT_PROCESSED
    assert request.is_locked is True

    added = await svc.add_tranche(
        request.id,
        TrancheCreate(amount=Decimal("500.00"), tentative_payment_date=date(2026, 9, 1)),
        merch.id, UserRole.MERCHANDISER,
    )
    assert request.current_status == RequestStatus.PENDING_PAYMENT
    assert request.is_locked is False
    assert Decimal(str(request.deposit_amount)) == Decimal("1500.00")
    payment_row = (
        await db_session.execute(
            sa_select(PaymentDetails).where(
                PaymentDetails.deposit_request_id == request.id
            )
        )
    ).scalar_one()
    assert payment_row.payment_status is None  # completion marker stepped back
    assert payment_row.payment_date is not None  # paid-so-far date kept

    # The reopened file is a normal pending request: the new tranche can be
    # edited (no request-wide freeze from the leftover payment row)...
    updated = await svc.update_tranche(
        request.id, added.id, TrancheUpdate(amount=Decimal("400.00")),
        merch.id, UserRole.MERCHANDISER,
    )
    assert updated.amount == Decimal("400.00")
    # ...and paying it completes the file again.
    await _payable(db_session, added)
    await svc.pay_tranche(request.id, added.id, accounts.id, UserRole.ACCOUNTS_TEAM)
    assert request.current_status == RequestStatus.PAYMENT_PROCESSED
    assert request.is_locked is True
    assert payment_row.payment_status == "processed"


async def test_deleting_the_reopening_tranche_recompletes_the_request(db_session):
    """Dynamic status (19 Aug 2026 follow-up): if the tranche that reopened a
    completed file is deleted again, every live tranche is paid once more —
    the request must flip straight back to payment_processed and re-lock."""
    from sqlalchemy import select as sa_select

    merch, accounts, request, (t1,) = await _setup(db_session)
    svc = TrancheService(db_session)
    await _payable(db_session, t1)
    await svc.pay_tranche(request.id, t1.id, accounts.id, UserRole.ACCOUNTS_TEAM)

    added = await svc.add_tranche(
        request.id,
        TrancheCreate(amount=Decimal("500.00"), tentative_payment_date=date(2026, 9, 1)),
        merch.id, UserRole.MERCHANDISER,
    )
    assert request.current_status == RequestStatus.PENDING_PAYMENT

    await svc.delete_tranche(request.id, added.id, merch.id, UserRole.MERCHANDISER)
    assert request.current_status == RequestStatus.PAYMENT_PROCESSED
    assert request.is_locked is True
    assert Decimal(str(request.deposit_amount)) == Decimal("1000.00")
    payment_row = (
        await db_session.execute(
            sa_select(PaymentDetails).where(
                PaymentDetails.deposit_request_id == request.id
            )
        )
    ).scalar_one()
    assert payment_row.payment_status == "processed"  # marker re-derived


async def test_reopen_by_adding_respects_invoice_ceiling_and_roles(db_session):
    merch, accounts, request, (t1,) = await _setup(db_session)
    svc = TrancheService(db_session)
    await _payable(db_session, t1)
    await svc.pay_tranche(request.id, t1.id, accounts.id, UserRole.ACCOUNTS_TEAM)

    # Ceiling: 1000 paid + 9500 would breach the 10000 invoice total.
    with pytest.raises(ValidationError, match="cannot exceed"):
        await svc.add_tranche(
            request.id,
            TrancheCreate(amount=Decimal("9500.00"), tentative_payment_date=date(2026, 9, 1)),
            merch.id, UserRole.MERCHANDISER,
        )
    assert request.current_status == RequestStatus.PAYMENT_PROCESSED
    # Only the request's merchandiser (or super admin) can reopen by adding.
    with pytest.raises(AuthorizationError):
        await svc.add_tranche(
            request.id,
            TrancheCreate(amount=Decimal("100.00"), tentative_payment_date=date(2026, 9, 1)),
            accounts.id, UserRole.ACCOUNTS_TEAM,
        )


async def test_paid_tranche_no_longer_freezes_siblings(db_session):
    """The 19 Aug 2026 requirement: after a tranche is paid, the merchandiser
    can still ADD tranches and EDIT/DELETE the untouched unpaid ones. The paid
    tranche itself stays immutable."""
    merch, accounts, request, (t1, t2) = await _setup(
        db_session, tranche_amounts=("600.00", "400.00")
    )
    svc = TrancheService(db_session)
    await _payable(db_session, t1)
    await svc.pay_tranche(request.id, t1.id, accounts.id, UserRole.ACCOUNTS_TEAM)

    added = await svc.add_tranche(
        request.id,
        TrancheCreate(amount=Decimal("100.00"), tentative_payment_date=date(2026, 9, 1)),
        merch.id, UserRole.MERCHANDISER,
    )
    assert added.tranche_number == 3
    updated = await svc.update_tranche(
        request.id, t2.id, TrancheUpdate(amount=Decimal("300.00")),
        merch.id, UserRole.MERCHANDISER,
    )
    assert updated.amount == Decimal("300.00")
    await svc.delete_tranche(request.id, added.id, merch.id, UserRole.MERCHANDISER)
    with pytest.raises(ConflictError, match="already paid"):
        await svc.update_tranche(
            request.id, t1.id, TrancheUpdate(amount=Decimal("1.00")),
            merch.id, UserRole.MERCHANDISER,
        )


async def test_edit_blocked_when_request_not_pending(db_session):
    merch, _, request, (tranche,) = await _setup(db_session)
    request.current_status = RequestStatus.HOLD_BY_ACCOUNTS
    await db_session.flush()
    svc = TrancheService(db_session)
    with pytest.raises(ConflictError, match="still pending"):
        await svc.update_tranche(
            request.id, tranche.id, TrancheUpdate(amount=Decimal("500.00")),
            merch.id, UserRole.MERCHANDISER,
        )


async def test_super_admin_can_still_edit_after_accounts_touch(db_session):
    _, _, request, (tranche,) = await _setup(db_session)
    await _add_payment_row(db_session, request)
    admin = await make_user(db_session, UserRole.SUPER_ADMIN)
    svc = TrancheService(db_session)
    updated = await svc.update_tranche(
        request.id, tranche.id, TrancheUpdate(amount=Decimal("500.00")),
        admin.id, UserRole.SUPER_ADMIN,
    )
    assert updated.amount == Decimal("500.00")


# ── Merchandiser add / delete tranches ────────────────────────────────────────


async def test_add_tranche_numbers_and_syncs_totals(db_session):
    merch, _, request, (t1,) = await _setup(db_session)
    svc = TrancheService(db_session)
    added = await svc.add_tranche(
        request.id,
        TrancheCreate(amount=Decimal("500.00"), tentative_payment_date=date(2026, 9, 1)),
        merch.id, UserRole.MERCHANDISER,
    )
    assert added.tranche_number == t1.tranche_number + 1
    assert Decimal(str(request.deposit_amount)) == Decimal("1500.00")
    logs = await _audit_rows(db_session, "payment_tranches", added.id)
    assert len(logs) == 1  # create audit row


async def test_add_tranche_cannot_exceed_invoice_total(db_session):
    merch, _, request, _ = await _setup(db_session, tranche_amounts=("9000.00",))
    svc = TrancheService(db_session)
    with pytest.raises(ValidationError, match="cannot exceed"):
        await svc.add_tranche(
            request.id,
            TrancheCreate(amount=Decimal("2000.00"), tentative_payment_date=date(2026, 9, 1)),
            merch.id, UserRole.MERCHANDISER,
        )


async def test_add_tranche_blocked_after_accounts_touch(db_session):
    merch, _, request, _ = await _setup(db_session)
    await _add_payment_row(db_session, request)
    svc = TrancheService(db_session)
    with pytest.raises(ConflictError, match="no longer be changed"):
        await svc.add_tranche(
            request.id,
            TrancheCreate(amount=Decimal("100.00"), tentative_payment_date=date(2026, 9, 1)),
            merch.id, UserRole.MERCHANDISER,
        )


async def test_delete_tranche_syncs_totals(db_session):
    merch, _, request, (t1, t2) = await _setup(
        db_session, tranche_amounts=("600.00", "400.00")
    )
    svc = TrancheService(db_session)
    label = await svc.delete_tranche(request.id, t2.id, merch.id, UserRole.MERCHANDISER)
    assert label == "Deposit - Tranche 2"
    assert Decimal(str(request.deposit_amount)) == Decimal("600.00")
    remaining = await svc.list_for_request(request.id)
    assert [t.id for t in remaining] == [t1.id]


async def test_last_tranche_cannot_be_deleted(db_session):
    merch, _, request, (tranche,) = await _setup(db_session)
    svc = TrancheService(db_session)
    with pytest.raises(ValidationError, match="at least one tranche"):
        await svc.delete_tranche(request.id, tranche.id, merch.id, UserRole.MERCHANDISER)


async def test_delete_blocked_after_accounts_touch(db_session):
    merch, _, request, (t1, t2) = await _setup(
        db_session, tranche_amounts=("600.00", "400.00")
    )
    await _add_payment_row(db_session, request)
    svc = TrancheService(db_session)
    with pytest.raises(ConflictError, match="no longer be changed"):
        await svc.delete_tranche(request.id, t2.id, merch.id, UserRole.MERCHANDISER)


async def test_non_owner_cannot_add_or_delete(db_session):
    _, _, request, (t1, t2) = await _setup(
        db_session, tranche_amounts=("600.00", "400.00")
    )
    other = await make_user(db_session, UserRole.MERCHANDISER)
    svc = TrancheService(db_session)
    with pytest.raises(AuthorizationError):
        await svc.add_tranche(
            request.id,
            TrancheCreate(amount=Decimal("100.00"), tentative_payment_date=date(2026, 9, 1)),
            other.id, UserRole.MERCHANDISER,
        )
    with pytest.raises(AuthorizationError):
        await svc.delete_tranche(request.id, t2.id, other.id, UserRole.MERCHANDISER)


async def test_accounts_touched_reason_is_none_when_untouched(db_session):
    _, _, request, _ = await _setup(db_session)
    svc = TrancheService(db_session)
    assert await svc.accounts_touched_reason(request.id) is None


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
    updated = await svc.attach_tt_copy(
        request.id, tranche.id,
        tt_copy_url="https://drive.test/y", tt_copy_file_id="f2",
        tt_copy_filename="b.pdf",
        user_id=admin.id, role=UserRole.SUPER_ADMIN,
    )
    assert updated.tt_copy_url == "https://drive.test/y"
    assert updated.status == TrancheStatus.UNPAID


# ── Per-tranche payment details (Aug 2026, item 3) ────────────────────────────


async def test_update_payment_details_saves_and_audits(db_session):
    _, accounts, request, (tranche,) = await _setup(db_session)
    await _seed_bank(db_session)
    svc = TrancheService(db_session)
    updated = await svc.update_payment_details(
        request.id, tranche.id,
        TranchePaymentDetailsUpdate(payment_date=date(2026, 8, 2), bank="HSBC (USD)"),
        accounts.id, UserRole.ACCOUNTS_TEAM,
    )
    assert updated.payment_date == date(2026, 8, 2)
    assert updated.bank == "HSBC (USD)"  # composed "{name} ({request currency})"
    assert updated.payment_reference_number is None
    logs = await _audit_rows(db_session, "payment_tranches", tranche.id)
    assert {log.field_name for log in logs} == {"payment_date", "bank"}


async def test_bank_must_come_from_the_master(db_session):
    """Bank master (Aug 2026): dropdown-only — arbitrary values are rejected,
    and an empty master blocks bank entry entirely."""
    _, accounts, request, (tranche,) = await _setup(db_session)
    svc = TrancheService(db_session)
    # Empty master → blocked.
    with pytest.raises(ValidationError, match="No banks are configured"):
        await svc.update_payment_details(
            request.id, tranche.id,
            TranchePaymentDetailsUpdate(bank="HSBC (USD)"),
            accounts.id, UserRole.ACCOUNTS_TEAM,
        )
    await _seed_bank(db_session)
    # Wrong composition (missing currency suffix) → rejected.
    with pytest.raises(ValidationError, match="not an available bank"):
        await svc.update_payment_details(
            request.id, tranche.id,
            TranchePaymentDetailsUpdate(bank="HSBC"),
            accounts.id, UserRole.ACCOUNTS_TEAM,
        )
    # Unknown bank → rejected.
    with pytest.raises(ValidationError, match="not an available bank"):
        await svc.update_payment_details(
            request.id, tranche.id,
            TranchePaymentDetailsUpdate(bank="Barclays (USD)"),
            accounts.id, UserRole.ACCOUNTS_TEAM,
        )
    # Details without a bank change are unaffected by the master.
    updated = await svc.update_payment_details(
        request.id, tranche.id,
        TranchePaymentDetailsUpdate(payment_date=date(2026, 8, 2)),
        accounts.id, UserRole.ACCOUNTS_TEAM,
    )
    assert updated.payment_date == date(2026, 8, 2)


async def test_merchandiser_cannot_record_payment_details(db_session):
    merch, _, request, (tranche,) = await _setup(db_session)
    svc = TrancheService(db_session)
    with pytest.raises(AuthorizationError):
        await svc.update_payment_details(
            request.id, tranche.id,
            TranchePaymentDetailsUpdate(bank="HSBC"),
            merch.id, UserRole.MERCHANDISER,
        )


async def test_payment_details_locked_once_paid(db_session):
    _, accounts, request, (tranche,) = await _setup(db_session)
    await _payable(db_session, tranche)
    svc = TrancheService(db_session)
    await svc.pay_tranche(request.id, tranche.id, accounts.id, UserRole.ACCOUNTS_TEAM)
    with pytest.raises(ConflictError, match="locked"):
        await svc.update_payment_details(
            request.id, tranche.id,
            TranchePaymentDetailsUpdate(bank="Other Bank"),
            accounts.id, UserRole.ACCOUNTS_TEAM,
        )


async def test_tranche_payment_details_lock_only_that_tranche(db_session):
    """Recorded tranche payment details lock that tranche against merchandiser
    changes; its untouched sibling stays editable (19 Aug 2026 relaxation of
    the Phase 3 guard)."""
    merch, accounts, request, (t1, t2) = await _setup(
        db_session, tranche_amounts=("600.00", "400.00")
    )
    await _seed_bank(db_session)
    svc = TrancheService(db_session)
    await svc.update_payment_details(
        request.id, t1.id,
        TranchePaymentDetailsUpdate(payment_date=date(2026, 8, 2), bank="HSBC (USD)"),
        accounts.id, UserRole.ACCOUNTS_TEAM,
    )
    with pytest.raises(ConflictError, match="started processing"):
        await svc.update_tranche(
            request.id, t1.id, TrancheUpdate(amount=Decimal("500.00")),
            merch.id, UserRole.MERCHANDISER,
        )
    updated = await svc.update_tranche(
        request.id, t2.id, TrancheUpdate(amount=Decimal("500.00")),
        merch.id, UserRole.MERCHANDISER,
    )
    assert updated.amount == Decimal("500.00")
