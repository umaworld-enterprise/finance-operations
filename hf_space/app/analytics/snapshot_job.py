"""
Scheduled job: refreshes analytics_snapshots for all active deposit requests.

Runs via APScheduler. Can also be triggered manually via the admin API.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.analytics.engine import AnalyticsInput, compute
from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.deposit_request import DepositRequest
from app.models.masters import SystemConfig
from app.repositories.analytics_repo import AnalyticsRepository

logger = get_logger(__name__)
settings = get_settings()


async def _load_config(session: AsyncSession) -> dict[str, str]:
    result = await session.execute(select(SystemConfig))
    return {row.config_key: row.config_value for row in result.scalars().all()}


async def refresh_all_snapshots(session_factory: async_sessionmaker) -> int:
    """Recalculate analytics for every non-deleted request. Returns count refreshed."""
    async with session_factory() as session:
        config = await _load_config(session)

        etd_grace_days = int(config.get("etd_grace_days", settings.default_etd_grace_days))
        cost_rate = float(config.get("cost_of_fund_rate", settings.default_cost_of_fund_rate))
        cost_grace = int(config.get("cost_of_fund_grace_days", settings.default_cost_of_fund_grace_days))

        result = await session.execute(
            select(DepositRequest).where(DepositRequest.is_deleted == False)  # noqa: E712
        )
        requests = list(result.scalars().all())

        analytics_repo = AnalyticsRepository(session)
        count = 0

        for req in requests:
            payment = req.payment  # may be None if not loaded; load lazily
            try:
                inp = AnalyticsInput(
                    deposit_request_id=req.id,
                    estimated_etd=req.estimated_etd,
                    created_at=req.created_at.date(),
                    deposit_amount=Decimal(str(req.deposit_amount)),
                    payment_date=payment.payment_date if payment else None,
                    ship_date=payment.ship_date if payment else None,
                    etd_grace_days=etd_grace_days,
                    cost_of_fund_rate=cost_rate,
                    cost_of_fund_grace_days=cost_grace,
                )
                result_metrics = compute(inp)
                await analytics_repo.upsert(
                    req.id,
                    grace_etd=result_metrics.grace_etd,
                    etd_grace_overdue_days=result_metrics.etd_grace_overdue_days,
                    payment_to_ship_days=result_metrics.payment_to_ship_days,
                    payment_to_request_days=result_metrics.payment_to_request_days,
                    actual_etd_overdue_days=result_metrics.actual_etd_overdue_days,
                    cost_of_fund_applicable=result_metrics.cost_of_fund_applicable,
                    cost_of_fund_amount=result_metrics.cost_of_fund_amount,
                    default_status=result_metrics.default_status,
                )
                count += 1
            except Exception as exc:
                logger.error("Snapshot failed", request_id=str(req.id), error=str(exc))

        await session.commit()
        logger.info("Analytics snapshots refreshed", count=count)
        return count
