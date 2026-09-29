"""Sidebar "new since you last looked" badges (29 Sep 2026, executive
request). The count is what arrived or changed in a section since the user
last opened it; visiting the section clears it. Sections a role cannot see
are never counted.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.models.enums import RequestStatus, UserRole
from app.models.file_remark import FileRemark, FileRemarkStatus
from app.services.presence_service import (
    SECTION_ACCOUNTS,
    SECTION_FILE_REMARKS,
    SECTION_HOM,
    SECTION_MERCHANDISER,
    PresenceService,
)
from tests.factories import make_customer, make_request, make_supplier, make_user

pytestmark = pytest.mark.asyncio


def _ago(minutes: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(minutes=minutes)


async def _user(db_session, role: UserRole):
    user = await make_user(db_session, role)
    # Baseline in the past so freshly created rows count as new.
    user.unseen_since = _ago(60 * 24)
    await db_session.flush()
    return user


async def _request(db_session, status: RequestStatus):
    supplier = await make_supplier(db_session)
    customer = await make_customer(db_session)
    merch = await make_user(db_session, UserRole.MERCHANDISER)
    return await make_request(
        db_session, supplier=supplier, customer=customer, created_by=merch, status=status,
    )


async def test_accounts_badge_counts_new_pending_requests(db_session):
    accounts = await _user(db_session, UserRole.ACCOUNTS_TEAM)
    await _request(db_session, RequestStatus.PENDING_PAYMENT)
    await _request(db_session, RequestStatus.PENDING_PAYMENT)

    counts = await PresenceService(db_session).sidebar_counts(accounts.id, accounts.role)
    assert counts[SECTION_ACCOUNTS] == 2


async def test_opening_the_section_clears_the_badge(db_session):
    accounts = await _user(db_session, UserRole.ACCOUNTS_TEAM)
    await _request(db_session, RequestStatus.PENDING_PAYMENT)
    svc = PresenceService(db_session)
    assert (await svc.sidebar_counts(accounts.id, accounts.role))[SECTION_ACCOUNTS] == 1

    await svc.mark_section_viewed(accounts.id, SECTION_ACCOUNTS)
    assert (await svc.sidebar_counts(accounts.id, accounts.role))[SECTION_ACCOUNTS] == 0


async def test_work_arriving_after_the_visit_reappears(db_session):
    accounts = await _user(db_session, UserRole.ACCOUNTS_TEAM)
    svc = PresenceService(db_session)
    await svc.mark_section_viewed(accounts.id, SECTION_ACCOUNTS)
    assert (await svc.sidebar_counts(accounts.id, accounts.role))[SECTION_ACCOUNTS] == 0

    req = await _request(db_session, RequestStatus.PENDING_PAYMENT)
    req.created_at = datetime.now(timezone.utc) + timedelta(seconds=5)
    await db_session.flush()

    assert (await svc.sidebar_counts(accounts.id, accounts.role))[SECTION_ACCOUNTS] == 1


async def test_hom_badge_counts_only_awaiting_approval(db_session):
    hom = await _user(db_session, UserRole.HEAD_OF_MERCHANDISER)
    await _request(db_session, RequestStatus.PENDING_HOM_APPROVAL)
    await _request(db_session, RequestStatus.PENDING_PAYMENT)  # not HoM's queue

    counts = await PresenceService(db_session).sidebar_counts(hom.id, hom.role)
    assert counts[SECTION_HOM] == 1


async def test_sections_a_role_cannot_see_are_not_counted(db_session):
    """An accounts user has no Requests item in their sidebar, and a
    merchandiser has no Accounts Workspace — neither should be reported."""
    accounts = await _user(db_session, UserRole.ACCOUNTS_TEAM)
    merch = await _user(db_session, UserRole.MERCHANDISER)
    await _request(db_session, RequestStatus.PENDING_PAYMENT)
    svc = PresenceService(db_session)

    accounts_counts = await svc.sidebar_counts(accounts.id, accounts.role)
    assert SECTION_MERCHANDISER not in accounts_counts
    assert SECTION_HOM not in accounts_counts

    merch_counts = await svc.sidebar_counts(merch.id, merch.role)
    assert SECTION_ACCOUNTS not in merch_counts
    assert merch_counts[SECTION_MERCHANDISER] == 1


async def test_modify_request_badge_counts_raised_and_decided(db_session):
    accounts = await _user(db_session, UserRole.ACCOUNTS_TEAM)
    req = await _request(db_session, RequestStatus.PAYMENT_PROCESSED)
    db_session.add(
        FileRemark(
            deposit_request_id=req.id,
            category="invoice_amount_change",
            status=FileRemarkStatus.OPEN.value,
            created_by=accounts.id,
        )
    )
    await db_session.flush()

    counts = await PresenceService(db_session).sidebar_counts(accounts.id, accounts.role)
    assert counts[SECTION_FILE_REMARKS] == 1


async def test_badges_start_quiet_on_rollout(db_session):
    """History predating the user's baseline must not light up every badge
    the first time the feature runs."""
    accounts = await _user(db_session, UserRole.ACCOUNTS_TEAM)
    await _request(db_session, RequestStatus.PENDING_PAYMENT)
    accounts.unseen_since = datetime.now(timezone.utc) + timedelta(seconds=5)
    await db_session.flush()

    counts = await PresenceService(db_session).sidebar_counts(accounts.id, accounts.role)
    assert counts[SECTION_ACCOUNTS] == 0


async def test_badges_are_per_user(db_session):
    a = await _user(db_session, UserRole.ACCOUNTS_TEAM)
    b = await _user(db_session, UserRole.ACCOUNTS_TEAM)
    await _request(db_session, RequestStatus.PENDING_PAYMENT)
    svc = PresenceService(db_session)

    await svc.mark_section_viewed(a.id, SECTION_ACCOUNTS)
    assert (await svc.sidebar_counts(a.id, a.role))[SECTION_ACCOUNTS] == 0
    assert (await svc.sidebar_counts(b.id, b.role))[SECTION_ACCOUNTS] == 1
