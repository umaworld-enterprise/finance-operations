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
    period_editable,
    reminder_period,
    set_lock_enabled,
    window_open,
    window_opens_for,
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


async def test_merchandiser_edit_window_runs_to_the_end_of_the_month(db_session):
    """5 Nov 2026: the window for October opens 25 Sep and now stays open to
    31 Oct, so a figure can still be corrected while October is running."""
    merch, _other, _admin, v1, _v2 = await _setup(db_session)
    svc = ProjectionService(db_session)

    # Before the 25th of September, October is not yet open.
    with pytest.raises(BusinessRuleError, match="can be filed or edited"):
        await svc.submit(
            merch.id, UserRole.MERCHANDISER, 2026, 10, [_amounts(v1)],
            today=date(2026, 9, 10),
        )

    # From the 25th it is.
    assert await svc.submit(
        merch.id, UserRole.MERCHANDISER, 2026, 10, [_amounts(v1)],
        today=date(2026, 9, 26),
    ) == 1

    # And it is STILL editable late in October itself — the new edit option.
    assert await svc.submit(
        merch.id, UserRole.MERCHANDISER, 2026, 10, [_amounts(v1)],
        today=date(2026, 10, 31),
    ) == 1

    # Once October has closed, only the Super Admin may change it.
    with pytest.raises(BusinessRuleError, match="can be filed or edited"):
        await svc.submit(
            merch.id, UserRole.MERCHANDISER, 2026, 10, [_amounts(v1)],
            today=date(2026, 11, 1),
        )


async def test_period_math_for_the_window_and_the_reminder():
    assert window_opens_for(2026, 10) == date(2026, 9, 25)
    assert window_opens_for(2026, 1) == date(2025, 12, 25)      # year wrap
    assert period_editable(2026, 10, date(2026, 10, 31)) is True
    assert period_editable(2026, 10, date(2026, 11, 1)) is False
    # One continuous October reminder from 25 Sep through 31 Oct.
    assert reminder_period(date(2026, 9, 25)) == (2026, 10)
    assert reminder_period(date(2026, 10, 5)) == (2026, 10)
    assert reminder_period(date(2026, 10, 31)) == (2026, 11)


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


# ── Confirmation form: 3-month trend (5 Nov 2026) ────────────────────────────


async def _raise_for(db_session, vertical, merch, when, amount):
    """One live request against a vertical, dated `when`."""
    supplier = await make_supplier(db_session)
    customer = await make_customer(db_session)
    req = await make_request(
        db_session, supplier=supplier, customer=customer, created_by=merch,
        currency=CurrencyCode.USD, deposit_amount=Decimal(str(amount)),
        status=RequestStatus.PENDING_PAYMENT,
    )
    req.vertical_id = vertical.id
    req.created_at = when
    await db_session.flush()
    return req


async def test_trend_compares_projection_to_actuals_and_suggests_the_average(db_session):
    """The client's sheet: three months of proposed vs actually requested,
    the gap between them, and November anchored on the average of ACTUALS."""
    from datetime import datetime, timezone

    merch, _other, _admin, v1, _v2 = await _setup(db_session)
    svc = ProjectionService(db_session)

    # Proposed, per the sheet: Aug 275k, Sep 250k, Oct 300k.
    for (y, m), amount in (((2026, 8), 275000), ((2026, 9), 250000), ((2026, 10), 300000)):
        await svc.submit(
            merch.id, UserRole.SUPER_ADMIN, y, m, [_amounts(v1, usd=amount)],
        )
    # Actually requested: Aug 250k, Sep 300k, Oct 250k.
    for (y, m), amount in (((2026, 8), 250000), ((2026, 9), 300000), ((2026, 10), 250000)):
        await _raise_for(
            db_session, v1, merch, datetime(y, m, 15, tzinfo=timezone.utc), amount
        )

    trend = await svc.trend(v1.id, 2026, 11)
    by_label = {r["label"]: r for r in trend["rows"]}

    assert trend["rows"][0]["label"] == "Oct 2026"       # newest month first
    assert by_label["Oct 2026"]["proposed_usd"] == 300000
    assert by_label["Oct 2026"]["actual_usd"] == 250000
    assert by_label["Oct 2026"]["variance_usd"] == 50000        # over-estimated
    assert by_label["Sep 2026"]["variance_usd"] == -50000       # under-estimated
    assert by_label["Aug 2026"]["variance_usd"] == 25000

    # (250000 + 300000 + 250000) / 3 — the actuals, not the projections.
    assert trend["suggested_usd"] == 266666.67
    assert trend["confirmed"] is False


async def test_trend_reports_the_confirmed_figure_once_filed(db_session):
    merch, _other, _admin, v1, _v2 = await _setup(db_session)
    svc = ProjectionService(db_session)
    await svc.submit(merch.id, UserRole.SUPER_ADMIN, 2026, 11, [_amounts(v1, usd=270000)])

    trend = await svc.trend(v1.id, 2026, 11)
    assert trend["confirmed"] is True
    assert trend["confirmed_usd"] == 270000             # edited, not the average
    assert trend["editable_until"] == "2026-11-30"


# ── Reminder (advisory only) ─────────────────────────────────────────────────


async def test_reminder_names_the_period_and_deadline(db_session):
    _merch, _other, _admin, v1, v2 = await _setup(db_session)
    svc = ProjectionService(db_session)
    out = await svc.reminders(today=date(2026, 9, 25))

    assert out["period_label"] == "October 2026"
    assert out["deadline_label"] == "31 October 2026"
    names = {p["name"] for p in out["pending"]}
    assert {v1.name, v2.name} <= names


async def test_reminder_clears_for_a_vertical_once_it_is_filed(db_session):
    merch, _other, _admin, v1, v2 = await _setup(db_session)
    svc = ProjectionService(db_session)
    await svc.submit(
        merch.id, UserRole.MERCHANDISER, 2026, 10, [_amounts(v1)],
        today=date(2026, 9, 26),
    )
    out = await svc.reminders(today=date(2026, 9, 26))
    names = {p["name"] for p in out["pending"]}
    assert v1.name not in names        # filed — no nag
    assert v2.name in names            # still owing


async def test_reminder_never_blocks_a_request(db_session):
    """Bullet 4: 'no blockers in creating requests as it hampers work.' The
    reminder is advisory; with the lock off nothing is ever refused."""
    _merch, _other, _admin, v1, _v2 = await _setup(db_session)
    svc = ProjectionService(db_session)
    out = await svc.reminders(today=date(2026, 9, 26))

    assert v1.name in {p["name"] for p in out["pending"]}
    assert await lock_enabled(db_session) is False
    await svc.assert_vertical_open(v1.id, today=date(2026, 10, 2))   # no raise


# ── Audit trail ──────────────────────────────────────────────────────────────


async def test_every_projection_change_is_audit_logged(db_session):
    """'All changes should be audit logged' (5 Nov 2026)."""
    from sqlalchemy import select as _select

    from app.models.audit import AuditLog

    merch, _other, _admin, v1, _v2 = await _setup(db_session)
    svc = ProjectionService(db_session)

    await svc.submit(merch.id, UserRole.SUPER_ADMIN, 2026, 11, [_amounts(v1, usd=1000)])
    await svc.submit(merch.id, UserRole.SUPER_ADMIN, 2026, 11, [_amounts(v1, usd=2500)])

    logs = (
        await db_session.execute(
            _select(AuditLog).where(AuditLog.entity_name == "projection")
        )
    ).scalars().all()

    actions = [log.action.value for log in logs]
    assert "CREATE" in actions
    updates = [log for log in logs if log.action.value == "UPDATE"]
    usd = next(log for log in updates if "amount_usd" in (log.field_name or ""))
    assert usd.old_value.startswith("1000")
    assert usd.new_value.startswith("2500")
    assert usd.changed_by == merch.id
