"""Projections module (4 Sep 2026; reworked 7 Oct 2026).

Cycle (client decisions):
- EVERY active vertical needs a projection each month (USD / EUR / CNY).
  Verticals are no longer assigned to a merchandiser: ANY merchandiser may
  fill ANY vertical, and may overwrite what a colleague entered — the row
  records who touched it last.
- From the 25th to the last day of each month the NEXT month is collected,
  and every merchandiser is reminded of the verticals still missing.
- Once the target month starts, a vertical still missing its projection is
  LOCKED: nobody may raise a request against that vertical, whatever their
  role (7 Oct 2026 — previously the whole merchandiser was blocked). Filling
  the projection unlocks it immediately, so the team can unblock itself.
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

    async def active_verticals(self) -> list[Vertical]:
        """Every active vertical — all of them need a projection each month
        since the assignment model was dropped (7 Oct 2026)."""
        rows = await self._session.execute(
            select(Vertical)
            .where(Vertical.is_active == True)  # noqa: E712
            .order_by(func.lower(Vertical.name))
        )
        return list(rows.scalars().all())

    async def missing_verticals(self, year: int, month: int) -> list[Vertical]:
        """Active verticals with no projection row for the period."""
        filled = (
            await self._session.execute(
                select(Projection.vertical_id).where(
                    Projection.year == year, Projection.month == month
                )
            )
        ).scalars().all()
        filled_ids = set(filled)
        return [v for v in await self.active_verticals() if v.id not in filled_ids]

    async def locked_vertical_ids(self, today: date | None = None) -> set[UUID]:
        """Verticals that cannot take a new request: the CURRENT month has
        started and their projection is still missing."""
        today = today or date.today()
        return {v.id for v in await self.missing_verticals(today.year, today.month)}

    async def assert_vertical_open(
        self, vertical_id: UUID | None, today: date | None = None
    ) -> None:
        """Gate for request creation — raises when the request's vertical has
        no projection for the current month. Applies to EVERY role (7 Oct
        2026): the vertical is locked, not the person."""
        if vertical_id is None:
            return
        today = today or date.today()
        missing = await self.missing_verticals(today.year, today.month)
        hit = next((v for v in missing if v.id == vertical_id), None)
        if hit is None:
            return
        raise BusinessRuleError(
            f"Requests for '{hit.name}' are on hold because its "
            f"{today.strftime('%B %Y')} projection has not been filed. "
            "Any merchandiser can add it on the Projections page — the vertical "
            "unlocks as soon as it is saved."
        )

    async def get_status(self, user_id: UUID, today: date | None = None) -> dict:
        """Everything the projections UI needs: the collection window, the
        target period's fill state across ALL verticals (with who filled each
        one), and which verticals are currently locked for request creation."""
        today = today or date.today()
        t_year, t_month = next_period(today)
        verticals = await self.active_verticals()

        filled_rows = (
            await self._session.execute(
                select(Projection)
                .where(Projection.year == t_year, Projection.month == t_month)
                .options(selectinload(Projection.submitter))
            )
        ).scalars().all()
        filled = {p.vertical_id: p for p in filled_rows}

        locked = await self.locked_vertical_ids(today)
        _, window_end = month_bounds(today.year, today.month)

        return {
            "window_open": window_open(today),
            "window_ends": window_end.isoformat(),
            "target_year": t_year,
            "target_month": t_month,
            "verticals": [
                {
                    "vertical_id": str(v.id),
                    "name": v.name,
                    "filled": v.id in filled,
                    "amount_usd": float(filled[v.id].amount_usd) if v.id in filled else None,
                    "amount_eur": float(filled[v.id].amount_eur) if v.id in filled else None,
                    "amount_cny": float(filled[v.id].amount_cny) if v.id in filled else None,
                    # Who touched the row last — any merchandiser may overwrite
                    # a colleague's figures, so the UI names the owner.
                    "last_updated_by": (
                        filled[v.id].submitter.full_name
                        if v.id in filled and filled[v.id].submitter
                        else None
                    ),
                    "last_updated_at": (
                        filled[v.id].updated_at.isoformat() if v.id in filled else None
                    ),
                    # Locked = this vertical's CURRENT month is missing, so no
                    # request may be raised against it right now.
                    "locked": v.id in locked,
                }
                for v in verticals
            ],
            "missing_target": [v.name for v in verticals if v.id not in filled],
            "locked_verticals": [v.name for v in verticals if v.id in locked],
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

        Any merchandiser may fill ANY vertical and overwrite what a
        colleague entered (7 Oct 2026) — ``submitted_by`` records who touched
        it last. Merchandisers are still held to the NEXT month during the
        25th→EOM window; the Super Admin may file any vertical for any
        period, which is how a vertical that missed the deadline is unlocked.
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
                # No vertical owner any more — the row belongs to whoever
                # last filled it, which is what the table shows.
                existing.user_id = user_id
                existing.submitted_by = user_id
            else:
                self._session.add(
                    Projection(
                        vertical_id=vertical.id,
                        user_id=user_id,
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
                .options(
                    selectinload(Projection.vertical),
                    selectinload(Projection.user),
                    selectinload(Projection.submitter),
                )
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

        out: list[dict] = []
        for v in verticals:
            proj = proj_by_vertical.get(v.id)
            act = actuals.get(v.id)
            if proj is None and act is None:
                continue  # nothing projected, nothing spent — noise
            # Verticals have no owner since 7 Oct 2026: the name shown is
            # whoever last filled the projection.
            merch = proj.submitter.full_name if proj and proj.submitter else None
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
