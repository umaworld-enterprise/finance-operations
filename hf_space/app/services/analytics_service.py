"""Analytics service — reads snapshots and computes aggregate summaries."""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analytics import AnalyticsSnapshot
from app.models.deposit_request import DepositRequest
from app.models.enums import RequestStatus, UserRole
from app.repositories.analytics_repo import AnalyticsRepository
from app.schemas.analytics import AnalyticsFilters, AnalyticsSummary


class AnalyticsService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = AnalyticsRepository(session)

    async def get_summary(
        self, role: UserRole, user_id: UUID, filters: AnalyticsFilters
    ) -> AnalyticsSummary:
        # Build base query scoped by role and filters
        stmt = (
            select(DepositRequest)
            .where(DepositRequest.is_deleted == False)  # noqa: E712
        )
        if role == UserRole.MERCHANDISER:
            stmt = stmt.where(DepositRequest.created_by == user_id)
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
        requests = list(result.scalars().all())

        request_ids = [r.id for r in requests]

        total = len(requests)
        pending = sum(1 for r in requests if r.current_status == RequestStatus.PENDING_PAYMENT)
        processed = sum(1 for r in requests if r.current_status == RequestStatus.PAYMENT_PROCESSED)
        total_exposure = sum(Decimal(str(r.deposit_amount)) for r in requests)

        # Pull snapshots
        overdue = 0
        total_cof = Decimal("0")
        ship_days: list[int] = []

        if request_ids:
            snap_result = await self._session.execute(
                select(AnalyticsSnapshot).where(
                    AnalyticsSnapshot.deposit_request_id.in_(request_ids)
                )
            )
            snapshots = list(snap_result.scalars().all())
            for snap in snapshots:
                if snap.etd_grace_overdue_days and snap.etd_grace_overdue_days > 0:
                    overdue += 1
                if snap.cost_of_fund_amount:
                    total_cof += Decimal(str(snap.cost_of_fund_amount))
                if snap.payment_to_ship_days is not None:
                    ship_days.append(snap.payment_to_ship_days)

        avg_ship = sum(ship_days) / len(ship_days) if ship_days else None

        return AnalyticsSummary(
            total_requests=total,
            pending_payment_count=pending,
            payment_processed_count=processed,
            total_deposit_exposure=total_exposure,
            overdue_shipments=overdue,
            total_cost_of_fund=total_cof,
            avg_payment_to_ship_days=avg_ship,
        )

    async def get_request_snapshots(
        self, role: UserRole, user_id: UUID, filters: AnalyticsFilters
    ) -> list[AnalyticsSnapshot]:
        stmt = (
            select(AnalyticsSnapshot)
            .join(DepositRequest, AnalyticsSnapshot.deposit_request_id == DepositRequest.id)
            .where(DepositRequest.is_deleted == False)  # noqa: E712
        )
        if role == UserRole.MERCHANDISER:
            stmt = stmt.where(DepositRequest.created_by == user_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
