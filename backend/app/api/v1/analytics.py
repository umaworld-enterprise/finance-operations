"""Analytics endpoints — read-only, available to all roles."""

import json
from typing import Annotated
from uuid import UUID

from datetime import date as DateType

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionFactory, get_db_session
from app.core.dependencies import CurrentUser, get_current_user
from app.core.exceptions import AuthorizationError
from app.models.enums import UserRole
from app.schemas.analytics import AnalyticsFilters, AnalyticsSnapshotResponse, AnalyticsSummary, MonthlyTrendPoint, NpaResponse
from app.schemas.common import MessageResponse
from app.services.analytics_service import (
    AnalyticsService,
    ANALYTICS_SECTIONS,
    DEFAULT_PERMISSIONS,
    get_analytics_permissions,
)

router = APIRouter(prefix="/analytics", tags=["analytics"])

DB = Annotated[AsyncSession, Depends(get_db_session)]
User = Annotated[CurrentUser, Depends(get_current_user)]


def _parse_filters(
    supplier_id: UUID | None = None,
    customer_id: UUID | None = None,
    vertical_id: UUID | None = None,
    staff_id: UUID | None = None,
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
) -> AnalyticsFilters:
    # Malformed dates are silently dropped rather than raising ValueError,
    # which would escape FastAPI's validation and surface as a 500.
    return AnalyticsFilters(
        supplier_id=supplier_id,
        customer_id=customer_id,
        vertical_id=vertical_id,
        staff_id=staff_id,
        date_from=_parse_d(date_from),
        date_to=_parse_d(date_to),
    )


def _parse_d(value: str | None) -> DateType | None:
    try:
        return DateType.fromisoformat(value) if value else None
    except ValueError:
        return None


async def _check_section_access(section: str, current_user: CurrentUser, db: AsyncSession) -> None:
    """Raise AuthorizationError if the user's role is not allowed for the given section."""
    if current_user.role == UserRole.SUPER_ADMIN:
        return
    perms = await get_analytics_permissions(db)
    allowed_roles = perms.get(section, DEFAULT_PERMISSIONS.get(section, []))
    if current_user.role.value not in allowed_roles:
        raise AuthorizationError(
            f"Your role does not have access to the '{section}' analytics section. "
            "Contact your Super Admin to enable it."
        )


# ── Existing endpoints ────────────────────────────────────────────────────────

@router.get("/summary", response_model=AnalyticsSummary)
async def get_summary(
    current_user: User,
    db: DB,
    filters: AnalyticsFilters = Depends(_parse_filters),
) -> AnalyticsSummary:
    svc = AnalyticsService(db)
    return await svc.get_summary(current_user.role, current_user.id, filters)


@router.get("/requests", response_model=list[AnalyticsSnapshotResponse])
async def get_request_snapshots(
    current_user: User,
    db: DB,
    filters: AnalyticsFilters = Depends(_parse_filters),
) -> list[AnalyticsSnapshotResponse]:
    svc = AnalyticsService(db)
    snapshots = await svc.get_request_snapshots(current_user.role, current_user.id, filters)
    return [AnalyticsSnapshotResponse.from_orm_obj(s) for s in snapshots]


@router.post("/recalculate", response_model=MessageResponse)
async def recalculate_snapshots(
    current_user: User,
    background_tasks: BackgroundTasks,
) -> MessageResponse:
    """Trigger a full analytics snapshot refresh (Super Admin / Finance Admin only)."""
    if current_user.role not in {UserRole.SUPER_ADMIN, UserRole.FINANCE_ADMIN}:
        raise AuthorizationError("Only Super Admin or Finance Admin can trigger recalculation.")

    from app.analytics.snapshot_job import refresh_all_snapshots
    # force=True recomputes frozen (shipped/cancelled) rows too, so a manual
    # recalculation fully applies formula or config changes to stored values.
    background_tasks.add_task(refresh_all_snapshots, AsyncSessionFactory, True)
    return MessageResponse(message="Analytics recalculation started in background.")


# ── Permissions endpoint ──────────────────────────────────────────────────────

@router.get("/my-permissions")
async def get_my_permissions(current_user: User, db: DB) -> dict[str, bool]:
    """Returns which analytics sections the current user can access."""
    if current_user.role == UserRole.SUPER_ADMIN:
        return {section: True for section in ANALYTICS_SECTIONS}

    perms = await get_analytics_permissions(db)
    result: dict[str, bool] = {}
    for section in ANALYTICS_SECTIONS:
        allowed_roles = perms.get(section, DEFAULT_PERMISSIONS.get(section, []))
        result[section] = current_user.role.value in allowed_roles
    return result


# ── New dashboard endpoints ───────────────────────────────────────────────────

@router.get("/overdue-by-currency")
async def get_overdue_by_currency(
    current_user: User, db: DB,
    date_from: str | None = Query(None), date_to: str | None = Query(None),
) -> list[dict]:
    """Overdue deposit totals split by currency with notional gain."""
    await _check_section_access("overdue_kpis", current_user, db)
    svc = AnalyticsService(db)
    return await svc.get_overdue_by_currency(_parse_d(date_from), _parse_d(date_to))


@router.get("/shipment-kpis")
async def get_shipment_kpis(
    current_user: User, db: DB,
    date_from: str | None = Query(None), date_to: str | None = Query(None),
) -> dict:
    """5-card shipment pipeline counters. Merchandisers see only their own requests."""
    await _check_section_access("shipment_kpis", current_user, db)
    svc = AnalyticsService(db)
    return await svc.get_shipment_kpis(
        current_user.role, current_user.id, _parse_d(date_from), _parse_d(date_to)
    )


@router.get("/delay-buckets")
async def get_delay_buckets(
    current_user: User, db: DB,
    date_from: str | None = Query(None), date_to: str | None = Query(None),
    staff_id: UUID | None = Query(None),
    vertical_id: UUID | None = Query(None),
    customer_id: UUID | None = Query(None),
) -> list[dict]:
    """11-row aging analysis by delay range."""
    await _check_section_access("delay_buckets", current_user, db)
    svc = AnalyticsService(db)
    return await svc.get_delay_buckets(
        _parse_d(date_from), _parse_d(date_to),
        staff_id=staff_id, vertical_id=vertical_id, customer_id=customer_id,
    )


@router.get("/by-merchandiser")
async def get_by_merchandiser(
    current_user: User, db: DB,
    date_from: str | None = Query(None), date_to: str | None = Query(None),
    vertical_id: UUID | None = Query(None),
    customer_id: UUID | None = Query(None),
    etd_min: int | None = Query(None),
    etd_max: int | None = Query(None),
) -> list[dict]:
    """Overdue metrics grouped by merchandiser."""
    await _check_section_access("by_merchandiser", current_user, db)
    svc = AnalyticsService(db)
    return await svc.get_by_merchandiser(
        _parse_d(date_from), _parse_d(date_to),
        vertical_id=vertical_id, customer_id=customer_id,
        etd_min=etd_min, etd_max=etd_max,
    )


@router.get("/by-vertical")
async def get_by_vertical(
    current_user: User, db: DB,
    date_from: str | None = Query(None), date_to: str | None = Query(None),
    staff_id: UUID | None = Query(None),
    customer_id: UUID | None = Query(None),
    etd_min: int | None = Query(None),
    etd_max: int | None = Query(None),
) -> list[dict]:
    """Overdue metrics grouped by vertical/category."""
    await _check_section_access("by_vertical", current_user, db)
    svc = AnalyticsService(db)
    return await svc.get_by_vertical(
        _parse_d(date_from), _parse_d(date_to),
        staff_id=staff_id, customer_id=customer_id,
        etd_min=etd_min, etd_max=etd_max,
    )


@router.get("/by-customer")
async def get_by_customer(
    current_user: User, db: DB,
    date_from: str | None = Query(None), date_to: str | None = Query(None),
    staff_id: UUID | None = Query(None),
    vertical_id: UUID | None = Query(None),
    etd_min: int | None = Query(None),
    etd_max: int | None = Query(None),
) -> list[dict]:
    """Overdue metrics grouped by customer."""
    await _check_section_access("by_customer", current_user, db)
    svc = AnalyticsService(db)
    return await svc.get_by_customer(
        _parse_d(date_from), _parse_d(date_to),
        staff_id=staff_id, vertical_id=vertical_id,
        etd_min=etd_min, etd_max=etd_max,
    )


@router.get("/outstanding")
async def get_outstanding_tracker(
    current_user: User, db: DB,
    group_by: str = Query("week", pattern="^(week|merchandiser|customer|vertical)$"),
    date_from: str | None = Query(None), date_to: str | None = Query(None),
) -> list[dict]:
    """Outstanding Deposit Tracker — unpaid requested tranche value grouped by
    weekly request-date range, merchandiser, customer or vertical, with
    per-currency totals."""
    await _check_section_access("outstanding_tracker", current_user, db)
    svc = AnalyticsService(db)
    return await svc.get_outstanding_tracker(
        group_by, _parse_d(date_from), _parse_d(date_to)
    )


@router.get("/npa", response_model=NpaResponse)
async def get_npa(
    current_user: User,
    db: DB,
) -> NpaResponse:
    """Non-Performing Assets panel — flagged suppliers and merchandiser performance."""
    if current_user.role not in {UserRole.HEAD_OF_MERCHANDISER, UserRole.SUPER_ADMIN}:
        raise AuthorizationError("Only Head of Merchandiser or Super Admin can view NPA data.")
    svc = AnalyticsService(db)
    return await svc.get_npa()


@router.get("/monthly-trends", response_model=list[MonthlyTrendPoint])
async def get_monthly_trends(
    current_user: User,
    db: DB,
    year: int = Query(default=None),
) -> list[MonthlyTrendPoint]:
    """Monthly aggregates of overdue days and cost-of-fund for a given calendar year.

    Merchandisers see only their own requests — this feeds the ungated Overview tab.
    """
    import datetime
    resolved_year = year if year is not None else datetime.date.today().year
    svc = AnalyticsService(db)
    data = await svc.get_monthly_trends(
        year=resolved_year, role=current_user.role, user_id=current_user.id
    )
    return [MonthlyTrendPoint(**p) for p in data]
