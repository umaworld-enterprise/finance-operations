"""Away pop-up + seen/unseen red dot (23 Sep 2026, executive requests).

The pop-up reports what reached the Accounts queue during a real absence;
the red dot marks requests changed since this user last opened them.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.models.enums import RequestStatus, UserRole
from app.services.presence_service import AWAY_THRESHOLD_MINUTES, PresenceService
from tests.factories import make_customer, make_request, make_supplier, make_user

pytestmark = pytest.mark.asyncio


def _ago(minutes: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(minutes=minutes)


async def _accounts_user(db_session, last_seen_minutes_ago: int | None):
    user = await make_user(db_session, UserRole.ACCOUNTS_TEAM)
    user.last_seen_at = None if last_seen_minutes_ago is None else _ago(last_seen_minutes_ago)
    # Baseline well in the past so freshly made requests count as unseen.
    user.unseen_since = _ago(60 * 24)
    await db_session.flush()
    return user


async def _pending_request(db_session, created_minutes_ago: int = 5):
    supplier = await make_supplier(db_session)
    customer = await make_customer(db_session)
    merch = await make_user(db_session, UserRole.MERCHANDISER)
    req = await make_request(
        db_session, supplier=supplier, customer=customer, created_by=merch,
        status=RequestStatus.PENDING_PAYMENT,
    )
    req.created_at = _ago(created_minutes_ago)
    await db_session.flush()
    return req


# ── "While you were away" ────────────────────────────────────────────────────


async def test_counts_requests_that_arrived_during_a_real_absence(db_session):
    user = await _accounts_user(db_session, last_seen_minutes_ago=120)
    await _pending_request(db_session, created_minutes_ago=30)
    await _pending_request(db_session, created_minutes_ago=10)

    summary = await PresenceService(db_session).away_summary(user.id)
    assert summary["new_requests"] == 2
    assert summary["away_minutes"] >= AWAY_THRESHOLD_MINUTES
    assert summary["show"] is True


async def test_requests_predating_the_absence_are_not_counted(db_session):
    user = await _accounts_user(db_session, last_seen_minutes_ago=60)
    await _pending_request(db_session, created_minutes_ago=180)  # before they left

    summary = await PresenceService(db_session).away_summary(user.id)
    assert summary["new_requests"] == 0
    assert summary["show"] is False


async def test_short_gap_does_not_pop_the_dialog(db_session):
    """Switching to Excel for a few minutes is not 'being away'."""
    user = await _accounts_user(db_session, last_seen_minutes_ago=2)
    await _pending_request(db_session, created_minutes_ago=1)

    summary = await PresenceService(db_session).away_summary(user.id)
    assert summary["new_requests"] == 1
    assert summary["show"] is False


async def test_first_ever_visit_reports_nothing(db_session):
    user = await _accounts_user(db_session, last_seen_minutes_ago=None)
    await _pending_request(db_session, created_minutes_ago=10)

    summary = await PresenceService(db_session).away_summary(user.id)
    assert summary == {"since": None, "away_minutes": 0, "new_requests": 0, "show": False}


async def test_heartbeat_records_presence(db_session):
    user = await _accounts_user(db_session, last_seen_minutes_ago=120)
    await PresenceService(db_session).touch(user.id)
    await db_session.refresh(user)
    assert user.last_seen_at is not None

    summary = await PresenceService(db_session).away_summary(user.id)
    assert summary["away_minutes"] < AWAY_THRESHOLD_MINUTES


# ── Seen / unseen red dot ────────────────────────────────────────────────────


async def test_new_request_is_unseen_until_opened(db_session):
    user = await _accounts_user(db_session, last_seen_minutes_ago=10)
    req = await _pending_request(db_session)
    svc = PresenceService(db_session)

    assert str(req.id) in await svc.unseen_request_ids(user.id)

    await svc.mark_viewed(user.id, req.id)
    assert str(req.id) not in await svc.unseen_request_ids(user.id)


async def test_modification_after_viewing_raises_the_dot_again(db_session):
    user = await _accounts_user(db_session, last_seen_minutes_ago=10)
    req = await _pending_request(db_session)
    svc = PresenceService(db_session)
    await svc.mark_viewed(user.id, req.id)
    assert str(req.id) not in await svc.unseen_request_ids(user.id)

    # Someone edits the file afterwards.
    req.updated_at = datetime.now(timezone.utc) + timedelta(seconds=5)
    await db_session.flush()

    assert str(req.id) in await svc.unseen_request_ids(user.id)


async def test_tranche_edit_alone_raises_the_dot(db_session):
    """A tranche change does not always touch the parent row — the dot must
    still appear, which is why activity spans both tables."""
    from tests.factories import make_tranche

    user = await _accounts_user(db_session, last_seen_minutes_ago=10)
    req = await _pending_request(db_session)
    svc = PresenceService(db_session)
    await svc.mark_viewed(user.id, req.id)
    assert str(req.id) not in await svc.unseen_request_ids(user.id)

    tranche = await make_tranche(db_session, req)
    tranche.updated_at = datetime.now(timezone.utc) + timedelta(seconds=5)
    await db_session.flush()

    assert str(req.id) in await svc.unseen_request_ids(user.id)


async def test_historical_files_stay_quiet_on_rollout(db_session):
    """Requests whose last activity predates the user's baseline must not all
    light up the first time the feature runs."""
    user = await _accounts_user(db_session, last_seen_minutes_ago=10)
    user.unseen_since = datetime.now(timezone.utc) + timedelta(seconds=5)
    await db_session.flush()
    await _pending_request(db_session)

    assert await PresenceService(db_session).unseen_request_ids(user.id) == []


async def test_seen_state_is_per_user(db_session):
    user_a = await _accounts_user(db_session, last_seen_minutes_ago=10)
    user_b = await _accounts_user(db_session, last_seen_minutes_ago=10)
    req = await _pending_request(db_session)
    svc = PresenceService(db_session)

    await svc.mark_viewed(user_a.id, req.id)
    assert str(req.id) not in await svc.unseen_request_ids(user_a.id)
    assert str(req.id) in await svc.unseen_request_ids(user_b.id)
