"""Projections module (4 Sep 2026; reworked 7 Oct 2026).

The assignment model is gone: every active vertical needs a projection each
month, ANY merchandiser may fill ANY vertical and overwrite a colleague's
figures, and a vertical still missing the CURRENT month's projection is
locked for request creation — for every role, not just merchandisers.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.core.exceptions import BusinessRuleError
from app.models.enums import CurrencyCode, RequestStatus, UserRole
from app.services.projection_service import (
    ProjectionService,
    lock_enabled,
    next_period,
    set_lock_enabled,
    window_open,
)
from tests.factories import (
    make_customer,
    make_request,
    make_supplier,
    make_user,
    make_vertical,
)

pytestmark = pytest.mark.asyncio


async def test_window_and_period_math():
    assert next_period(date(2026, 9, 26)) == (2026, 10)
    assert next_period(date(2026, 12, 25)) == (2027, 1)
    assert window_open(date(2026, 9, 25)) is True
    assert window_open(date(2026, 9, 30)) is True
    assert window_open(date(2026, 9, 24)) is False


async def _setup(db_session):
    merch = await make_user(db_session)
    other = await make_user(db_session, UserRole.MERCHANDISER)
    admin = await make_user(db_session, UserRole.SUPER_ADMIN)
    v1 = await make_vertical(db_session)
    v2 = await make_vertical(db_session)
    return merch, other, admin, v1, v2


def _amounts(vertical, usd=1000, eur=0, cny=0):
    return {
        "vertical_id": vertical.id,
        "amount_usd": usd,
        "amount_eur": eur,
        "amount_cny": cny,
    }


# ── Any merchandiser, any vertical ───────────────────────────────────────────


async def test_any_merchandiser_may_fill_any_vertical(db_session):
    merch, _other, _admin, v1, _v2 = await _setup(db_session)
    svc = ProjectionService(db_session)
    today = date(2026, 9, 26)  # inside the window
    year, month = next_period(today)

    count = await svc.submit(
        merch.id, UserRole.MERCHANDISER, year, month, [_amounts(v1)], today=today
    )
    assert count == 1


async def test_a_colleague_can_overwrite_and_the_row_names_them(db_session):
    merch, other, _admin, v1, _v2 = await _setup(db_session)
    svc = ProjectionService(db_session)
    today = date(2026, 9, 26)
    year, month = next_period(today)

    await svc.submit(merch.id, UserRole.MERCHANDISER, year, month, [_amounts(v1, usd=500)], today=today)
    await svc.submit(other.id, UserRole.MERCHANDISER, year, month, [_amounts(v1, usd=900)], today=today)

    status = await svc.get_status(merch.id, today=today)
    row = next(r for r in status["verticals"] if r["vertical_id"] == str(v1.id))
    assert row["amount_usd"] == 900.0
    assert row["last_updated_by"] == other.full_name


async def test_status_lists_every_active_vertical(db_session):
    merch, _other, _admin, v1, v2 = await _setup(db_session)
    svc = ProjectionService(db_session)
    today = date(2026, 9, 26)
    year, month = next_period(today)
    await svc.submit(merch.id, UserRole.MERCHANDISER, year, month, [_amounts(v1)], today=today)

    status = await svc.get_status(merch.id, today=today)
    names = {r["name"] for r in status["verticals"]}
    assert {v1.name, v2.name} <= names
    assert v2.name in status["missing_target"]
    assert v1.name not in status["missing_target"]


async def test_merchandiser_is_held_to_next_month_inside_the_window(db_session):
    merch, _other, _admin, v1, _v2 = await _setup(db_session)
    svc = ProjectionService(db_session)
    outside = date(2026, 9, 10)
    year, month = next_period(outside)
    with pytest.raises(BusinessRuleError, match="window opens"):
        await svc.submit(
            merch.id, UserRole.MERCHANDISER, year, month, [_amounts(v1)], today=outside
        )

    inside = date(2026, 9, 26)
    with pytest.raises(BusinessRuleError, match="NEXT month"):
        await svc.submit(
            merch.id, UserRole.MERCHANDISER, 2026, 9, [_amounts(v1)], today=inside
        )


# ── Per-vertical lock ────────────────────────────────────────────────────────


async def test_lock_is_off_by_default(db_session):
    """9 Oct 2026: the lock shipped ON and stopped management raising
    requests. With no config row nobody is blocked."""
    _merch, _other, _admin, v1, _v2 = await _setup(db_session)
    svc = ProjectionService(db_session)
    today = date(2026, 10, 3)  # October started, nothing filed

    assert await lock_enabled(db_session) is False
    await svc.assert_vertical_open(v1.id, today=today)  # no raise
    assert await svc.locked_vertical_ids(today) == set()


async def test_unprojected_vertical_is_locked_once_armed(db_session):
    _merch, _other, _admin, v1, _v2 = await _setup(db_session)
    svc = ProjectionService(db_session)
    today = date(2026, 10, 3)
    await set_lock_enabled(db_session, True)

    with pytest.raises(BusinessRuleError, match=v1.name):
        await svc.assert_vertical_open(v1.id, today=today)


async def test_lock_can_be_disarmed_again(db_session):
    _merch, _other, _admin, v1, _v2 = await _setup(db_session)
    svc = ProjectionService(db_session)
    today = date(2026, 10, 3)
    await set_lock_enabled(db_session, True)
    with pytest.raises(BusinessRuleError):
        await svc.assert_vertical_open(v1.id, today=today)

    await set_lock_enabled(db_session, False)
    await svc.assert_vertical_open(v1.id, today=today)  # no raise


async def test_filing_the_projection_unlocks_the_vertical(db_session):
    merch, _other, admin, v1, _v2 = await _setup(db_session)
    svc = ProjectionService(db_session)
    today = date(2026, 10, 3)
    await set_lock_enabled(db_session, True)

    # Super Admin can file for the current month — the post-deadline fix.
    await svc.submit(admin.id, UserRole.SUPER_ADMIN, 2026, 10, [_amounts(v1)], today=today)
    await svc.assert_vertical_open(v1.id, today=today)  # no raise


async def test_lock_is_per_vertical_not_per_person(db_session):
    """A projected vertical stays open even while a sibling is locked."""
    merch, _other, admin, v1, v2 = await _setup(db_session)
    svc = ProjectionService(db_session)
    today = date(2026, 10, 3)
    await set_lock_enabled(db_session, True)
    await svc.submit(admin.id, UserRole.SUPER_ADMIN, 2026, 10, [_amounts(v1)], today=today)

    await svc.assert_vertical_open(v1.id, today=today)  # filled → open
    with pytest.raises(BusinessRuleError):
        await svc.assert_vertical_open(v2.id, today=today)  # missing → locked


async def test_request_without_a_vertical_is_never_blocked(db_session):
    await _setup(db_session)
    await ProjectionService(db_session).assert_vertical_open(None, today=date(2026, 10, 3))


# ── Dashboard ────────────────────────────────────────────────────────────────


async def test_dashboard_compares_projection_to_actuals(db_session):
    merch, _other, admin, v1, _v2 = await _setup(db_session)
    svc = ProjectionService(db_session)
    today = date(2026, 10, 3)
    await svc.submit(
        admin.id, UserRole.SUPER_ADMIN, 2026, 10, [_amounts(v1, usd=5000)], today=today
    )

    supplier = await make_supplier(db_session)
    customer = await make_customer(db_session)
    req = await make_request(
        db_session, supplier=supplier, customer=customer, created_by=merch,
        status=RequestStatus.PENDING_PAYMENT, deposit_amount=Decimal("1200.00"),
    )
    req.vertical_id = v1.id
    req.currency = CurrencyCode.USD
    req.created_at = req.created_at.replace(year=2026, month=10, day=2)
    await db_session.flush()

    rows = await svc.dashboard(2026, 10)
    row = next(r for r in rows if r["vertical_id"] == str(v1.id))
    assert row["proj_usd"] == 5000.0
    assert row["actual_usd"] == 1200.0
    # The merchandiser shown is whoever last filed the projection.
    assert row["merchandiser"] == admin.full_name
