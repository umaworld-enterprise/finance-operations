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

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deposit_request import DepositRequest
from app.models.enums import RequestStatus, UserRole
from app.models.file_remark import FileRemark, FileRemarkStatus
from app.models.masters import User
from app.models.request_view import RequestView
from app.models.section_view import SectionView
from app.models.tranche import PaymentTranche

# Ignore blips: switching to Excel for a moment is not "being away".
AWAY_THRESHOLD_MINUTES = 30

# Safety valve — the dot only ever needs to mark what a person can scroll to.
MAX_UNSEEN_IDS = 500

# Sidebar sections that carry a "new since you last looked" badge
# (29 Sep 2026). Keys are shared verbatim with the frontend.
SECTION_ACCOUNTS = "accounts"
SECTION_HOM = "hom"
SECTION_FILE_REMARKS = "file_remarks"
SECTION_MERCHANDISER = "merchandiser"

SIDEBAR_SECTIONS = (
    SECTION_ACCOUNTS,
    SECTION_HOM,
    SECTION_FILE_REMARKS,
    SECTION_MERCHANDISER,
)

# Which roles see which section — the badge must never count work the user
# cannot open (their sidebar does not carry that item at all).
_SECTION_ROLES: dict[str, set[UserRole]] = {
    SECTION_ACCOUNTS: {UserRole.ACCOUNTS_TEAM, UserRole.SUPER_ADMIN},
    SECTION_HOM: {UserRole.HEAD_OF_MERCHANDISER, UserRole.SUPER_ADMIN},
    SECTION_FILE_REMARKS: {
        UserRole.MERCHANDISER,
        UserRole.ACCOUNTS_TEAM,
        UserRole.SUPER_ADMIN,
        UserRole.FINANCE_ADMIN,
    },
    SECTION_MERCHANDISER: {UserRole.MERCHANDISER},
}


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

    # ── Sidebar "new since you last looked" badges (29 Sep 2026) ────────────

    async def _section_cutoffs(self, user: User) -> dict[str, datetime]:
        """Per-section "last opened" timestamps, falling back to the user's
        baseline so a section never opened does not count its whole history."""
        baseline = _aware(user.unseen_since) or datetime.now(timezone.utc)
        rows = (
            await self._session.execute(
                select(SectionView.section, SectionView.viewed_at).where(
                    SectionView.user_id == user.id
                )
            )
        ).all()
        seen = {section: _aware(at) or baseline for section, at in rows}
        return {s: seen.get(s, baseline) for s in SIDEBAR_SECTIONS}

    async def sidebar_counts(self, user_id: UUID, role: UserRole) -> dict[str, int]:
        """How many items arrived or changed in each sidebar section since the
        user last opened it. Sections the role cannot see are omitted, and a
        section with nothing new reports 0 (the frontend hides the badge)."""
        user = await self._session.get(User, user_id)
        if user is None:
            return {}
        cutoffs = await self._section_cutoffs(user)
        counts: dict[str, int] = {}

        async def _request_count(section: str, status: RequestStatus) -> int:
            """Requests sitting in `status` that arrived or changed since the
            cutoff — "new work in this queue"."""
            cutoff = cutoffs[section]
            return int(
                (
                    await self._session.execute(
                        select(func.count(DepositRequest.id)).where(
                            DepositRequest.is_deleted == False,  # noqa: E712
                            DepositRequest.current_status == status,
                            or_(
                                DepositRequest.created_at > cutoff,
                                DepositRequest.updated_at > cutoff,
                            ),
                        )
                    )
                ).scalar_one()
            )

        if role in _SECTION_ROLES[SECTION_ACCOUNTS]:
            counts[SECTION_ACCOUNTS] = await _request_count(
                SECTION_ACCOUNTS, RequestStatus.PENDING_PAYMENT
            )

        if role in _SECTION_ROLES[SECTION_HOM]:
            counts[SECTION_HOM] = await _request_count(
                SECTION_HOM, RequestStatus.PENDING_HOM_APPROVAL
            )

        if role in _SECTION_ROLES[SECTION_FILE_REMARKS]:
            # Raised or decided since the cutoff — both directions matter: the
            # Accounts team needs new ones, the raiser needs the verdict.
            cutoff = cutoffs[SECTION_FILE_REMARKS]
            counts[SECTION_FILE_REMARKS] = int(
                (
                    await self._session.execute(
                        select(func.count(FileRemark.id)).where(
                            or_(
                                FileRemark.created_at > cutoff,
                                FileRemark.resolved_at > cutoff,
                            )
                        )
                    )
                ).scalar_one()
            )

        if role in _SECTION_ROLES[SECTION_MERCHANDISER]:
            # Every merchandiser sees every request (11 Sep 2026), so this
            # mirrors the list they actually open.
            cutoff = cutoffs[SECTION_MERCHANDISER]
            counts[SECTION_MERCHANDISER] = int(
                (
                    await self._session.execute(
                        select(func.count(DepositRequest.id)).where(
                            DepositRequest.is_deleted == False,  # noqa: E712
                            or_(
                                DepositRequest.created_at > cutoff,
                                DepositRequest.updated_at > cutoff,
                            ),
                        )
                    )
                ).scalar_one()
            )

        return counts

    async def mark_section_viewed(self, user_id: UUID, section: str) -> None:
        """Clears a sidebar badge — the user has opened that section."""
        if section not in SIDEBAR_SECTIONS:
            return
        existing = (
            await self._session.execute(
                select(SectionView).where(
                    SectionView.user_id == user_id, SectionView.section == section
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing.viewed_at = datetime.now(timezone.utc)
        else:
            self._session.add(
                SectionView(
                    user_id=user_id, section=section, viewed_at=datetime.now(timezone.utc)
                )
            )
        await self._session.flush()

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


__all__ = ["PresenceService", "AWAY_THRESHOLD_MINUTES", "SIDEBAR_SECTIONS"]
