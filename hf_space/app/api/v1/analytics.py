"""Analytics endpoints — read-only, available to all roles."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.dependencies import CurrentUser, get_current_user
from app.schemas.analytics import AnalyticsFilters, AnalyticsSnapshotResponse, AnalyticsSummary
from app.schemas.common import MessageResponse
from app.services.analytics_service import AnalyticsService

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
    from datetime import date
    return AnalyticsFilters(
        supplier_id=supplier_id,
        customer_id=customer_id,
        vertical_id=vertical_id,
        staff_id=staff_id,
        date_from=date.fromisoformat(date_from) if date_from else None,
        date_to=date.fromisoformat(date_to) if date_to else None,
    )


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
    return [AnalyticsSnapshotResponse.model_validate(s) for s in snapshots]


@router.post("/recalculate", response_model=MessageResponse)
async def recalculate_snapshots(
    current_user: User,
    db: DB,
) -> MessageResponse:
    """Trigger a full analytics snapshot refresh (Super Admin / Finance Admin only)."""
    from app.models.enums import UserRole
    from app.core.exceptions import AuthorizationError
    if current_user.role not in {UserRole.SUPER_ADMIN, UserRole.FINANCE_ADMIN}:
        raise AuthorizationError("Only Super Admin or Finance Admin can trigger recalculation.")

    from app.core.database import AsyncSessionFactory
    from app.analytics.snapshot_job import refresh_all_snapshots
    count = await refresh_all_snapshots(AsyncSessionFactory)
    return MessageResponse(message=f"Recalculated {count} analytics snapshots.")
