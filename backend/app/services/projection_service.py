"""Projections module (4 Sep 2026).

Cycle (client decisions):
- From the 25th to the last day of each month, merchandisers with assigned
  verticals fill NEXT month's projection per vertical (USD / EUR / CNY).
- Daily reminders run through the window; merchandisers can still raise
  requests while it is open.
- Once the target month starts, a merchandiser whose assigned verticals are
  missing that month's projection is BLOCKED from creating new requests and
  receives the formal "contact Super Admin" notification. Only the Super
  Admin's on-behalf entry unblocks them (no late self-fill).
- Merchandisers with no assigned verticals are never nagged or blocked.
- The dashboard compares projections against ACTUALS: deposit amounts of
  live requests whose request date falls in the month, per vertical and
  currency.
"""

import calendar
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AuthorizationError, BusinessRuleError, ValidationError
from app.models.deposit_request import DepositRequest
from app.models.enums import CurrencyCode, RequestStatus, UserRole
from app.models.masters import User, Vertical
from app.models.projection import Projection

_EXCLUDED_STATUSES = (
    RequestStatus.CANCELLED_BY_MERCHANDISER,
    RequestStatus.CANCELLED_BY_ACCOUNTS,
    RequestStatus.REJECTED_BY_HOM,
    RequestStatus.REJECTED_BY_ACCOUNTS,
)

WINDOW_OPENS_ON = 25  # the 25th of each month, through month end


def next_period(today: date) -> tuple[int, int]:
    """The (year, month) the 25th→EOM window collects: NEXT month."""
    return (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)


def window_open(today: date) -> bool:
    return today.day >= WINDOW_OPENS_ON


def month_bounds(year: int, month: int) -> tuple[date, date]:
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


class ProjectionService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def assigned_verticals(self, user_id: UUID) -> list[Vertical]:
        rows = await self._session.execute(
            select(Vertical)
            .where(Vertical.assigned_user_id == user_id, Vertical.is_active == True)  # noqa: E712
            .order_by(Vertical.name)
        )
        return list(rows.scalars().all())

    async def _missing_verticals(self, user_id: UUID, year: int, month: int) -> list[Vertical]:
        """Assigned active verticals with NO projection row for the period."""
        filled = (
            select(Projection.vertical_id)
            .where(Projection.year == year, Projection.month == month)
            .scalar_subquery()
        )
        rows = await self._session.execute(
            select(Vertical)
            .where(
                Vertical.assigned_user_id == user_id,
                Vertical.is_active == True,  # noqa: E712
                Vertical.id.notin_(filled),
            )
            .order_by(Vertical.name)
        )
        return list(rows.scalars().all())

    async def is_blocked(self, user_id: UUID, today: date | None = None) -> tuple[bool, str | None]:
        """Whether request creation is blocked for this merchandiser: the
        CURRENT month has started and at least one assigned vertical is
        missing its projection. Returns (blocked, formal message)."""
        today = today or date.today()
        missing = await self._missing_verticals(user_id, today.year, today.month)
        if not missing:
            return False, None
        month_label = today.strftime("%B %Y")
        return True, (
            f"Request creation is stopped because your {month_label} projections "
            f"were not added before the deadline "
            f"(missing: {', '.join(v.name for v in missing)}). "
            "Please contact the Super Admin to add them on your behalf and unblock you."
        )

    async def get_status(self, user_id: UUID, today: date | None = None) -> dict:
        """Everything the merchandiser UI needs: the collection window, the
        target period's fill state, and the current-month block state."""
        today = today or date.today()
        t_year, t_month = next_period(today)
        assigned = await self.assigned_verticals(user_id)
        filled_rows = (
            await self._session.execute(
                select(Projection).where(
                    Projection.user_id == user_id,
                    Projection.year == t_year,
                    Projection.month == t_month,
                )
            )
        ).scalars().all()
        filled_by_vertical = {p.vertical_id: p for p in filled_rows}
        blocked, block_message = await self.is_blocked(user_id, today)
        _, window_end = month_bounds(today.year, today.month)
        return {
            "has_verticals": len(assigned) > 0,
            "window_open": window_open(today) and len(assigned) > 0,
            "window_ends": window_end.isoformat(),
            "target_year": t_year,
            "target_month": t_month,
            "verticals": [
                {
                    "vertical_id": str(v.id),
                    "name": v.name,
                    "filled": v.id in filled_by_vertical,
                    "amount_usd": float(filled_by_vertical[v.id].amount_usd) if v.id in filled_by_vertical else None,
                    "amount_eur": float(filled_by_vertical[v.id].amount_eur) if v.id in filled_by_vertical else None,
                    "amount_cny": float(filled_by_vertical[v.id].amount_cny) if v.id in filled_by_vertical else None,
                }
                for v in assigned
            ],
            "missing_target": [v.name for v in assigned if v.id not in filled_by_vertical],
            "blocked": blocked,
            "block_message": block_message,
        }

    async def submit(
        self,
        user_id: UUID,
        role: UserRole,
        year: int,
        month: int,
        items: list[dict],
        today: date | None = None,
    ) -> int:
        """Upsert projection rows for (year, month).

        Merchandiser: only their OWN assigned verticals, only for the NEXT
        month, only while the 25th→EOM window is open. Super Admin: any
        vertical (must be assigned to someone — the row belongs to the
        assignee), any period — this is the unblock path.
        """
        today = today or date.today()
        if role == UserRole.MERCHANDISER:
            t_year, t_month = next_period(today)
            if (year, month) != (t_year, t_month):
                raise BusinessRuleError(
                    "Merchandisers can only file the NEXT month's projections."
                )
            if not window_open(today):
                raise BusinessRuleError(
                    f"The projection window opens on the {WINDOW_OPENS_ON}th of the "
                    "month. After the deadline, only the Super Admin can add them."
                )
        elif role != UserRole.SUPER_ADMIN:
            raise AuthorizationError(
                "Only merchandisers (their own) or the Super Admin can file projections."
            )
        if not items:
            raise ValidationError("No projection rows supplied.")

        count = 0
        for item in items:
            vertical = await self._session.get(Vertical, item["vertical_id"])
            if vertical is None or not vertical.is_active:
                raise ValidationError("Unknown or inactive vertical in the projection.")
            if vertical.assigned_user_id is None:
                raise BusinessRuleError(
                    f"Vertical '{vertical.name}' is not assigned to any merchandiser — "
                    "assign it first."
                )
            if role == UserRole.MERCHANDISER and vertical.assigned_user_id != user_id:
                raise AuthorizationError(
                    f"Vertical '{vertical.name}' is not assigned to you."
                )

            amounts = {
                f"amount_{cur}": Decimal(str(item.get(f"amount_{cur}") or 0))
                for cur in ("usd", "eur", "cny")
            }
            for value in amounts.values():
                if value < 0:
                    raise ValidationError("Projection amounts cannot be negative.")

            existing = (
                await self._session.execute(
                    select(Projection).where(
                        Projection.vertical_id == vertical.id,
                        Projection.year == year,
                        Projection.month == month,
                    )
                )
            ).scalar_one_or_none()
            if existing:
                for field, value in amounts.items():
                    setattr(existing, field, value)
                existing.user_id = vertical.assigned_user_id
                existing.submitted_by = user_id
            else:
                self._session.add(
                    Projection(
                        vertical_id=vertical.id,
                        user_id=vertical.assigned_user_id,
                        year=year,
                        month=month,
                        submitted_by=user_id,
                        **amounts,
                    )
                )
            count += 1
        await self._session.flush()
        return count

    async def dashboard(self, year: int, month: int) -> list[dict]:
        """Projection vs actual per vertical for one month. Actuals = deposit
        amounts of live requests with a request date in the month, split
        USD / EUR / CNY."""
        start, end = month_bounds(year, month)

        def cur_sum(code: CurrencyCode, label: str):
            return func.coalesce(
                func.sum(case((DepositRequest.currency == code, DepositRequest.deposit_amount), else_=0)), 0
            ).label(label)

        actual_rows = (
            await self._session.execute(
                select(
                    DepositRequest.vertical_id,
                    cur_sum(CurrencyCode.USD, "usd"),
                    cur_sum(CurrencyCode.EUR, "eur"),
                    cur_sum(CurrencyCode.CNY, "cny"),
                )
                .where(
                    DepositRequest.is_deleted == False,  # noqa: E712
                    DepositRequest.current_status.notin_(_EXCLUDED_STATUSES),
                    func.date(DepositRequest.created_at) >= start,
                    func.date(DepositRequest.created_at) <= end,
                )
                .group_by(DepositRequest.vertical_id)
            )
        ).fetchall()
        actuals = {r.vertical_id: r for r in actual_rows}

        projections = (
            await self._session.execute(
                select(Projection)
                .where(Projection.year == year, Projection.month == month)
                .options(selectinload(Projection.vertical), selectinload(Projection.user))
            )
        ).scalars().all()
        proj_by_vertical = {p.vertical_id: p for p in projections}

        # Every vertical that has a projection OR actuals for the month, plus
        # assigned verticals with neither (so gaps are visible).
        verticals = (
            await self._session.execute(
                select(Vertical)
                .where(Vertical.is_active == True)  # noqa: E712
                .order_by(Vertical.name)
            )
        ).scalars().all()

        assignees = {
            u.id: u.full_name
            for u in (
                await self._session.execute(select(User).where(User.id.in_(
                    [v.assigned_user_id for v in verticals if v.assigned_user_id]
                )))
            ).scalars().all()
        } if any(v.assigned_user_id for v in verticals) else {}

        out: list[dict] = []
        for v in verticals:
            proj = proj_by_vertical.get(v.id)
            act = actuals.get(v.id)
            if proj is None and act is None and v.assigned_user_id is None:
                continue  # unassigned vertical with no data — noise
            merch = (
                proj.user.full_name if proj and proj.user
                else assignees.get(v.assigned_user_id)
            )
            out.append({
                "vertical_id": str(v.id),
                "vertical": v.name,
                "merchandiser": merch,
                "filled": proj is not None,
                "proj_usd": float(proj.amount_usd) if proj else 0.0,
                "proj_eur": float(proj.amount_eur) if proj else 0.0,
                "proj_cny": float(proj.amount_cny) if proj else 0.0,
                "actual_usd": float(act.usd) if act else 0.0,
                "actual_eur": float(act.eur) if act else 0.0,
                "actual_cny": float(act.cny) if act else 0.0,
            })
        return out

    async def assign_verticals(
        self, user_id: UUID, vertical_ids: list[UUID], actor_role: UserRole
    ) -> list[Vertical]:
        """Bind verticals to ONE user (Super Admin only): the given list
        becomes the user's assignment set. A vertical already assigned to a
        DIFFERENT user is refused (single vertical → single user)."""
        if actor_role != UserRole.SUPER_ADMIN:
            raise AuthorizationError("Only the Super Admin can assign verticals.")
        user = await self._session.get(User, user_id)
        if user is None:
            raise ValidationError("User not found.")

        wanted = set(vertical_ids)
        conflicts = (
            await self._session.execute(
                select(Vertical).where(
                    Vertical.id.in_(wanted) if wanted else False,
                    Vertical.assigned_user_id.isnot(None),
                    Vertical.assigned_user_id != user_id,
                )
            )
        ).scalars().all() if wanted else []
        if conflicts:
            raise BusinessRuleError(
                "Already assigned to another user: "
                + ", ".join(v.name for v in conflicts)
                + ". A vertical can belong to only one user — unassign it first."
            )

        current = (
            await self._session.execute(
                select(Vertical).where(Vertical.assigned_user_id == user_id)
            )
        ).scalars().all()
        for v in current:
            if v.id not in wanted:
                v.assigned_user_id = None
        if wanted:
            targets = (
                await self._session.execute(select(Vertical).where(Vertical.id.in_(wanted)))
            ).scalars().all()
            if len(targets) != len(wanted):
                raise ValidationError("One or more verticals not found.")
            for v in targets:
                v.assigned_user_id = user_id
        await self._session.flush()
        return await self.assigned_verticals(user_id)
