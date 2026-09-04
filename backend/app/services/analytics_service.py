"""Analytics service — reads snapshots and computes aggregate summaries."""

import json
from datetime import date as Date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, case, extract, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.analytics import AnalyticsSnapshot
from app.models.deposit_request import DepositRequest
from app.models.enums import CurrencyCode, RequestStatus, UserRole
from app.models.integrations import DefaultedSupplier
from app.models.masters import Customer, Supplier, User, Vertical
from app.models.payment import PaymentDetails
from app.repositories.analytics_repo import AnalyticsRepository

# Cancelled / rejected PIs are excluded from every dashboard screen
# (Formula Reference §4, 2 Sep 2026).
_DASH_EXCLUDED_STATUSES = (
    RequestStatus.CANCELLED_BY_MERCHANDISER,
    RequestStatus.CANCELLED_BY_ACCOUNTS,
    RequestStatus.REJECTED_BY_HOM,
    RequestStatus.REJECTED_BY_ACCOUNTS,
)


def _days_from_etd_expr():
    """SQL expression: days overdue counted from the ORIGINAL Est ETD —
    etd_grace_overdue_days is anchored at the Grace ETD, so add the grace
    window span back (grace_etd − estimated_etd). Meaningful for Delayed rows
    (overdue > 0), where the sheet's TODAY() − Est ETD applies."""
    return AnalyticsSnapshot.etd_grace_overdue_days + (
        AnalyticsSnapshot.grace_etd - DepositRequest.estimated_etd
    )


def _notional_by_currency_cols():
    """Per-currency Notional Gain (= Cost of Fund) sums — the 4 Sep 2026
    sheet splits every grouped table's notional into USD / RMB / EUR."""
    def cur_sum(code: CurrencyCode, label: str):
        return func.coalesce(
            func.sum(
                case(
                    (DepositRequest.currency == code, AnalyticsSnapshot.cost_of_fund_amount),
                    else_=0,
                )
            ),
            0,
        ).label(label)

    return (
        cur_sum(CurrencyCode.USD, "notional_usd"),
        cur_sum(CurrencyCode.CNY, "notional_cny"),
        cur_sum(CurrencyCode.EUR, "notional_eur"),
    )


from app.schemas.analytics import AnalyticsFilters, AnalyticsSummary, FlaggedSupplierNpa, MerchandiserNpa, NpaResponse

# ── Analytics section keys (must stay in sync with frontend) ─────────────────
ANALYTICS_SECTIONS = [
    "overdue_kpis",
    "shipment_kpis",
    "delay_buckets",
    "by_merchandiser",
    "by_vertical",
    "by_customer",
    "outstanding_tracker",
]

DEFAULT_PERMISSIONS: dict[str, list[str]] = {
    "overdue_kpis":    ["finance_admin", "accounts_team"],
    "shipment_kpis":   ["finance_admin", "accounts_team", "merchandiser", "head_of_merchandiser"],
    "delay_buckets":   ["finance_admin"],
    # HoM dashboard's NPA panel links into the by_merchandiser drill-down.
    "by_merchandiser": ["finance_admin", "head_of_merchandiser"],
    "by_vertical":     ["finance_admin", "accounts_team"],
    "by_customer":     ["finance_admin", "accounts_team"],
    "outstanding_tracker": ["finance_admin", "accounts_team", "head_of_merchandiser"],
}


async def get_analytics_permissions(session: AsyncSession) -> dict[str, list[str]]:
    """Read analytics_permissions from system_config. Falls back to defaults."""
    row = await session.execute(
        text("SELECT config_value FROM system_config WHERE config_key = 'analytics_permissions'")
    )
    val = row.scalar_one_or_none()
    if val:
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            pass
    return DEFAULT_PERMISSIONS


async def save_analytics_permissions(
    session: AsyncSession, perms: dict[str, list[str]]
) -> None:
    """Upsert analytics_permissions into system_config."""
    await session.execute(
        text("""
            INSERT INTO system_config (id, config_key, config_value, description, updated_at)
            VALUES (gen_random_uuid(), 'analytics_permissions', :val, 'Analytics section access by role', NOW())
            ON CONFLICT (config_key) DO UPDATE
              SET config_value = EXCLUDED.config_value,
                  updated_at   = NOW()
        """),
        {"val": json.dumps(perms)},
    )


# head_of_merchandiser added 10 Aug 2026 (UAT follow-up): the role was
# missing entirely, and unknown roles resolve to False — so HOM saw NO gated
# field (not even the deposit amount they approve). Defaults mirror
# accounts_team: HOM approves what Accounts pay.
FIELD_VISIBILITY_DEFAULTS: dict[str, dict[str, bool]] = {
    "exchange_rate":                 {"merchandiser": False, "accounts_team": False, "finance_admin": True, "head_of_merchandiser": False},
    "deposit_amount":                {"merchandiser": True,  "accounts_team": True,  "finance_admin": True, "head_of_merchandiser": True},
    "deposit_percentage":            {"merchandiser": True,  "accounts_team": True,  "finance_admin": True, "head_of_merchandiser": True},
    "total_supplier_invoice_amount": {"merchandiser": True,  "accounts_team": True,  "finance_admin": True, "head_of_merchandiser": True},
    "payment_date":                  {"merchandiser": False, "accounts_team": True,  "finance_admin": True, "head_of_merchandiser": True},
    "bank":                          {"merchandiser": False, "accounts_team": True,  "finance_admin": True, "head_of_merchandiser": True},
    "payment_reference_number":      {"merchandiser": False, "accounts_team": True,  "finance_admin": True, "head_of_merchandiser": True},
    "ship_date":                     {"merchandiser": False, "accounts_team": True,  "finance_admin": True, "head_of_merchandiser": True},
    "accounts_remarks":              {"merchandiser": False, "accounts_team": True,  "finance_admin": True, "head_of_merchandiser": True},
    "grace_etd":                     {"merchandiser": False, "accounts_team": True,  "finance_admin": True, "head_of_merchandiser": True},
    "etd_grace_overdue_days":        {"merchandiser": False, "accounts_team": True,  "finance_admin": True, "head_of_merchandiser": True},
    "actual_etd_overdue_days":       {"merchandiser": False, "accounts_team": True,  "finance_admin": True, "head_of_merchandiser": True},
    "payment_to_ship_days":          {"merchandiser": False, "accounts_team": True,  "finance_admin": True, "head_of_merchandiser": True},
    # cost_of_fund and payment_to_request_days flipped ON for accounts + HoM
    # (12 Aug 2026 fix — the Analytics Snapshot card silently dropped both
    # rows for the Accounts role; they pay the file, they see its full cost).
    "payment_to_request_days":       {"merchandiser": False, "accounts_team": True,  "finance_admin": True, "head_of_merchandiser": True},
    "cost_of_fund":                  {"merchandiser": False, "accounts_team": True,  "finance_admin": True, "head_of_merchandiser": True},
    "default_status":                {"merchandiser": False, "accounts_team": True,  "finance_admin": True, "head_of_merchandiser": True},
    "creator_info":                  {"merchandiser": True,  "accounts_team": True,  "finance_admin": True, "head_of_merchandiser": True},
    "status_history":                {"merchandiser": True,  "accounts_team": True,  "finance_admin": True, "head_of_merchandiser": True},
    "accounts_timestamp":            {"merchandiser": False, "accounts_team": True,  "finance_admin": True, "head_of_merchandiser": True},
}


async def get_field_visibility(session: AsyncSession) -> dict[str, dict[str, bool]]:
    """Stored config merged OVER the defaults — a config saved before a new
    role (or field) existed inherits the defaults for the missing keys
    instead of silently resolving them to False."""
    row = await session.execute(
        text("SELECT config_value FROM system_config WHERE config_key = 'field_visibility'")
    )
    val = row.scalar_one_or_none()
    if val:
        try:
            stored = json.loads(val)
            merged: dict[str, dict[str, bool]] = {
                field: {**roles} for field, roles in FIELD_VISIBILITY_DEFAULTS.items()
            }
            for field, roles in stored.items():
                if not isinstance(roles, dict):
                    continue
                merged.setdefault(field, {})
                merged[field].update(roles)
            return merged
        except (json.JSONDecodeError, TypeError):
            pass
    return FIELD_VISIBILITY_DEFAULTS


async def save_field_visibility(session: AsyncSession, config: dict[str, dict[str, bool]]) -> None:
    await session.execute(
        text("""
            INSERT INTO system_config (id, config_key, config_value, description, updated_at)
            VALUES (gen_random_uuid(), 'field_visibility', :val, 'Field visibility by role in request detail views', NOW())
            ON CONFLICT (config_key) DO UPDATE
              SET config_value = EXCLUDED.config_value,
                  updated_at   = NOW()
        """),
        {"val": json.dumps(config)},
    )


def _merchandiser_scope(role: UserRole, user_id: UUID):
    """WHERE predicate limiting rows to the merchandiser's own requests.

    Returns None for every other role. Own requests = created in-app OR
    submitted via the public form with the user's registered email (legacy
    rows where created_by was NULL before the email-lookup fix). Mirrors
    DepositRequestRepository._apply_filters — keep the two in sync.
    """
    if role != UserRole.MERCHANDISER:
        return None
    user_email_sq = select(User.email).where(User.id == user_id).scalar_subquery()
    return or_(
        DepositRequest.created_by == user_id,
        and_(
            DepositRequest.created_by.is_(None),
            DepositRequest.submitter_email == user_email_sq,
        ),
    )


class AnalyticsService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = AnalyticsRepository(session)

    async def get_summary(
        self, role: UserRole, user_id: UUID, filters: AnalyticsFilters
    ) -> AnalyticsSummary:
        # ── Single query for request-level aggregates ────────────────────────
        req_stmt = (
            select(
                func.count(DepositRequest.id).label("total"),
                func.count(DepositRequest.id).filter(
                    DepositRequest.current_status == RequestStatus.PENDING_PAYMENT
                ).label("pending"),
                func.count(DepositRequest.id).filter(
                    DepositRequest.current_status == RequestStatus.PAYMENT_PROCESSED
                ).label("processed"),
                func.coalesce(func.sum(DepositRequest.deposit_amount), 0).label("total_exposure"),
            )
            .where(DepositRequest.is_deleted == False)  # noqa: E712
        )
        merch_filter = _merchandiser_scope(role, user_id)
        if merch_filter is not None:
            req_stmt = req_stmt.where(merch_filter)
        if filters.supplier_id:
            req_stmt = req_stmt.where(DepositRequest.supplier_id == filters.supplier_id)
        if filters.customer_id:
            req_stmt = req_stmt.where(DepositRequest.customer_id == filters.customer_id)
        if filters.vertical_id:
            req_stmt = req_stmt.where(DepositRequest.vertical_id == filters.vertical_id)
        if filters.staff_id:
            req_stmt = req_stmt.where(DepositRequest.created_by == filters.staff_id)
        if filters.date_from:
            req_stmt = req_stmt.where(DepositRequest.created_at >= filters.date_from)
        if filters.date_to:
            req_stmt = req_stmt.where(DepositRequest.created_at <= filters.date_to)

        req_row = (await self._session.execute(req_stmt)).one()

        # ── Single query for snapshot-level aggregates ───────────────────────
        snap_stmt = (
            select(
                func.count(AnalyticsSnapshot.id).filter(
                    AnalyticsSnapshot.etd_grace_overdue_days > 0
                ).label("overdue"),
                func.coalesce(func.sum(AnalyticsSnapshot.cost_of_fund_amount), 0).label("total_cof"),
                func.avg(AnalyticsSnapshot.payment_to_ship_days).label("avg_ship"),
            )
            .join(DepositRequest, AnalyticsSnapshot.deposit_request_id == DepositRequest.id)
            .where(DepositRequest.is_deleted == False)  # noqa: E712
        )
        if merch_filter is not None:
            snap_stmt = snap_stmt.where(merch_filter)
        if filters.supplier_id:
            snap_stmt = snap_stmt.where(DepositRequest.supplier_id == filters.supplier_id)
        if filters.customer_id:
            snap_stmt = snap_stmt.where(DepositRequest.customer_id == filters.customer_id)
        if filters.vertical_id:
            snap_stmt = snap_stmt.where(DepositRequest.vertical_id == filters.vertical_id)
        if filters.staff_id:
            snap_stmt = snap_stmt.where(DepositRequest.created_by == filters.staff_id)
        if filters.date_from:
            snap_stmt = snap_stmt.where(DepositRequest.created_at >= filters.date_from)
        if filters.date_to:
            snap_stmt = snap_stmt.where(DepositRequest.created_at <= filters.date_to)

        snap_row = (await self._session.execute(snap_stmt)).one()

        avg_ship = float(snap_row.avg_ship) if snap_row.avg_ship is not None else None

        return AnalyticsSummary(
            total_requests=req_row.total or 0,
            pending_payment_count=req_row.pending or 0,
            payment_processed_count=req_row.processed or 0,
            total_deposit_exposure=Decimal(str(req_row.total_exposure)),
            overdue_shipments=snap_row.overdue or 0,
            total_cost_of_fund=Decimal(str(snap_row.total_cof)),
            avg_payment_to_ship_days=avg_ship,
        )

    async def get_request_snapshots(
        self, role: UserRole, user_id: UUID, filters: AnalyticsFilters
    ) -> list[AnalyticsSnapshot]:
        stmt = (
            select(AnalyticsSnapshot)
            .join(DepositRequest, AnalyticsSnapshot.deposit_request_id == DepositRequest.id)
            .options(selectinload(AnalyticsSnapshot.deposit_request))
            .where(DepositRequest.is_deleted == False)  # noqa: E712
            .order_by(AnalyticsSnapshot.calculated_at.desc())
        )
        merch_filter = _merchandiser_scope(role, user_id)
        if merch_filter is not None:
            stmt = stmt.where(merch_filter)
        if filters.supplier_id:
            stmt = stmt.where(DepositRequest.supplier_id == filters.supplier_id)
        if filters.customer_id:
            stmt = stmt.where(DepositRequest.customer_id == filters.customer_id)
        if filters.vertical_id:
            stmt = stmt.where(DepositRequest.vertical_id == filters.vertical_id)
        if filters.staff_id:
            stmt = stmt.where(DepositRequest.created_by == filters.staff_id)
        if filters.date_from:
            stmt = stmt.where(DepositRequest.created_at >= filters.date_from)
        if filters.date_to:
            stmt = stmt.where(DepositRequest.created_at <= filters.date_to)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    # ── New dashboard endpoints ───────────────────────────────────────────────
    # Aligned to the Deposit Dashboard Formula Reference (2 Sep 2026):
    # cancelled/rejected PIs are excluded from every screen; "Delayed" =
    # etd_grace_overdue_days > 0 (paid + graced ETD passed + unshipped); day
    # counts shown to users run from the ORIGINAL Est ETD (overdue +
    # grace-window span), matching the sheet's TODAY() − Est ETD.

    async def get_overdue_by_currency(self, date_from: Date | None = None, date_to: Date | None = None) -> list[dict]:
        """Overdue deposit totals per currency (Delayed rows only) and
        notional gain per currency over ALL live rows — the formula reference
        (§3.A) sums Notional Gain unfiltered by status."""
        stmt = (
            select(
                DepositRequest.currency,
                func.count(DepositRequest.id).filter(
                    AnalyticsSnapshot.etd_grace_overdue_days > 0
                ).label("cases"),
                func.coalesce(func.sum(
                    case(
                        (AnalyticsSnapshot.etd_grace_overdue_days > 0, DepositRequest.deposit_amount),
                        else_=0,
                    )
                ), 0).label("overdue_amount"),
                func.coalesce(func.sum(AnalyticsSnapshot.cost_of_fund_amount), 0).label("notional_gain"),
            )
            .join(AnalyticsSnapshot, AnalyticsSnapshot.deposit_request_id == DepositRequest.id)
            .where(DepositRequest.is_deleted == False)  # noqa: E712
            .where(DepositRequest.current_status.notin_(_DASH_EXCLUDED_STATUSES))
            .group_by(DepositRequest.currency)
            .order_by(func.sum(
                case(
                    (AnalyticsSnapshot.etd_grace_overdue_days > 0, DepositRequest.deposit_amount),
                    else_=0,
                )
            ).desc())
        )
        if date_from:
            stmt = stmt.where(DepositRequest.created_at >= date_from)
        if date_to:
            stmt = stmt.where(DepositRequest.created_at <= date_to)
        rows = await self._session.execute(stmt)
        return [
            {
                "currency": r.currency.value if hasattr(r.currency, "value") else r.currency,
                "cases": r.cases,
                "overdue_amount": float(r.overdue_amount),
                "notional_gain": float(r.notional_gain),
            }
            for r in rows
        ]

    async def get_shipment_kpis(
        self,
        role: UserRole,
        user_id: UUID,
        date_from: Date | None = None,
        date_to: Date | None = None,
    ) -> dict:
        """5 shipment pipeline counters — single query with conditional COUNT aggregates.

        Merchandisers see only their own requests — this section is in their
        DEFAULT_PERMISSIONS allow-list, so the data itself must be scoped.
        """
        # Formula Reference §3.B (2 Sep 2026) — the five counters follow the
        # sheet's per-row STATUS, all derived from payment + ship dates:
        #   Delayed        = etd_grace_overdue_days > 0 (paid, unshipped, past grace)
        #   Graced ETD     = paid, unshipped, Est ETD < TODAY ≤ Grace ETD
        #   Shipped        = ship date recorded
        #   Yet to be Shipped = paid, unshipped, Est ETD not passed (or none)
        #   Total Active   = paid rows (the sheet's "Payt Date not blank")
        # Cancelled / rejected PIs are excluded from every counter.
        merch_filter = _merchandiser_scope(role, user_id)
        today = Date.today()
        paid = PaymentDetails.payment_date.isnot(None)
        unshipped = PaymentDetails.ship_date.is_(None)
        etd_passed = and_(
            DepositRequest.estimated_etd.isnot(None),
            DepositRequest.estimated_etd < today,
        )
        stmt = (
            select(
                func.count(DepositRequest.id).filter(paid).label("total_active"),
                func.count(DepositRequest.id).filter(
                    PaymentDetails.ship_date.isnot(None)
                ).label("total_shipped"),
                func.count(DepositRequest.id).filter(
                    AnalyticsSnapshot.etd_grace_overdue_days > 0
                ).label("total_overdue"),
                func.count(DepositRequest.id).filter(
                    and_(paid, unshipped, etd_passed, AnalyticsSnapshot.grace_etd >= today)
                ).label("etd_grace_pending"),
                func.count(DepositRequest.id).filter(
                    and_(
                        paid,
                        unshipped,
                        or_(
                            DepositRequest.estimated_etd.is_(None),
                            DepositRequest.estimated_etd >= today,
                        ),
                    )
                ).label("yet_to_ship"),
            )
            .select_from(DepositRequest)
            .outerjoin(AnalyticsSnapshot, AnalyticsSnapshot.deposit_request_id == DepositRequest.id)
            .outerjoin(PaymentDetails, PaymentDetails.deposit_request_id == DepositRequest.id)
            .where(DepositRequest.is_deleted == False)  # noqa: E712
            .where(DepositRequest.current_status.notin_(_DASH_EXCLUDED_STATUSES))
        )
        if merch_filter is not None:
            stmt = stmt.where(merch_filter)
        if date_from:
            stmt = stmt.where(DepositRequest.created_at >= date_from)
        if date_to:
            stmt = stmt.where(DepositRequest.created_at <= date_to)
        row = (await self._session.execute(stmt)).one()

        return {
            "total_overdue":    row.total_overdue or 0,
            "etd_grace_pending": row.etd_grace_pending or 0,
            "total_shipped":    row.total_shipped or 0,
            "yet_to_ship":      row.yet_to_ship or 0,
            "total_active":     row.total_active or 0,
        }

    async def get_delay_buckets(
        self,
        date_from: Date | None = None,
        date_to: Date | None = None,
        staff_id: UUID | None = None,
        vertical_id: UUID | None = None,
        customer_id: UUID | None = None,
    ) -> list[dict]:
        """Aging analysis per the Formula Reference §2.2/§2.3/§3.C
        (2 Sep 2026): 15-day buckets over days counted from the ORIGINAL Est
        ETD (the sheet's TODAY() − Est ETD). The Cases/Overdue columns cover
        only Graced/Delayed rows (paid, unshipped, ETD passed); Shipped and
        Yet-to-be-Shipped rows carry no delay range. The Notional columns are
        keyed off the Actual-ETD-Overdue days instead (§2.3) — they include
        shipped rows, deliberately a different row set. '% of Delayed' keeps
        the sheet's denominator (delayed buckets only, Graced excluded)."""
        BUCKETS: list[tuple[str, int | None, int | None]] = [
            ("Graced ETD",   None,  10),
            ("G-15 Days",    10,    15),
            ("15-30 Days",   15,   30),
            ("30-45 Days",   30,   45),
            ("45-60 Days",   45,   60),
            ("60-75 Days",   60,   75),
            ("75-90 Days",   75,   90),
            ("90-105 Days",  90,  105),
            ("105-120 Days", 105, 120),
            ("120-135 Days", 120, 135),
            ("135-150 Days", 135, 150),
            (">150 Days",    150, None),
        ]

        bucket_stmt = (
            select(
                AnalyticsSnapshot.etd_grace_overdue_days,
                AnalyticsSnapshot.actual_etd_overdue_days,
                AnalyticsSnapshot.grace_etd,
                DepositRequest.estimated_etd,
                PaymentDetails.payment_date,
                PaymentDetails.ship_date,
                DepositRequest.deposit_amount,
                DepositRequest.currency,
                AnalyticsSnapshot.cost_of_fund_amount,
            )
            .join(DepositRequest, AnalyticsSnapshot.deposit_request_id == DepositRequest.id)
            .outerjoin(PaymentDetails, PaymentDetails.deposit_request_id == DepositRequest.id)
            .where(DepositRequest.is_deleted == False)  # noqa: E712
            .where(DepositRequest.current_status.notin_(_DASH_EXCLUDED_STATUSES))
        )
        if date_from:
            bucket_stmt = bucket_stmt.where(DepositRequest.created_at >= date_from)
        if date_to:
            bucket_stmt = bucket_stmt.where(DepositRequest.created_at <= date_to)
        if staff_id:
            bucket_stmt = bucket_stmt.where(DepositRequest.created_by == staff_id)
        if vertical_id:
            bucket_stmt = bucket_stmt.where(DepositRequest.vertical_id == vertical_id)
        if customer_id:
            bucket_stmt = bucket_stmt.where(DepositRequest.customer_id == customer_id)
        all_rows = (await self._session.execute(bucket_stmt)).fetchall()

        today = Date.today()

        def delay_days(r) -> int | None:  # type: ignore[no-untyped-def]
            """Days from Est ETD for Graced/Delayed rows only — None for
            Shipped / Yet-to-be-Shipped / unpaid rows (no delay range)."""
            if r.payment_date is None or r.ship_date is not None:
                return None
            if r.estimated_etd is None or r.estimated_etd >= today:
                return None
            return (today - r.estimated_etd).days

        def in_bucket(days: int, low: int | None, high: int | None) -> bool:
            if low is not None and days <= low:
                return False
            return high is None or days <= high

        total_delayed = sum(
            1 for r in all_rows if r.etd_grace_overdue_days and r.etd_grace_overdue_days > 0
        )

        result = []
        for label, low, high in BUCKETS:
            matched = [
                r for r in all_rows
                if (d := delay_days(r)) is not None and in_bucket(d, low, high)
            ]
            cases = len(matched)
            by_cur: dict[str, float] = {}
            for r in matched:
                cur = r.currency.value if hasattr(r.currency, "value") else str(r.currency)
                by_cur[cur] = by_cur.get(cur, 0.0) + float(r.deposit_amount or 0)

            # Notional per bucket keys off Actual-ETD-Overdue days (§2.3):
            # every live row with the field, shipped ones included.
            notional: dict[str, float] = {}
            for r in all_rows:
                ae = r.actual_etd_overdue_days
                if ae is None or not in_bucket(ae, low, high):
                    continue
                cur = r.currency.value if hasattr(r.currency, "value") else str(r.currency)
                notional[cur] = notional.get(cur, 0.0) + float(r.cost_of_fund_amount or 0)

            pct_cases = round(cases / total_delayed * 100, 1) if total_delayed > 0 else 0.0
            result.append({
                "delay_range": label,
                "bucket_min": low,    # None for "Graced ETD"; days from Est ETD
                "bucket_max": high,   # None for ">150 Days"
                "cases": cases,
                "overdue_usd": by_cur.get("USD", 0.0),
                "overdue_cny": by_cur.get("CNY", 0.0),
                "overdue_eur": by_cur.get("EUR", 0.0),
                "pct_of_delayed_cases": pct_cases,
                "notional_usd": notional.get("USD", 0.0),
                "notional_cny": notional.get("CNY", 0.0),
                "notional_eur": notional.get("EUR", 0.0),
            })
        return result

    async def get_by_merchandiser(
        self,
        date_from: Date | None = None,
        date_to: Date | None = None,
        vertical_id: UUID | None = None,
        customer_id: UUID | None = None,
        etd_min: int | None = None,
        etd_max: int | None = None,
    ) -> list[dict]:
        """Overdue metrics grouped by merchandiser — Formula Reference §3.D
        (2 Sep 2026): Contribution % is CASES-based; Avg Delay counts days
        from the ORIGINAL Est ETD; Notional Gain (= Cost of Fund) sums over
        ALL of the merchandiser's live rows, not just the Delayed ones —
        PER CURRENCY since the 4 Sep 2026 sheet (USD / RMB / EUR columns)."""
        merch_stmt = (
            select(
                User.full_name,
                func.count(DepositRequest.id).label("overdue_cases"),
                func.coalesce(func.sum(
                    case((DepositRequest.currency == CurrencyCode.USD, DepositRequest.deposit_amount), else_=0)
                ), 0).label("overdue_usd"),
                func.coalesce(func.sum(
                    case((DepositRequest.currency == CurrencyCode.CNY, DepositRequest.deposit_amount), else_=0)
                ), 0).label("overdue_cny"),
                func.coalesce(func.sum(
                    case((DepositRequest.currency == CurrencyCode.EUR, DepositRequest.deposit_amount), else_=0)
                ), 0).label("overdue_eur"),
                func.coalesce(func.avg(_days_from_etd_expr()), 0).label("avg_delay"),
            )
            .join(AnalyticsSnapshot, AnalyticsSnapshot.deposit_request_id == DepositRequest.id)
            .join(User, User.id == DepositRequest.created_by)
            .where(DepositRequest.is_deleted == False)  # noqa: E712
            .where(DepositRequest.current_status.notin_(_DASH_EXCLUDED_STATUSES))
            .where(AnalyticsSnapshot.etd_grace_overdue_days > 0)
            .group_by(User.full_name)
            .order_by(func.sum(DepositRequest.deposit_amount).desc())
        )
        # Notional gain (Cost of Fund) per §3.D: every live row of the
        # merchandiser, split per currency (4 Sep 2026 sheet: USD/RMB/EUR).
        notional_stmt = (
            select(
                User.full_name,
                *_notional_by_currency_cols(),
            )
            .select_from(DepositRequest)
            .join(AnalyticsSnapshot, AnalyticsSnapshot.deposit_request_id == DepositRequest.id)
            .join(User, User.id == DepositRequest.created_by)
            .where(DepositRequest.is_deleted == False)  # noqa: E712
            .where(DepositRequest.current_status.notin_(_DASH_EXCLUDED_STATUSES))
            .group_by(User.full_name)
        )
        for col_filter in (
            (DepositRequest.created_at >= date_from) if date_from else None,
            (DepositRequest.created_at <= date_to) if date_to else None,
            (DepositRequest.vertical_id == vertical_id) if vertical_id else None,
            (DepositRequest.customer_id == customer_id) if customer_id else None,
        ):
            if col_filter is not None:
                merch_stmt = merch_stmt.where(col_filter)
                notional_stmt = notional_stmt.where(col_filter)
        if etd_min is not None:
            merch_stmt = merch_stmt.where(_days_from_etd_expr() > etd_min)
        if etd_max is not None:
            merch_stmt = merch_stmt.where(_days_from_etd_expr() <= etd_max)
        rows = (await self._session.execute(merch_stmt)).fetchall()
        notional_by_name = {
            r.full_name: (float(r.notional_usd), float(r.notional_cny), float(r.notional_eur))
            for r in (await self._session.execute(notional_stmt)).fetchall()
        }
        total_cases = sum(r.overdue_cases for r in rows)
        return [
            {
                "merchandiser": r.full_name,
                "overdue_cases": r.overdue_cases,
                "overdue_usd": float(r.overdue_usd),
                "overdue_cny": float(r.overdue_cny),
                "overdue_eur": float(r.overdue_eur),
                "contribution_pct": round(r.overdue_cases / total_cases * 100, 1) if total_cases else 0.0,
                "avg_delay_days": round(float(r.avg_delay), 0),
                # Cost of Fund per currency (4 Sep 2026 sheet); notional_gain
                # keeps the old USD-only value for backward compatibility.
                "notional_usd": notional_by_name.get(r.full_name, (0.0, 0.0, 0.0))[0],
                "notional_cny": notional_by_name.get(r.full_name, (0.0, 0.0, 0.0))[1],
                "notional_eur": notional_by_name.get(r.full_name, (0.0, 0.0, 0.0))[2],
                "notional_gain": notional_by_name.get(r.full_name, (0.0, 0.0, 0.0))[0],
            }
            for r in rows
        ]

    async def get_by_vertical(
        self,
        date_from: Date | None = None,
        date_to: Date | None = None,
        staff_id: UUID | None = None,
        customer_id: UUID | None = None,
        etd_min: int | None = None,
        etd_max: int | None = None,
    ) -> list[dict]:
        """Overdue metrics grouped by vertical/category."""
        vert_stmt = (
            select(
                Vertical.name,
                func.count(DepositRequest.id).label("overdue_cases"),
                func.coalesce(func.sum(
                    case((DepositRequest.currency == CurrencyCode.USD, DepositRequest.deposit_amount), else_=0)
                ), 0).label("overdue_usd"),
                func.coalesce(func.sum(
                    case((DepositRequest.currency == CurrencyCode.CNY, DepositRequest.deposit_amount), else_=0)
                ), 0).label("overdue_cny"),
                func.coalesce(func.sum(
                    case((DepositRequest.currency == CurrencyCode.EUR, DepositRequest.deposit_amount), else_=0)
                ), 0).label("overdue_eur"),
                func.coalesce(func.avg(_days_from_etd_expr()), 0).label("avg_delay"),
            )
            .join(AnalyticsSnapshot, AnalyticsSnapshot.deposit_request_id == DepositRequest.id)
            .join(Vertical, Vertical.id == DepositRequest.vertical_id)
            .where(DepositRequest.is_deleted == False)  # noqa: E712
            .where(DepositRequest.current_status.notin_(_DASH_EXCLUDED_STATUSES))
            .where(AnalyticsSnapshot.etd_grace_overdue_days > 0)
            .group_by(Vertical.name)
            .order_by(func.count(DepositRequest.id).desc())
        )
        # Notional gain (Cost of Fund) per §3.E: every live row of the
        # vertical, split per currency (4 Sep 2026 sheet: USD/RMB/EUR).
        notional_stmt = (
            select(
                Vertical.name,
                *_notional_by_currency_cols(),
            )
            .select_from(DepositRequest)
            .join(AnalyticsSnapshot, AnalyticsSnapshot.deposit_request_id == DepositRequest.id)
            .join(Vertical, Vertical.id == DepositRequest.vertical_id)
            .where(DepositRequest.is_deleted == False)  # noqa: E712
            .where(DepositRequest.current_status.notin_(_DASH_EXCLUDED_STATUSES))
            .group_by(Vertical.name)
        )
        for col_filter in (
            (DepositRequest.created_at >= date_from) if date_from else None,
            (DepositRequest.created_at <= date_to) if date_to else None,
            (DepositRequest.created_by == staff_id) if staff_id else None,
            (DepositRequest.customer_id == customer_id) if customer_id else None,
        ):
            if col_filter is not None:
                vert_stmt = vert_stmt.where(col_filter)
                notional_stmt = notional_stmt.where(col_filter)
        if etd_min is not None:
            vert_stmt = vert_stmt.where(_days_from_etd_expr() > etd_min)
        if etd_max is not None:
            vert_stmt = vert_stmt.where(_days_from_etd_expr() <= etd_max)
        rows = (await self._session.execute(vert_stmt)).fetchall()
        notional_by_name = {
            r.name: (float(r.notional_usd), float(r.notional_cny), float(r.notional_eur))
            for r in (await self._session.execute(notional_stmt)).fetchall()
        }
        total_cases = sum(r.overdue_cases for r in rows)
        return [
            {
                "category": r.name,
                "overdue_cases": r.overdue_cases,
                "overdue_usd": float(r.overdue_usd),
                "overdue_cny": float(r.overdue_cny),
                "overdue_eur": float(r.overdue_eur),
                "contribution_pct": round(r.overdue_cases / total_cases * 100, 1) if total_cases else 0.0,
                "avg_delay_days": round(float(r.avg_delay), 0),
                # Cost of Fund per currency (4 Sep 2026 sheet); notional_gain
                # keeps the old USD-only value for backward compatibility.
                "notional_usd": notional_by_name.get(r.name, (0.0, 0.0, 0.0))[0],
                "notional_cny": notional_by_name.get(r.name, (0.0, 0.0, 0.0))[1],
                "notional_eur": notional_by_name.get(r.name, (0.0, 0.0, 0.0))[2],
                "notional_gain": notional_by_name.get(r.name, (0.0, 0.0, 0.0))[0],
            }
            for r in rows
        ]

    async def get_outstanding_tracker(
        self,
        group_by: str,
        date_from: Date | None = None,
        date_to: Date | None = None,
    ) -> list[dict]:
        """Outstanding deposits — requested but not yet paid, at TRANCHE level.

        Every unpaid tranche on a live (not cancelled / rejected / deleted)
        request counts as outstanding; paid tranches are excluded, so partial
        payment is reflected correctly. Grouped by ISO week of the request's
        CREATED date (per the process note), merchandiser, customer or
        vertical, with per-currency totals (USD, CNY/RMB, EUR, … — whatever
        currencies exist in the data).
        """
        from datetime import timedelta

        from app.models.enums import TrancheStatus
        from app.models.tranche import PaymentTranche

        _EXCLUDED = (
            RequestStatus.CANCELLED_BY_MERCHANDISER,
            RequestStatus.CANCELLED_BY_ACCOUNTS,
            RequestStatus.REJECTED_BY_HOM,
        )
        stmt = (
            select(
                PaymentTranche.amount,
                DepositRequest.id.label("request_id"),
                DepositRequest.currency,
                DepositRequest.created_at,
                User.full_name.label("merchandiser_name"),
                DepositRequest.submitter_email,
                Customer.name.label("customer_name"),
                Vertical.name.label("vertical_name"),
            )
            .join(DepositRequest, PaymentTranche.deposit_request_id == DepositRequest.id)
            .join(Customer, Customer.id == DepositRequest.customer_id)
            .outerjoin(User, User.id == DepositRequest.created_by)
            .outerjoin(Vertical, Vertical.id == DepositRequest.vertical_id)
            .where(
                DepositRequest.is_deleted == False,  # noqa: E712
                DepositRequest.current_status.notin_(_EXCLUDED),
                PaymentTranche.status == TrancheStatus.UNPAID,
            )
        )
        if date_from:
            stmt = stmt.where(DepositRequest.created_at >= date_from)
        if date_to:
            stmt = stmt.where(DepositRequest.created_at <= date_to)
        rows = (await self._session.execute(stmt)).fetchall()

        def group_key(r) -> tuple:
            if group_by == "week":
                # ISO week of the request-created date: Monday–Sunday,
                # boundaries explicit in the label (DD/MM/YYYY "to" — Aug 2026
                # client request).
                created = r.created_at.date() if hasattr(r.created_at, "date") else r.created_at
                week_start = created - timedelta(days=created.weekday())
                week_end = week_start + timedelta(days=6)
                return (
                    week_start.isoformat(),
                    # 10-Aug-2026 style (10 Aug UAT follow-up) — reads as a
                    # week range at a glance, no day/month ambiguity.
                    f"{week_start.strftime('%d-%b-%Y')} to {week_end.strftime('%d-%b-%Y')}",
                )
            if group_by == "merchandiser":
                name = r.merchandiser_name or r.submitter_email or "Unassigned"
                return (name.lower(), name)
            if group_by == "customer":
                return (r.customer_name.lower(), r.customer_name)
            # vertical
            name = r.vertical_name or "Unassigned"
            return (name.lower(), name)

        groups: dict[tuple, dict] = {}
        for r in rows:
            key = group_key(r)
            g = groups.setdefault(
                key,
                {"group": key[1], "tranche_count": 0, "request_ids": set(), "outstanding": {}},
            )
            cur = r.currency.value if hasattr(r.currency, "value") else (r.currency or "OTHER")
            g["tranche_count"] += 1
            g["request_ids"].add(r.request_id)
            g["outstanding"][cur] = g["outstanding"].get(cur, 0.0) + float(r.amount or 0)

        # Weeks newest-first; name groups by largest outstanding first.
        if group_by == "week":
            ordered = sorted(groups.items(), key=lambda kv: kv[0][0], reverse=True)
        else:
            ordered = sorted(
                groups.items(), key=lambda kv: -sum(kv[1]["outstanding"].values())
            )
        return [
            {
                "group": g["group"],
                "tranche_count": g["tranche_count"],
                "request_count": len(g["request_ids"]),
                "outstanding": g["outstanding"],
            }
            for _, g in ordered
        ]

    async def get_weekly_deposit_tracker(self) -> list[dict]:
        """Weekly Deposit Tracker (Aug 2026 batch, item 4.1) — row-level view
        of requested, UNPAID deposits sorted by Estimated ETD and bucketed
        into ISO weeks (Monday–Sunday) of the ETD. Requests without an ETD
        collect in a trailing "No ETD" bucket.
        """
        from datetime import timedelta

        from app.models.enums import TrancheStatus
        from app.models.masters import Supplier
        from app.models.tranche import PaymentTranche, tranche_label

        _EXCLUDED = (
            RequestStatus.CANCELLED_BY_MERCHANDISER,
            RequestStatus.CANCELLED_BY_ACCOUNTS,
            RequestStatus.REJECTED_BY_HOM,
        )
        stmt = (
            select(
                PaymentTranche.amount,
                PaymentTranche.tranche_number,
                PaymentTranche.tentative_payment_date,
                DepositRequest.id.label("request_id"),
                DepositRequest.request_number,
                DepositRequest.sunshine_invoice_number,
                DepositRequest.currency,
                DepositRequest.estimated_etd,
                Supplier.name.label("supplier_name"),
            )
            .join(DepositRequest, PaymentTranche.deposit_request_id == DepositRequest.id)
            .join(Supplier, Supplier.id == DepositRequest.supplier_id)
            .where(
                DepositRequest.is_deleted == False,  # noqa: E712
                DepositRequest.current_status.notin_(_EXCLUDED),
                PaymentTranche.status == TrancheStatus.UNPAID,
            )
            # Portable NULLS LAST, then soonest ETD first.
            .order_by(
                DepositRequest.estimated_etd.is_(None),
                DepositRequest.estimated_etd,
                DepositRequest.request_number,
                PaymentTranche.tranche_number,
            )
        )
        rows = (await self._session.execute(stmt)).fetchall()

        groups: dict[str | None, dict] = {}
        for r in rows:
            if r.estimated_etd is not None:
                week_start = r.estimated_etd - timedelta(days=r.estimated_etd.weekday())
                week_end = week_start + timedelta(days=6)
                key: str | None = week_start.isoformat()
                label = f"{week_start.strftime('%d-%b-%Y')} to {week_end.strftime('%d-%b-%Y')}"
            else:
                key, label = None, "No ETD recorded"
            g = groups.setdefault(
                key, {"week": label, "week_start": key, "rows": [], "outstanding": {}}
            )
            cur = r.currency.value if hasattr(r.currency, "value") else (r.currency or "OTHER")
            g["rows"].append(
                {
                    "request_id": str(r.request_id),
                    "request_number": r.request_number,
                    "sunshine_invoice_number": r.sunshine_invoice_number,
                    "supplier_name": r.supplier_name,
                    "tranche_label": tranche_label(r.tranche_number),
                    "currency": cur,
                    "amount": float(r.amount or 0),
                    "tentative_payment_date": (
                        r.tentative_payment_date.isoformat()
                        if r.tentative_payment_date else None
                    ),
                    "estimated_etd": (
                        r.estimated_etd.isoformat() if r.estimated_etd else None
                    ),
                }
            )
            g["outstanding"][cur] = g["outstanding"].get(cur, 0.0) + float(r.amount or 0)

        # Soonest ETD week first; the "No ETD" bucket trails.
        ordered = sorted(groups.values(), key=lambda g: (g["week_start"] is None, g["week_start"] or ""))
        return ordered

    async def get_shipments_list(self) -> list[dict]:
        """All shipments (Aug 2026 batch, item 4.2) — every live request with
        Request #, Sunshine Invoice No., Original ETD, Amount, and Days
        Delayed computed server-side against TODAY (max(0, today − ETD);
        null when no ETD), so the number can never drift from the backend
        clock. Most-delayed first.
        """
        from datetime import date as _date

        from app.models.masters import Supplier
        from app.models.payment import PaymentDetails as _Payment

        _EXCLUDED = (
            RequestStatus.CANCELLED_BY_MERCHANDISER,
            RequestStatus.CANCELLED_BY_ACCOUNTS,
            RequestStatus.REJECTED_BY_HOM,
        )
        stmt = (
            select(
                DepositRequest.id.label("request_id"),
                DepositRequest.request_number,
                DepositRequest.sunshine_invoice_number,
                DepositRequest.currency,
                DepositRequest.deposit_amount,
                DepositRequest.estimated_etd,
                DepositRequest.current_status,
                DepositRequest.created_at,
                Supplier.name.label("supplier_name"),
                _Payment.payment_date,
            )
            .join(Supplier, Supplier.id == DepositRequest.supplier_id)
            .outerjoin(_Payment, _Payment.deposit_request_id == DepositRequest.id)
            .where(
                DepositRequest.is_deleted == False,  # noqa: E712
                DepositRequest.current_status.notin_(_EXCLUDED),
            )
        )
        rows = (await self._session.execute(stmt)).fetchall()
        today = _date.today()

        def to_row(r) -> dict:
            days_delayed = (
                max(0, (today - r.estimated_etd).days) if r.estimated_etd else None
            )
            cur = r.currency.value if hasattr(r.currency, "value") else r.currency
            status = (
                r.current_status.value
                if hasattr(r.current_status, "value")
                else r.current_status
            )
            return {
                "request_id": str(r.request_id),
                "request_number": r.request_number,
                "sunshine_invoice_number": r.sunshine_invoice_number,
                "supplier_name": r.supplier_name,
                "currency": cur,
                "amount": float(r.deposit_amount or 0),
                "estimated_etd": r.estimated_etd.isoformat() if r.estimated_etd else None,
                "days_delayed": days_delayed,
                "current_status": status,
                # Request date — drives the "Request date (new → old)" sort
                # on the Analytical Snapshot tables (19 Aug 2026).
                "created_at": r.created_at.isoformat() if r.created_at else None,
                # Payment date beside every paid amount (2 Sep 2026).
                "payment_date": r.payment_date.isoformat() if r.payment_date else None,
            }

        out = [to_row(r) for r in rows]
        # Most delayed first; ETD-less rows trail, newest request first there.
        out.sort(
            key=lambda x: (
                x["days_delayed"] is None,
                -(x["days_delayed"] or 0),
                x["estimated_etd"] or "",
                x["request_number"],
            )
        )
        return out

    async def get_monthly_trends(self, year: int, role: UserRole, user_id: UUID) -> list[dict]:
        """Per-month aggregates of overdue days and cost-of-fund for a given calendar year.

        Merchandisers see only their own requests — this feeds the ungated
        Overview tab, so it must be scoped like get_summary.
        """
        MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                       "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        stmt = (
            select(
                extract("month", DepositRequest.created_at).label("month"),
                func.coalesce(func.sum(AnalyticsSnapshot.etd_grace_overdue_days), 0).label("total_overdue_days"),
                func.coalesce(func.sum(AnalyticsSnapshot.cost_of_fund_amount), 0).label("total_cost_of_fund"),
                func.count(DepositRequest.id).label("request_count"),
            )
            .join(AnalyticsSnapshot, AnalyticsSnapshot.deposit_request_id == DepositRequest.id)
            .where(
                DepositRequest.is_deleted == False,  # noqa: E712
                extract("year", DepositRequest.created_at) == year,
            )
            .group_by(extract("month", DepositRequest.created_at))
            .order_by(extract("month", DepositRequest.created_at))
        )
        merch_filter = _merchandiser_scope(role, user_id)
        if merch_filter is not None:
            stmt = stmt.where(merch_filter)
        rows_r = await self._session.execute(stmt)
        rows = rows_r.fetchall()
        data_by_month = {int(r.month): r for r in rows}

        points = []
        ytd_overdue = 0
        ytd_cof = 0.0
        for m in range(1, 13):
            row = data_by_month.get(m)
            overdue = int(row.total_overdue_days or 0) if row else 0
            cof = float(row.total_cost_of_fund or 0) if row else 0.0
            count = int(row.request_count or 0) if row else 0
            ytd_overdue += overdue
            ytd_cof += cof
            points.append({
                "month": m,
                "month_name": MONTH_NAMES[m - 1],
                "total_overdue_days": overdue,
                "total_cost_of_fund": round(cof, 2),
                "ytd_overdue_days": ytd_overdue,
                "ytd_cost_of_fund": round(ytd_cof, 2),
                "request_count": count,
            })
        return points

    async def get_npa(self) -> NpaResponse:
        """Non-Performing Assets: overdue suppliers + merchandiser performance metrics.

        Sources overdue suppliers directly from analytics_snapshots (etd_grace_overdue_days > 0)
        so ALL overdue suppliers appear, not just those formally entered in defaulted_suppliers.
        Left-joins defaulted_suppliers to show formal flag info where it exists.
        """
        # 1. All suppliers with at least one overdue snapshot, plus formal flag info
        flag_stmt = (
            select(
                DepositRequest.supplier_id,
                Supplier.name.label("supplier_name"),
                func.count(AnalyticsSnapshot.id).label("overdue_count"),
                func.max(AnalyticsSnapshot.etd_grace_overdue_days).label("max_overdue_days"),
                func.max(DefaultedSupplier.flagged_date).label("flagged_date"),
                func.max(DefaultedSupplier.default_reason).label("default_reason"),
                func.bool_or(DefaultedSupplier.is_auto_flagged.is_(True)).label("is_auto_flagged"),
                func.bool_or(DefaultedSupplier.id.isnot(None)).label("is_formally_flagged"),
            )
            .join(Supplier, Supplier.id == DepositRequest.supplier_id)
            .join(AnalyticsSnapshot, AnalyticsSnapshot.deposit_request_id == DepositRequest.id)
            .outerjoin(
                DefaultedSupplier,
                and_(
                    DefaultedSupplier.supplier_id == DepositRequest.supplier_id,
                    DefaultedSupplier.is_active == True,  # noqa: E712
                ),
            )
            .where(
                AnalyticsSnapshot.etd_grace_overdue_days > 0,
                DepositRequest.is_deleted == False,  # noqa: E712
            )
            .group_by(DepositRequest.supplier_id, Supplier.name)
            .order_by(func.max(AnalyticsSnapshot.etd_grace_overdue_days).desc())
        )
        flag_rows = (await self._session.execute(flag_stmt)).fetchall()
        flagged_suppliers = [
            FlaggedSupplierNpa(
                supplier_id=r.supplier_id,
                supplier_name=r.supplier_name,
                flagged_date=r.flagged_date,
                default_reason=r.default_reason,
                is_auto_flagged=bool(r.is_auto_flagged),
                is_formally_flagged=bool(r.is_formally_flagged),
                overdue_request_count=r.overdue_count or 0,
                max_overdue_days=r.max_overdue_days or 0,
            )
            for r in flag_rows
        ]

        # 2. Merchandiser performance metrics
        merch_stmt = (
            select(
                User.id,
                User.full_name,
                User.email,
                func.count(DepositRequest.id).label("total_requests"),
                func.count(DepositRequest.id).filter(
                    AnalyticsSnapshot.etd_grace_overdue_days > 0
                ).label("overdue_count"),
                func.avg(
                    func.nullif(AnalyticsSnapshot.etd_grace_overdue_days, 0)
                ).label("avg_overdue_days"),
            )
            .join(DepositRequest, DepositRequest.created_by == User.id)
            .outerjoin(AnalyticsSnapshot, AnalyticsSnapshot.deposit_request_id == DepositRequest.id)
            .where(
                User.role == "merchandiser",
                DepositRequest.is_deleted == False,  # noqa: E712
            )
            .group_by(User.id, User.full_name, User.email)
            .order_by(func.count(DepositRequest.id).filter(
                AnalyticsSnapshot.etd_grace_overdue_days > 0
            ).desc())
        )
        merch_rows = (await self._session.execute(merch_stmt)).fetchall()
        merchandiser_performance = [
            MerchandiserNpa(
                merchandiser_id=r.id,
                name=r.full_name,
                email=r.email,
                total_requests=r.total_requests or 0,
                overdue_count=r.overdue_count or 0,
                avg_overdue_days=float(r.avg_overdue_days) if r.avg_overdue_days is not None else None,
            )
            for r in merch_rows
        ]

        return NpaResponse(
            flagged_suppliers=flagged_suppliers,
            merchandiser_performance=merchandiser_performance,
        )

    async def get_by_customer(
        self,
        date_from: Date | None = None,
        date_to: Date | None = None,
        staff_id: UUID | None = None,
        vertical_id: UUID | None = None,
        etd_min: int | None = None,
        etd_max: int | None = None,
    ) -> list[dict]:
        """Overdue metrics grouped by customer."""
        cust_stmt = (
            select(
                Customer.name,
                func.count(DepositRequest.id).label("overdue_cases"),
                func.coalesce(func.sum(
                    case((DepositRequest.currency == CurrencyCode.USD, DepositRequest.deposit_amount), else_=0)
                ), 0).label("overdue_usd"),
                func.coalesce(func.sum(
                    case((DepositRequest.currency == CurrencyCode.CNY, DepositRequest.deposit_amount), else_=0)
                ), 0).label("overdue_cny"),
                func.coalesce(func.sum(
                    case((DepositRequest.currency == CurrencyCode.EUR, DepositRequest.deposit_amount), else_=0)
                ), 0).label("overdue_eur"),
                func.coalesce(func.avg(_days_from_etd_expr()), 0).label("avg_delay"),
                func.coalesce(func.max(_days_from_etd_expr()), 0).label("max_delay"),
            )
            .join(AnalyticsSnapshot, AnalyticsSnapshot.deposit_request_id == DepositRequest.id)
            .join(Customer, Customer.id == DepositRequest.customer_id)
            .where(DepositRequest.is_deleted == False)  # noqa: E712
            .where(DepositRequest.current_status.notin_(_DASH_EXCLUDED_STATUSES))
            .where(AnalyticsSnapshot.etd_grace_overdue_days > 0)
            .group_by(Customer.name)
            .order_by(func.count(DepositRequest.id).desc())
        )
        # ETD Pending per §3.F = STATUS "Yet to be Shipped" (paid, unshipped,
        # Est ETD not passed / none) — counted over ALL live rows, not just
        # the Delayed ones. Notional per §3.D pattern: all live USD rows.
        today = Date.today()
        pending_stmt = (
            select(
                Customer.name,
                func.count(DepositRequest.id).filter(
                    and_(
                        PaymentDetails.payment_date.isnot(None),
                        PaymentDetails.ship_date.is_(None),
                        or_(
                            DepositRequest.estimated_etd.is_(None),
                            DepositRequest.estimated_etd >= today,
                        ),
                    )
                ).label("etd_pending"),
                *_notional_by_currency_cols(),
            )
            .select_from(DepositRequest)
            .join(Customer, Customer.id == DepositRequest.customer_id)
            .outerjoin(AnalyticsSnapshot, AnalyticsSnapshot.deposit_request_id == DepositRequest.id)
            .outerjoin(PaymentDetails, PaymentDetails.deposit_request_id == DepositRequest.id)
            .where(DepositRequest.is_deleted == False)  # noqa: E712
            .where(DepositRequest.current_status.notin_(_DASH_EXCLUDED_STATUSES))
            .group_by(Customer.name)
        )
        for col_filter in (
            (DepositRequest.created_at >= date_from) if date_from else None,
            (DepositRequest.created_at <= date_to) if date_to else None,
            (DepositRequest.created_by == staff_id) if staff_id else None,
            (DepositRequest.vertical_id == vertical_id) if vertical_id else None,
        ):
            if col_filter is not None:
                cust_stmt = cust_stmt.where(col_filter)
                pending_stmt = pending_stmt.where(col_filter)
        if etd_min is not None:
            cust_stmt = cust_stmt.where(_days_from_etd_expr() > etd_min)
        if etd_max is not None:
            cust_stmt = cust_stmt.where(_days_from_etd_expr() <= etd_max)
        rows = (await self._session.execute(cust_stmt)).fetchall()
        extras = {
            r.name: (
                r.etd_pending,
                float(r.notional_usd),
                float(r.notional_cny),
                float(r.notional_eur),
            )
            for r in (await self._session.execute(pending_stmt)).fetchall()
        }
        total_cases = sum(r.overdue_cases for r in rows)
        return [
            {
                "customer": r.name,
                "overdue_cases": r.overdue_cases,
                "overdue_usd": float(r.overdue_usd),
                "overdue_cny": float(r.overdue_cny),
                "overdue_eur": float(r.overdue_eur),
                "contribution_pct": round(r.overdue_cases / total_cases * 100, 1) if total_cases else 0.0,
                "avg_delay_days": round(float(r.avg_delay), 0),
                "max_delay_days": int(r.max_delay),
                "etd_pending": extras.get(r.name, (0, 0.0, 0.0, 0.0))[0],
                # Cost of Fund per currency (4 Sep 2026 sheet); notional_gain
                # keeps the old USD-only value for backward compatibility.
                "notional_usd": extras.get(r.name, (0, 0.0, 0.0, 0.0))[1],
                "notional_cny": extras.get(r.name, (0, 0.0, 0.0, 0.0))[2],
                "notional_eur": extras.get(r.name, (0, 0.0, 0.0, 0.0))[3],
                "notional_gain": extras.get(r.name, (0, 0.0, 0.0, 0.0))[1],
            }
            for r in rows
        ]
