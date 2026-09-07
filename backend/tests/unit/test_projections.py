"""Projections module (4 Sep 2026): vertical assignments (single vertical →
single user), the 25th→EOM submission window for NEXT month, the post-deadline
request-creation block with Super-Admin unblock, and the projection-vs-actual
dashboard."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.core.exceptions import AuthorizationError, BusinessRuleError
from app.models.enums import CurrencyCode, RequestStatus, UserRole
from app.services.projection_service import (
    ProjectionService,
    next_period,
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
    admin = await make_user(db_session, UserRole.SUPER_ADMIN)
    v1 = await make_vertical(db_session)
    v2 = await make_vertical(db_session)
    svc = ProjectionService(db_session)
    await svc.assign_verticals(merch.id, [v1.id, v2.id], UserRole.SUPER_ADMIN)
    return merch, admin, v1, v2, svc


async def test_assignment_is_exclusive_per_vertical(db_session):
    merch, admin, v1, v2, svc = await _setup(db_session)
    other = await make_user(db_session)
    # v1 belongs to merch — assigning it to another user is refused.
    with pytest.raises(BusinessRuleError, match="only one user"):
        await svc.assign_verticals(other.id, [v1.id], UserRole.SUPER_ADMIN)
    # Reducing merch's set unassigns the removed vertical, freeing it up.
    await svc.assign_verticals(merch.id, [v2.id], UserRole.SUPER_ADMIN)
    freed = await svc.assign_verticals(other.id, [v1.id], UserRole.SUPER_ADMIN)
    assert [v.id for v in freed] == [v1.id]
    # Only the Super Admin may assign.
    with pytest.raises(AuthorizationError):
        await svc.assign_verticals(other.id, [v1.id], UserRole.MERCHANDISER)


async def test_merchandiser_submits_next_month_inside_window_only(db_session):
    merch, admin, v1, v2, svc = await _setup(db_session)
    in_window = date(2026, 9, 26)
    t_year, t_month = next_period(in_window)  # October 2026

    # Outside the window → refused.
    with pytest.raises(BusinessRuleError, match="window opens"):
        await svc.submit(
            merch.id, UserRole.MERCHANDISER, t_year, t_month,
            [{"vertical_id": v1.id, "amount_usd": "1000"}],
            today=date(2026, 9, 10),
        )
    # Wrong period → refused.
    with pytest.raises(BusinessRuleError, match="NEXT month"):
        await svc.submit(
            merch.id, UserRole.MERCHANDISER, 2026, 9,
            [{"vertical_id": v1.id, "amount_usd": "1000"}],
            today=in_window,
        )
    # Someone else's vertical → refused.
    other = await make_user(db_session)
    v3 = await make_vertical(db_session)
    await svc.assign_verticals(other.id, [v3.id], UserRole.SUPER_ADMIN)
    with pytest.raises(AuthorizationError, match="not assigned to you"):
        await svc.submit(
            merch.id, UserRole.MERCHANDISER, t_year, t_month,
            [{"vertical_id": v3.id, "amount_usd": "1"}],
            today=in_window,
        )

    saved = await svc.submit(
        merch.id, UserRole.MERCHANDISER, t_year, t_month,
        [
            {"vertical_id": v1.id, "amount_usd": "1000.00", "amount_eur": "200.00"},
            {"vertical_id": v2.id, "amount_cny": "5000.00"},
        ],
        today=in_window,
    )
    assert saved == 2
    status = await svc.get_status(merch.id, today=in_window)
    assert status["window_open"] is True
    assert status["missing_target"] == []
    # Re-submitting inside the window updates (upsert, no duplicate error).
    await svc.submit(
        merch.id, UserRole.MERCHANDISER, t_year, t_month,
        [{"vertical_id": v1.id, "amount_usd": "1500.00"}],
        today=in_window,
    )


async def test_block_after_deadline_and_super_admin_unblock(db_session):
    merch, admin, v1, v2, svc = await _setup(db_session)
    today = date(2026, 10, 3)  # October started, nothing filed for October

    blocked, message = await svc.is_blocked(merch.id, today)
    assert blocked is True
    assert "October 2026" in message and "Super Admin" in message

    # The merchandiser cannot self-fill October any more (window closed;
    # October is no longer "next month").
    with pytest.raises(BusinessRuleError):
        await svc.submit(
            merch.id, UserRole.MERCHANDISER, 2026, 10,
            [{"vertical_id": v1.id, "amount_usd": "1"}],
            today=today,
        )

    # Super Admin files on their behalf — for ALL missing verticals.
    await svc.submit(
        admin.id, UserRole.SUPER_ADMIN, 2026, 10,
        [
            {"vertical_id": v1.id, "amount_usd": "800.00"},
            {"vertical_id": v2.id, "amount_usd": "900.00"},
        ],
        today=today,
    )
    blocked, _ = await svc.is_blocked(merch.id, today)
    assert blocked is False

    # A merchandiser with NO assigned verticals is never blocked.
    free_user = await make_user(db_session)
    blocked, _ = await svc.is_blocked(free_user.id, today)
    assert blocked is False


async def test_dashboard_compares_projection_to_actuals(db_session):
    merch, admin, v1, v2, svc = await _setup(db_session)
    supplier = await make_supplier(db_session)
    customer = await make_customer(db_session)

    await svc.submit(
        admin.id, UserRole.SUPER_ADMIN, 2026, 10,
        [{"vertical_id": v1.id, "amount_usd": "1000.00", "amount_cny": "300.00"}],
    )
    # Actuals in October: one USD request in v1, one cancelled (excluded).
    from datetime import datetime, timezone

    await make_request(
        db_session, supplier=supplier, customer=customer, created_by=merch,
        vertical=v1, deposit_amount=Decimal("400.00"),
        created_at=datetime(2026, 10, 10, tzinfo=timezone.utc),
    )
    await make_request(
        db_session, supplier=supplier, customer=customer, created_by=merch,
        vertical=v1, deposit_amount=Decimal("999.00"),
        status=RequestStatus.CANCELLED_BY_MERCHANDISER,
        created_at=datetime(2026, 10, 12, tzinfo=timezone.utc),
    )
    # A September request never counts toward October.
    await make_request(
        db_session, supplier=supplier, customer=customer, created_by=merch,
        vertical=v1, deposit_amount=Decimal("777.00"),
        created_at=datetime(2026, 9, 20, tzinfo=timezone.utc),
    )

    rows = await svc.dashboard(2026, 10)
    row = next(r for r in rows if r["vertical_id"] == str(v1.id))
    assert row["filled"] is True
    assert row["proj_usd"] == 1000.0
    assert row["proj_cny"] == 300.0
    assert row["actual_usd"] == 400.0
    assert row["merchandiser"] == merch.full_name
    # v2 is assigned but unfilled — visible as a gap.
    gap = next(r for r in rows if r["vertical_id"] == str(v2.id))
    assert gap["filled"] is False and gap["actual_usd"] == 0.0
