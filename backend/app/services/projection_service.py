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

from sqlalchemy import and_, case, func, select, text
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


# ── Editable window (5 Nov 2026) ─────────────────────────────────────────────
# A projection for month M may be filed or edited from the 25th of M-1 through
# the LAST DAY of M — "Please update projection for the month October 2026 on
# or before 31st October". It previously closed at the end of M-1, which left
# a merchandiser no way to correct a figure once the month was under way.

def window_opens_for(year: int, month: int) -> date:
    """The 25th of the month BEFORE the one being projected."""
    py, pm = (year - 1, 12) if month == 1 else (year, month - 1)
    return date(py, pm, WINDOW_OPENS_ON)


def period_editable(year: int, month: int, today: date) -> bool:
    return window_opens_for(year, month) <= today <= month_bounds(year, month)[1]


def reminder_period(today: date) -> tuple[int, int]:
    """The period the requester is nagged about. From the 25th it is NEXT
    month (its window has just opened); before that it is the month already
    running, which stays editable to its last day. The effect is one
    continuous reminder for October from 25 September to 31 October."""
    return next_period(today) if window_open(today) else (today.year, today.month)


# ── Feature switch: the per-vertical request lock (9 Oct 2026) ───────────────
# The lock shipped ON and stopped management raising requests for verticals
# with no projection. It is now OPT-IN and defaults to OFF: with no stored
# config row, nobody is blocked and projections are collected for reporting
# only. A Super Admin turns it on when the team is ready.
LOCK_CONFIG_KEY = "projection_lock_enabled"


async def lock_enabled(session: AsyncSession) -> bool:
    """Is the per-vertical request lock switched on? Defaults to False."""
    row = await session.execute(
        text("SELECT config_value FROM system_config WHERE config_key = :key"),
        {"key": LOCK_CONFIG_KEY},
    )
    val = row.scalar_one_or_none()
    return str(val).strip().lower() in {"true", "1", "yes", "on"} if val is not None else False


async def set_lock_enabled(session: AsyncSession, enabled: bool) -> None:
    """Upsert the switch. Postgres and SQLite both support this ON CONFLICT."""
    # The id is generated in Python rather than with gen_random_uuid() so the
    # same statement runs on Postgres and on the SQLite test database.
    import uuid as _uuid
    from datetime import datetime as _dt, timezone as _tz

    await session.execute(
        text("""
            INSERT INTO system_config (id, config_key, config_value, description, updated_at)
            VALUES (:id, :key, :val,
                    'Block new requests for verticals with no projection this month', :now)
            ON CONFLICT (config_key) DO UPDATE
              SET config_value = EXCLUDED.config_value,
                  updated_at   = EXCLUDED.updated_at
        """),
        {
            "id": str(_uuid.uuid4()),
            "key": LOCK_CONFIG_KEY,
            "val": "true" if enabled else "false",
            "now": _dt.now(_tz.utc),
        },
    )
    await session.flush()


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
        if not await lock_enabled(self._session):
            return set()
        return {v.id for v in await self.missing_verticals(today.year, today.month)}

    async def assert_vertical_open(
        self, vertical_id: UUID | None, today: date | None = None
    ) -> None:
        """Gate for request creation — raises when the request's vertical has
        no projection for the current month. Applies to EVERY role (7 Oct
        2026): the vertical is locked, not the person."""
        if vertical_id is None:
            return
        if not await lock_enabled(self._session):
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

    async def _actuals(self, vertical_id: UUID, start: date, end: date) -> dict[str, Decimal]:
        """Advance payment actually REQUESTED for one vertical in a date range
        — the deposit amounts of live requests raised in that window. Same
        basis as the projection dashboard, so the two never disagree."""
        row = (
            await self._session.execute(
                select(
                    func.coalesce(func.sum(case(
                        (DepositRequest.currency == CurrencyCode.USD, DepositRequest.deposit_amount),
                        else_=0)), 0).label("usd"),
                    func.coalesce(func.sum(case(
                        (DepositRequest.currency == CurrencyCode.EUR, DepositRequest.deposit_amount),
                        else_=0)), 0).label("eur"),
                    func.coalesce(func.sum(case(
                        (DepositRequest.currency == CurrencyCode.CNY, DepositRequest.deposit_amount),
                        else_=0)), 0).label("cny"),
                ).where(
                    DepositRequest.is_deleted == False,  # noqa: E712
                    DepositRequest.vertical_id == vertical_id,
                    DepositRequest.current_status.notin_(_EXCLUDED_STATUSES),
                    func.date(DepositRequest.created_at) >= start,
                    func.date(DepositRequest.created_at) <= end,
                )
            )
        ).one()
        return {c: Decimal(str(getattr(row, c) or 0)) for c in ("usd", "eur", "cny")}

    async def trend(
        self, vertical_id: UUID, year: int, month: int, months: int = 3
    ) -> dict:
        """The confirmation form's trend (5 Nov 2026, executive request).

        For the `months` periods BEFORE (year, month), each row carries what
        was projected, what was actually requested, and the gap between them
        — positive where the projection was an over-estimate. The suggested
        figure is the average of the ACTUALS, not of the past projections:
        the point of the exercise is to anchor next month on what the
        vertical really spends, not on what it previously guessed.
        """
        vertical = await self._session.get(Vertical, vertical_id)
        if vertical is None or not vertical.is_active:
            raise ValidationError("Unknown or inactive vertical.")

        periods: list[tuple[int, int]] = []
        y, m = year, month
        for _ in range(months):
            y, m = (y - 1, 12) if m == 1 else (y, m - 1)
            periods.append((y, m))

        rows = []
        for py, pm in periods:
            start, end = month_bounds(py, pm)
            proj = (
                await self._session.execute(
                    select(Projection).where(
                        Projection.vertical_id == vertical_id,
                        Projection.year == py,
                        Projection.month == pm,
                    )
                )
            ).scalar_one_or_none()
            actual = await self._actuals(vertical_id, start, end)
            row = {
                "year": py,
                "month": pm,
                "label": start.strftime("%b %Y"),
                "filled": proj is not None,
            }
            for cur in ("usd", "eur", "cny"):
                proposed = Decimal(str(getattr(proj, f"amount_{cur}"))) if proj else Decimal("0")
                row[f"proposed_{cur}"] = float(proposed)
                row[f"actual_{cur}"] = float(actual[cur])
                # Over-estimate positive, under-estimate negative — the
                # sheet's "Overestimated/Underestimated Projections".
                row[f"variance_{cur}"] = float(proposed - actual[cur])
            rows.append(row)

        suggested = {}
        for cur in ("usd", "eur", "cny"):
            total = sum(Decimal(str(r[f"actual_{cur}"])) for r in rows)
            avg = (total / Decimal(len(rows))) if rows else Decimal("0")
            suggested[f"suggested_{cur}"] = float(round(avg, 2))

        existing = (
            await self._session.execute(
                select(Projection)
                .where(
                    Projection.vertical_id == vertical_id,
                    Projection.year == year,
                    Projection.month == month,
                )
                .options(selectinload(Projection.submitter))
            )
        ).scalar_one_or_none()

        _, closes = month_bounds(year, month)
        today = date.today()
        return {
            "vertical_id": str(vertical_id),
            "vertical": vertical.name,
            "year": year,
            "month": month,
            "label": month_bounds(year, month)[0].strftime("%B %Y"),
            # Newest month first, as the sheet is laid out.
            "rows": rows,
            **suggested,
            "confirmed": existing is not None,
            "confirmed_usd": float(existing.amount_usd) if existing else None,
            "confirmed_eur": float(existing.amount_eur) if existing else None,
            "confirmed_cny": float(existing.amount_cny) if existing else None,
            "confirmed_by": (
                existing.submitter.full_name if existing and existing.submitter else None
            ),
            "confirmed_at": existing.updated_at.isoformat() if existing else None,
            # Editing stays open to the last day of the month being projected.
            "editable": period_editable(year, month, today),
            "editable_until": closes.isoformat(),
        }

    async def reminders(self, today: date | None = None) -> dict:
        """Which verticals still owe a projection for the period currently
        being chased, for the disclaimer on the request form (5 Nov 2026).

        Advisory only — it never blocks. The request form shows the banner
        when the vertical the requester picked appears in `pending`.
        """
        today = today or date.today()
        r_year, r_month = reminder_period(today)
        start, closes = month_bounds(r_year, r_month)
        missing = await self.missing_verticals(r_year, r_month)
        return {
            "year": r_year,
            "month": r_month,
            "period_label": start.strftime("%B %Y"),
            # "on or before 31st October" — the client's wording.
            "deadline_label": f"{closes.day} {closes.strftime('%B %Y')}",
            "deadline": closes.isoformat(),
            "pending": [{"vertical_id": str(v.id), "name": v.name} for v in missing],
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
            # Open from the 25th of the previous month to the LAST DAY of the
            # month being projected (5 Nov 2026) — the client asked for an
            # edit option "till end of the month", so a figure can be
            # corrected while the month is still running.
            if not period_editable(year, month, today):
                opens = window_opens_for(year, month)
                closes = month_bounds(year, month)[1]
                raise BusinessRuleError(
                    f"{month_bounds(year, month)[0].strftime('%B %Y')} projections can be "
                    f"filed or edited between {opens.strftime('%d %b %Y')} and "
                    f"{closes.strftime('%d %b %Y')}. Outside that window only the "
                    "Super Admin can change them."
                )
        elif role != UserRole.SUPER_ADMIN:
            raise AuthorizationError(
                "Only merchandisers (their own) or the Super Admin can file projections."
            )
        if not items:
            raise ValidationError("No projection rows supplied.")

        from app.services.audit_service import AuditService

        audit = AuditService(self._session)
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
                # Audit BEFORE mutating — "all changes should be audit
                # logged" (5 Nov 2026). One row per currency that moved;
                # record_update drops no-op fields on its own.
                for field, value in amounts.items():
                    await audit.record_update(
                        entity_name="projection",
                        entity_id=existing.id,
                        changed_by=user_id,
                        field_name=f"{field} {year}-{month:02d} {vertical.name}",
                        old_value=str(getattr(existing, field)),
                        new_value=str(value),
                    )
                for field, value in amounts.items():
                    setattr(existing, field, value)
                # No vertical owner any more — the row belongs to whoever
                # last filled it, which is what the table shows.
                existing.user_id = user_id
                existing.submitted_by = user_id
            else:
                fresh = Projection(
                    vertical_id=vertical.id,
                    user_id=user_id,
                    year=year,
                    month=month,
                    submitted_by=user_id,
                    **amounts,
                )
                self._session.add(fresh)
                # Flushed here so the audit row can carry the real id.
                await self._session.flush()
                await audit.record_create(
                    entity_name="projection",
                    entity_id=fresh.id,
                    changed_by=user_id,
                    new_value=(
                        f"{vertical.name} {year}-{month:02d}: "
                        + ", ".join(f"{k[-3:].upper()} {v}" for k, v in amounts.items())
                    ),
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
