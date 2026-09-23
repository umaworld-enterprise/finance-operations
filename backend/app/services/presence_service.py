"""Presence + seen/unseen tracking for the Accounts team (23 Sep 2026).

Two executive requests share this service:

1. **"While you were away" pop-up.** The app writes a heartbeat while its tab
   is visible; the gap between the last heartbeat and the user's return IS the
   away window. ``away_summary`` reports how many requests landed in the
   Accounts queue during it.
2. **Seen/unseen red dot.** ``unseen_request_ids`` returns the requests whose
   latest activity is newer than the last time THIS user opened them, so a
   modified file is visibly flagged until someone looks at it.

"Latest activity" is the newest of the request row itself and its tranches —
a tranche edit alone does not always touch the parent row. The comparison is
done in Python because ``GREATEST`` (Postgres) and two-argument ``max``
(SQLite) are not portable across both engines.
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deposit_request import DepositRequest
from app.models.enums import RequestStatus
from app.models.masters import User
from app.models.request_view import RequestView
from app.models.tranche import PaymentTranche

# Ignore blips: switching to Excel for a moment is not "being away".
AWAY_THRESHOLD_MINUTES = 30

# Safety valve — the dot only ever needs to mark what a person can scroll to.
MAX_UNSEEN_IDS = 500


def _aware(value: datetime | None) -> datetime | None:
    """SQLite hands back naive datetimes; Postgres aware ones. Normalise so
    the two can be compared without a TypeError."""
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


class PresenceService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def touch(self, user_id: UUID) -> None:
        """Heartbeat — records that the user is currently in the app."""
        await self._session.execute(
            update(User).where(User.id == user_id).values(last_seen_at=func.now())
        )

    async def away_summary(self, user_id: UUID) -> dict:
        """How long the user was away and what arrived meanwhile.

        Counts requests CREATED during the gap that are still waiting for
        Accounts — the queue they come back to. `show` is the frontend's cue
        to pop the dialog: a real absence with something new in it.
        """
        user = await self._session.get(User, user_id)
        since = _aware(user.last_seen_at) if user else None
        now = datetime.now(timezone.utc)

        if since is None:
            # First visit since the feature shipped — nothing to compare to.
            return {"since": None, "away_minutes": 0, "new_requests": 0, "show": False}

        away_minutes = int((now - since).total_seconds() // 60)
        new_requests = (
            await self._session.execute(
                select(func.count(DepositRequest.id)).where(
                    DepositRequest.is_deleted == False,  # noqa: E712
                    DepositRequest.created_at > since,
                    DepositRequest.current_status == RequestStatus.PENDING_PAYMENT,
                )
            )
        ).scalar_one()

        return {
            "since": since.isoformat(),
            "away_minutes": away_minutes,
            "new_requests": int(new_requests),
            "show": away_minutes >= AWAY_THRESHOLD_MINUTES and new_requests > 0,
        }

    async def unseen_request_ids(self, user_id: UUID) -> list[str]:
        """Requests changed since this user last opened them.

        Never-opened requests count only when their activity is newer than the
        user's ``unseen_since`` baseline — without it, every historical file
        would light up the first time the feature ran.
        """
        user = await self._session.get(User, user_id)
        if user is None:
            return []
        baseline = _aware(user.unseen_since) or datetime.now(timezone.utc)

        viewed = {
            rid: _aware(seen)
            for rid, seen in (
                await self._session.execute(
                    select(RequestView.deposit_request_id, RequestView.viewed_at).where(
                        RequestView.user_id == user_id
                    )
                )
            ).all()
        }

        tranche_activity = {
            rid: _aware(seen)
            for rid, seen in (
                await self._session.execute(
                    select(
                        PaymentTranche.deposit_request_id,
                        func.max(PaymentTranche.updated_at),
                    ).group_by(PaymentTranche.deposit_request_id)
                )
            ).all()
        }

        rows = (
            await self._session.execute(
                select(DepositRequest.id, DepositRequest.updated_at).where(
                    DepositRequest.is_deleted == False,  # noqa: E712
                )
            )
        ).all()

        unseen: list[tuple[datetime, str]] = []
        for rid, updated_at in rows:
            activity = _aware(updated_at)
            tranche_at = tranche_activity.get(rid)
            if tranche_at and (activity is None or tranche_at > activity):
                activity = tranche_at
            if activity is None:
                continue
            cutoff = viewed.get(rid) or baseline
            if activity > cutoff:
                unseen.append((activity, str(rid)))

        # Newest activity first, so the cap keeps what matters most.
        unseen.sort(key=lambda pair: pair[0], reverse=True)
        return [rid for _activity, rid in unseen[:MAX_UNSEEN_IDS]]

    async def mark_viewed(self, user_id: UUID, request_id: UUID) -> None:
        """Clear the dot — the user has opened this request."""
        existing = (
            await self._session.execute(
                select(RequestView).where(
                    RequestView.user_id == user_id,
                    RequestView.deposit_request_id == request_id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing.viewed_at = datetime.now(timezone.utc)
        else:
            self._session.add(
                RequestView(
                    user_id=user_id,
                    deposit_request_id=request_id,
                    viewed_at=datetime.now(timezone.utc),
                )
            )
        await self._session.flush()


__all__ = ["PresenceService", "AWAY_THRESHOLD_MINUTES"]
