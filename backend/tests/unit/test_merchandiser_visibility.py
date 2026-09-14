"""All requests visible to ALL merchandisers WITH FULL RIGHTS (11 Sep 2026,
executive request): the repo no longer scopes MERCHANDISER listings to own
requests, and the ownership guards on the write paths (edit / status change /
tranche actions) are removed — any merchandiser may act on any request. Role
gates (only merchandisers / super admins touch tranches, etc.) are intact."""

from datetime import date
from decimal import Decimal

import pytest

from app.models.enums import RequestStatus, UserRole
from app.repositories.deposit_request_repo import DepositRequestRepository
from app.schemas.deposit_request import DepositRequestUpdate
from app.schemas.tranche import TrancheCreate
from app.services.deposit_request_service import DepositRequestService
from app.services.tranche_service import TrancheService
from tests.factories import make_customer, make_request, make_supplier, make_user

pytestmark = pytest.mark.asyncio


async def _two_merchandisers_with_requests(db_session):
    merch_a = await make_user(db_session, UserRole.MERCHANDISER)
    merch_b = await make_user(db_session, UserRole.MERCHANDISER)
    supplier = await make_supplier(db_session)
    customer = await make_customer(db_session)
    req_a = await make_request(
        db_session, supplier=supplier, customer=customer, created_by=merch_a,
        status=RequestStatus.PENDING_PAYMENT,
    )
    req_b = await make_request(
        db_session, supplier=supplier, customer=customer, created_by=merch_b,
        status=RequestStatus.PENDING_PAYMENT,
    )
    return merch_a, merch_b, req_a, req_b


async def test_merchandiser_sees_all_requests(db_session):
    merch_a, _merch_b, req_a, req_b = await _two_merchandisers_with_requests(db_session)
    repo = DepositRequestRepository(db_session)
    items = await repo.list_for_role(UserRole.MERCHANDISER, merch_a.id, limit=100)
    ids = {r.id for r in items}
    assert req_a.id in ids
    assert req_b.id in ids
    assert await repo.count_for_role(UserRole.MERCHANDISER, merch_a.id) >= 2


async def test_mine_only_filter_still_available(db_session):
    """The Merchandiser chip in the filter bar narrows back down to one
    person's requests via the created_by param."""
    merch_a, _merch_b, req_a, req_b = await _two_merchandisers_with_requests(db_session)
    repo = DepositRequestRepository(db_session)
    items = await repo.list_for_role(
        UserRole.MERCHANDISER, merch_a.id, created_by=merch_a.id, limit=100,
    )
    ids = {r.id for r in items}
    assert req_a.id in ids
    assert req_b.id not in ids


async def test_non_owner_merchandiser_can_edit(db_session):
    merch_a, _merch_b, _req_a, req_b = await _two_merchandisers_with_requests(db_session)
    svc = DepositRequestService(db_session)
    updated = await svc.update(
        req_b.id,
        DepositRequestUpdate(sunshine_invoice_number="CROSS-EDIT-1"),
        merch_a.id, UserRole.MERCHANDISER,
    )
    assert updated.sunshine_invoice_number == "CROSS-EDIT-1"


async def test_non_owner_merchandiser_can_change_status(db_session):
    merch_a, _merch_b, _req_a, req_b = await _two_merchandisers_with_requests(db_session)
    svc = DepositRequestService(db_session)
    updated = await svc.transition_status(
        req_b.id, RequestStatus.HOLD_BY_MERCHANDISER,
        merch_a.id, UserRole.MERCHANDISER,
    )
    assert updated.current_status == RequestStatus.HOLD_BY_MERCHANDISER


async def test_non_owner_merchandiser_can_add_tranche(db_session):
    merch_a, _merch_b, _req_a, req_b = await _two_merchandisers_with_requests(db_session)
    svc = TrancheService(db_session)
    tranche = await svc.add_tranche(
        req_b.id,
        TrancheCreate(amount=Decimal("100.00"), tentative_payment_date=date.today()),
        merch_a.id, UserRole.MERCHANDISER,
    )
    assert tranche.deposit_request_id == req_b.id
