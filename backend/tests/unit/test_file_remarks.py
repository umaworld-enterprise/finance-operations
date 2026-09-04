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
    notify_file_remark_decided,
    notify_file_remark_raised,
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


def _payload(request, category="invoice_amount_change", **extra):
    """4 Aug rework: two categories only, remark OPTIONAL. Neither the old
    amount nor the old file are sent — the server derives both from the
    selected file (10 Aug rework)."""
    from decimal import Decimal

    defaults: dict = {"new_file_number": "INV-NEW-1"}
    if category == "invoice_split":
        defaults = {
            "split_targets": [
                {"file_number": "INV-NEW-1", "amount": Decimal("600.00")},
                {"file_number": "INV-NEW-2", "amount": Decimal("400.00")},
            ]
        }
    defaults.update(extra)
    return FileRemarkCreate(
        deposit_request_id=request.id,
        category=category,
        **defaults,
    )


# ── Category-specific field validation (schema) ───────────────────────────────


def test_amount_change_requires_only_the_new_file_number():
    """The OLD file/amount (10 Aug rework) and the NEW amount (19 Aug: a
    whole-invoice change keeps the amount) are all server-derived — only the
    new file number comes from the client."""
    from uuid import uuid4

    with pytest.raises(PydanticValidationError, match="New file number"):
        FileRemarkCreate(
            deposit_request_id=uuid4(), category="invoice_amount_change",
        )
    # Valid with just the new file number.
    FileRemarkCreate(
        deposit_request_id=uuid4(), category="invoice_amount_change",
        new_file_number="N-1",
    )


def test_invoice_split_requires_target_rows_and_remark_is_optional():
    from decimal import Decimal
    from uuid import uuid4

    with pytest.raises(PydanticValidationError, match="splits to"):
        FileRemarkCreate(deposit_request_id=uuid4(), category="invoice_split")
    # A valid split needs no remark text — the rows carry the instruction.
    ok = FileRemarkCreate(
        deposit_request_id=uuid4(), category="invoice_split",
        split_targets=[{"file_number": "N-1", "amount": Decimal("10")}],
    )
    assert ok.remark is None
    # "other" is no longer a category.
    with pytest.raises(PydanticValidationError):
        FileRemarkCreate(deposit_request_id=uuid4(), category="other", remark="r")


# ── Create / resolve lifecycle ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_merchandiser_raises_remark_on_own_locked_request(db_session):
    merch, _, request = await _setup(db_session)
    svc = FileRemarkService(db_session)
    remark = await svc.create(_payload(request), merch.id, UserRole.MERCHANDISER)
    assert remark.status == "open"
    # Parent file reference is server-derived — the factory request carries
    # no invoice numbers, so it falls back to the request number.
    assert remark.old_file_number == request.request_number
    assert remark.new_file_number == "INV-NEW-1"
    # Server-derived from the file's deposit amount (factory default 1000).
    assert float(remark.old_amount) == 1000.0
    assert remark.remark is None  # optional since the 4 Aug rework
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
async def test_amounts_cannot_exceed_the_files_deposit(db_session):
    """7 Aug fix: the old (deposit) amount is the ceiling — split totals and
    the new file amount may equal it but never exceed it. (Factory deposit is
    1000; the default split payload totals exactly 1000 and passes.)"""
    from decimal import Decimal

    from app.core.exceptions import BusinessRuleError

    merch, _, request = await _setup(db_session)
    svc = FileRemarkService(db_session)

    with pytest.raises(BusinessRuleError, match="exceeds the file's"):
        await svc.create(
            _payload(
                request, category="invoice_split",
                split_targets=[
                    {"file_number": "INV-NEW-1", "amount": Decimal("800.00")},
                    {"file_number": "INV-NEW-2", "amount": Decimal("300.00")},
                ],
            ),
            merch.id, UserRole.MERCHANDISER,
        )
    # Invoice Change (19 Aug 2026): the new amount is server-derived — always
    # the file's own deposit amount, so it can never breach the ceiling.
    ok = await svc.create(_payload(request), merch.id, UserRole.MERCHANDISER)
    assert ok.status == "open"
    assert Decimal(str(ok.new_amount)) == Decimal("1000.00")


@pytest.mark.asyncio
async def test_only_payment_completed_files_are_eligible(db_session):
    """4 Aug rework: the select-file list (and the server) only accept files
    whose payment is completed."""
    from app.core.exceptions import BusinessRuleError

    merch, _, _ = await _setup(db_session)
    supplier = await make_supplier(db_session)
    customer = await make_customer(db_session)
    pending = await make_request(
        db_session, supplier=supplier, customer=customer, created_by=merch,
        status=RequestStatus.PENDING_PAYMENT,
    )
    svc = FileRemarkService(db_session)
    with pytest.raises(BusinessRuleError, match="payment-completed"):
        await svc.create(_payload(pending), merch.id, UserRole.MERCHANDISER)


@pytest.mark.asyncio
async def test_decide_flow_and_double_decision_conflict(db_session):
    """UAT Aug 2026 item 14: Accounts approve (optional note) or reject
    (mandatory reason) instead of a single Resolve."""
    from app.core.exceptions import ValidationError

    merch, accounts, request = await _setup(db_session)
    svc = FileRemarkService(db_session)
    remark = await svc.create(_payload(request), merch.id, UserRole.MERCHANDISER)

    with pytest.raises(AuthorizationError):
        await svc.decide(remark.id, "approved", merch.id, UserRole.MERCHANDISER)
    with pytest.raises(ValidationError, match="approved.*rejected"):
        await svc.decide(remark.id, "resolved", accounts.id, UserRole.ACCOUNTS_TEAM)

    approved = await svc.decide(
        remark.id, "approved", accounts.id, UserRole.ACCOUNTS_TEAM, "Invoice number updated."
    )
    assert approved.status == "approved"
    assert approved.resolved_by == accounts.id
    assert approved.response_note == "Invoice number updated."
    with pytest.raises(ConflictError, match="already been decided"):
        await svc.decide(remark.id, "rejected", accounts.id, UserRole.ACCOUNTS_TEAM, "no")


@pytest.mark.asyncio
async def test_reject_requires_a_reason(db_session):
    from app.core.exceptions import ValidationError

    merch, accounts, request = await _setup(db_session)
    svc = FileRemarkService(db_session)
    remark = await svc.create(_payload(request), merch.id, UserRole.MERCHANDISER)

    with pytest.raises(ValidationError, match="reason is mandatory"):
        await svc.decide(remark.id, "rejected", accounts.id, UserRole.ACCOUNTS_TEAM)
    rejected = await svc.decide(
        remark.id, "rejected", accounts.id, UserRole.ACCOUNTS_TEAM, "Amount mismatch."
    )
    assert rejected.status == "rejected"
    assert rejected.response_note == "Amount mismatch."


@pytest.mark.asyncio
async def test_list_scoping_and_filters(db_session):
    merch, accounts, request = await _setup(db_session)
    other = await make_user(db_session, UserRole.MERCHANDISER)
    supplier2 = await make_supplier(db_session)
    customer2 = await make_customer(db_session)
    other_req = await make_request(
        db_session, supplier=supplier2, customer=customer2, created_by=other,
        status=RequestStatus.PAYMENT_PROCESSED, is_locked=True,
    )
    svc = FileRemarkService(db_session)
    mine = await svc.create(_payload(request), merch.id, UserRole.MERCHANDISER)
    theirs = await svc.create(
        _payload(other_req, category="invoice_split"), other.id, UserRole.MERCHANDISER
    )
    await svc.decide(theirs.id, "approved", accounts.id, UserRole.ACCOUNTS_TEAM)

    own = await svc.list(merch.id, UserRole.MERCHANDISER)
    assert {r.id for r in own} == {mine.id}
    assert own[0].request_number == request.request_number
    # The request's currency travels with the remark (19 Aug 2026) — shown
    # next to every amount in the details display.
    assert own[0].currency == "USD"

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
    # "Invoice Change" was renamed "File Change" (4 Sep 2026).
    assert "File Change" in body
    assert request.request_number in body
    assert request.request_number in body and "INV-NEW-1" in body
    assert "1000.0" in body  # amounts travel in the notification


@pytest.mark.asyncio
async def test_decision_notifies_the_raiser_with_the_outcome(db_session, engine, monkeypatch):
    merch, accounts, request = await _setup(db_session)
    svc = FileRemarkService(db_session)
    approved = await svc.create(_payload(request), merch.id, UserRole.MERCHANDISER)
    await svc.decide(
        approved.id, "approved", accounts.id, UserRole.ACCOUNTS_TEAM, "Done — number updated."
    )
    rejected = await svc.create(
        _payload(request, category="invoice_split"), merch.id, UserRole.MERCHANDISER
    )
    await svc.decide(
        rejected.id, "rejected", accounts.id, UserRole.ACCOUNTS_TEAM, "Amounts do not match."
    )
    await db_session.commit()
    _patch_factory(engine, monkeypatch)

    await notify_file_remark_decided(approved.id)
    await notify_file_remark_decided(rejected.id)

    rows = (
        await db_session.execute(
            select(Notification).where(Notification.type == TYPE_FILE_REMARK_RESOLVED)
        )
    ).scalars().all()
    assert len(rows) == 2
    assert {n.user_id for n in rows} == {merch.id}
    bodies = " | ".join(n.body for n in rows)
    assert "approved and processed" in bodies
    assert "rejected" in bodies
    assert "Done — number updated." in bodies
    assert "Amounts do not match." in bodies


# ── File chains (19 Aug 2026): splits & changes selectable to any depth ──────

from decimal import Decimal
from app.core.exceptions import BusinessRuleError


@pytest.mark.asyncio
async def test_live_files_replay_the_approved_chain(db_session):
    """Root file → approved split (A + B, root fully consumed) → approved
    invoice change (A → C): the live set is exactly {C, B}, each with its
    carried amount, and everything stays anchored to the core request."""
    merch, accounts, request = await _setup(db_session)
    svc = FileRemarkService(db_session)

    split = await svc.create(
        _payload(
            request, category="invoice_split",
            split_targets=[
                {"file_number": "FILE-A", "amount": Decimal("600.00")},
                {"file_number": "FILE-B", "amount": Decimal("400.00")},
            ],
        ),
        merch.id, UserRole.MERCHANDISER,
    )
    await svc.decide(split.id, "approved", accounts.id, UserRole.ACCOUNTS_TEAM)

    change = await svc.create(
        _payload(request, file_number="FILE-A", new_file_number="FILE-C"),
        merch.id, UserRole.MERCHANDISER,
    )
    # The chained remark records the SPLIT file as its parent, with the
    # split amount — and lives on the core request (audit lands there).
    assert change.old_file_number == "FILE-A"
    assert Decimal(str(change.old_amount)) == Decimal("600.00")
    assert Decimal(str(change.new_amount)) == Decimal("600.00")
    assert change.deposit_request_id == request.id
    await svc.decide(change.id, "approved", accounts.id, UserRole.ACCOUNTS_TEAM)

    live = await svc.live_files_for_request(request)
    assert live == {"FILE-C": Decimal("600.00"), "FILE-B": Decimal("400.00")}

    # Full chain: a split-born file can be split again, capped at ITS amount.
    with pytest.raises(BusinessRuleError, match="exceeds the file's"):
        await svc.create(
            _payload(
                request, category="invoice_split", file_number="FILE-B",
                split_targets=[{"file_number": "FILE-D", "amount": Decimal("500.00")}],
            ),
            merch.id, UserRole.MERCHANDISER,
        )
    resplit = await svc.create(
        _payload(
            request, category="invoice_split", file_number="FILE-B",
            split_targets=[{"file_number": "FILE-D", "amount": Decimal("150.00")}],
        ),
        merch.id, UserRole.MERCHANDISER,
    )
    assert resplit.old_file_number == "FILE-B"
    assert Decimal(str(resplit.old_amount)) == Decimal("400.00")


@pytest.mark.asyncio
async def test_selectable_files_exclude_dead_and_open(db_session):
    """The dropdown offers live files only: a consumed parent disappears, an
    unapproved split adds nothing, and a file under an open remark is held
    back until decided. Rows carry the file number, not the supplier."""
    from app.core.exceptions import ValidationError as VErr

    merch, accounts, request = await _setup(db_session)
    svc = FileRemarkService(db_session)

    rows = await svc.selectable_files(merch.id, UserRole.MERCHANDISER)
    root = [r for r in rows if r["deposit_request_id"] == str(request.id)]
    assert len(root) == 1 and root[0]["is_root"] is True

    # Open (unapproved) split: targets NOT selectable yet; the parent file is
    # held back while its remark is open.
    split = await svc.create(
        _payload(
            request, category="invoice_split",
            split_targets=[{"file_number": "FILE-A", "amount": Decimal("1000.00")}],
        ),
        merch.id, UserRole.MERCHANDISER,
    )
    rows = await svc.selectable_files(merch.id, UserRole.MERCHANDISER)
    assert [r for r in rows if r["deposit_request_id"] == str(request.id)] == []

    # Approved: the parent was fully consumed — only FILE-A remains.
    await svc.decide(split.id, "approved", accounts.id, UserRole.ACCOUNTS_TEAM)
    rows = await svc.selectable_files(merch.id, UserRole.MERCHANDISER)
    mine = [r for r in rows if r["deposit_request_id"] == str(request.id)]
    assert [(r["file_number"], r["amount"]) for r in mine] == [("FILE-A", 1000.0)]

    # A file that is not live is refused server-side.
    with pytest.raises(VErr, match="not a live file"):
        await svc.create(
            _payload(request, file_number="NOT-A-FILE", new_file_number="X"),
            merch.id, UserRole.MERCHANDISER,
        )


# ── Invoice Value Change (4 Sep 2026) ─────────────────────────────────────────


def test_value_change_requires_a_proposed_amount():
    from decimal import Decimal
    from uuid import uuid4

    with pytest.raises(PydanticValidationError, match="proposed new amount"):
        FileRemarkCreate(deposit_request_id=uuid4(), category="invoice_value_change")
    ok = FileRemarkCreate(
        deposit_request_id=uuid4(), category="invoice_value_change",
        proposed_amount=Decimal("1250.00"),
    )
    assert ok.new_file_number is None


@pytest.mark.asyncio
async def test_value_change_full_flow_raise_approve_apply(db_session):
    """Merchandiser proposes → Accounts approve → Accounts apply the revised
    amount (separate step) → the live-file ledger carries the final figure."""
    from decimal import Decimal

    merch, accounts, request = await _setup(db_session)
    svc = FileRemarkService(db_session)
    remark = await svc.create(
        _payload(
            request, category="invoice_value_change",
            new_file_number=None, proposed_amount=Decimal("1250.00"),
        ),
        merch.id, UserRole.MERCHANDISER,
    )
    assert remark.status == "open"
    assert float(remark.old_amount) == 1000.0
    assert float(remark.proposed_amount) == 1250.0
    assert remark.new_amount is None  # nothing applied yet
    assert remark.new_file_number is None  # the number does not change

    # The revised amount cannot be applied before approval.
    with pytest.raises(ConflictError, match="APPROVED"):
        await svc.apply_revised_amount(
            remark.id, Decimal("1300.00"), accounts.id, UserRole.ACCOUNTS_TEAM
        )

    await svc.decide(remark.id, "approved", accounts.id, UserRole.ACCOUNTS_TEAM)
    # Approved but not applied → the ledger still shows the old amount, and
    # the file is held back from new remarks until the figure lands.
    live = await svc.live_files_for_request(request)
    assert live == {request.request_number: Decimal("1000.00")}
    rows = await svc.selectable_files(merch.id, UserRole.MERCHANDISER)
    assert [r for r in rows if r["deposit_request_id"] == str(request.id)] == []

    # Only decider roles may apply.
    with pytest.raises(AuthorizationError):
        await svc.apply_revised_amount(
            remark.id, Decimal("1300.00"), merch.id, UserRole.MERCHANDISER
        )

    applied = await svc.apply_revised_amount(
        remark.id, Decimal("1300.00"), accounts.id, UserRole.ACCOUNTS_TEAM
    )
    assert float(applied.new_amount) == 1300.0
    live = await svc.live_files_for_request(request)
    assert live == {request.request_number: Decimal("1300.00")}
    rows = await svc.selectable_files(merch.id, UserRole.MERCHANDISER)
    mine = [r for r in rows if r["deposit_request_id"] == str(request.id)]
    assert [(r["file_number"], r["amount"]) for r in mine] == [
        (request.request_number, 1300.0)
    ]

    # Applied exactly once.
    with pytest.raises(ConflictError, match="already been applied"):
        await svc.apply_revised_amount(
            remark.id, Decimal("1400.00"), accounts.id, UserRole.ACCOUNTS_TEAM
        )


@pytest.mark.asyncio
async def test_apply_revised_amount_only_on_value_changes(db_session):
    from decimal import Decimal

    from app.core.exceptions import BusinessRuleError

    merch, accounts, request = await _setup(db_session)
    svc = FileRemarkService(db_session)
    change = await svc.create(_payload(request), merch.id, UserRole.MERCHANDISER)
    await svc.decide(change.id, "approved", accounts.id, UserRole.ACCOUNTS_TEAM)
    with pytest.raises(BusinessRuleError, match="Invoice Value Change"):
        await svc.apply_revised_amount(
            change.id, Decimal("900.00"), accounts.id, UserRole.ACCOUNTS_TEAM
        )
