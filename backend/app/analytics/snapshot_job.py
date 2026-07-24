"""
Scheduled job: refreshes analytics_snapshots for all active deposit requests.

Runs via APScheduler. Can also be triggered manually via the admin API.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.analytics.engine import AnalyticsInput, compute
from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.deposit_request import DepositRequest
from app.models.enums import CurrencyCode
from app.models.integrations import DefaultedSupplier
from app.models.masters import SystemConfig
from app.repositories.analytics_repo import AnalyticsRepository
from app.repositories.supplier_repo import SupplierRepository

logger = get_logger(__name__)
settings = get_settings()


async def _load_config(session: AsyncSession) -> dict[str, str]:
    result = await session.execute(select(SystemConfig))
    return {row.config_key: row.config_value for row in result.scalars().all()}


async def _run_snapshots(session: AsyncSession, force: bool = False) -> int:
    """Core logic — runs inside the provided session.

    Each request is committed individually so a single bad row cannot leave
    the session in an aborted state and cascade InFailedSQLTransactionError
    to every subsequent upsert.  We avoid begin_nested() / SAVEPOINTs
    because Supabase's pgbouncer transaction pooler does not support them.
    """
    config = await _load_config(session)

    etd_grace_days = int(config.get("etd_grace_days", settings.default_etd_grace_days))
    cost_rate = float(config.get("cost_of_fund_rate", settings.default_cost_of_fund_rate))
    cost_grace = int(config.get("cost_of_fund_grace_days", settings.default_cost_of_fund_grace_days))

    # Skip rows whose metrics can never change again:
    #  - cancelled / rejected requests accrue nothing
    #  - processed requests with a ship date have fully static metrics
    # Only active rows and processed-but-unshipped rows tick day counters.
    from sqlalchemy import and_, not_, or_
    from app.models.enums import RequestStatus
    from app.models.payment import PaymentDetails

    _FROZEN = [
        RequestStatus.CANCELLED_BY_MERCHANDISER,
        RequestStatus.CANCELLED_BY_ACCOUNTS,
        RequestStatus.REJECTED_BY_HOM,
    ]
    stmt = (
        select(DepositRequest)
        .outerjoin(PaymentDetails, PaymentDetails.deposit_request_id == DepositRequest.id)
        .where(
            DepositRequest.is_deleted == False,  # noqa: E712
            DepositRequest.current_status.notin_(_FROZEN),
        )
        .options(selectinload(DepositRequest.payment))
    )
    if not force:
        # force=True (admin recalculate) also recomputes processed+shipped rows
        # — needed after formula/config changes so stored values match the new
        # rules. Cancelled/rejected rows stay excluded even then: their metrics
        # are meaningless and recomputing them would feed the auto-flag block.
        stmt = stmt.where(
            not_(
                and_(
                    DepositRequest.current_status == RequestStatus.PAYMENT_PROCESSED,
                    PaymentDetails.ship_date.is_not(None),
                )
            ),
        )
    result = await session.execute(stmt)
    requests = list(result.scalars().all())

    # Commit the initial read so each upsert below starts a clean transaction.
    # expire_on_commit=False means the loaded req/payment objects stay usable.
    await session.commit()

    analytics_repo = AnalyticsRepository(session)
    supplier_repo = SupplierRepository(session)
    count = 0

    for req in requests:
        payment = req.payment
        try:
            inp = AnalyticsInput(
                deposit_request_id=req.id,
                estimated_etd=req.estimated_etd,
                created_at=req.created_at.date(),
                deposit_amount=Decimal(str(req.deposit_amount)),
                payment_date=payment.payment_date if payment else None,
                ship_date=payment.ship_date if payment else None,
                actual_etd=payment.actual_etd if payment else None,
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

            if result_metrics.etd_grace_overdue_days and result_metrics.etd_grace_overdue_days > 0:
                existing = await supplier_repo.get_active_default_flag(req.supplier_id)
                if not existing:
                    session.add(DefaultedSupplier(
                        supplier_id=req.supplier_id,
                        outstanding_amount=0,
                        currency=CurrencyCode.USD,
                        default_reason=f"Auto-flagged: {result_metrics.etd_grace_overdue_days}d past ETD grace period",
                        flagged_date=date.today(),
                        flagged_by=None,
                        is_auto_flagged=True,
                    ))

            count += 1
            # Commit in batches of 100 — per-row commits cost a full network
            # round trip each; a failed batch is simply retried next cycle.
            if count % 100 == 0:
                await session.commit()
        except Exception as exc:
            logger.error("Snapshot failed", request_id=str(req.id), error=str(exc))
            await session.rollback()

    await session.commit()
    logger.info("Analytics snapshots refreshed", count=count)
    return count


async def refresh_all_snapshots(session_factory: async_sessionmaker, force: bool = False) -> int:
    """Recalculate analytics for every non-deleted request. Used by the scheduler."""
    try:
        async with session_factory() as session:
            return await _run_snapshots(session, force=force)
    except Exception as exc:
        logger.error("refresh_all_snapshots crashed", error=str(exc))
        return 0


async def seed_snapshot_for_request(request_id) -> None:  # type: ignore[no-untyped-def]
    """Compute + persist the analytics snapshot for ONE request.

    Designed for Starlette BackgroundTasks: runs after the response (and after
    the request's transaction has committed), with its own session, so it adds
    zero latency to the submit/payment hot path. Failures are logged and
    swallowed — snapshots are always recalculable by admins.
    """
    from app.core.database import AsyncSessionFactory

    try:
        async with AsyncSessionFactory() as session:
            config = await _load_config(session)
            result = await session.execute(
                select(DepositRequest)
                .where(DepositRequest.id == request_id, DepositRequest.is_deleted == False)  # noqa: E712
                .options(selectinload(DepositRequest.payment))
            )
            req = result.scalar_one_or_none()
            if req is None:
                return

            payment = req.payment
            inp = AnalyticsInput(
                deposit_request_id=req.id,
                estimated_etd=req.estimated_etd,
                created_at=req.created_at.date(),
                deposit_amount=Decimal(str(req.deposit_amount)),
                payment_date=payment.payment_date if payment else None,
                ship_date=payment.ship_date if payment else None,
                actual_etd=payment.actual_etd if payment else None,
                etd_grace_days=int(config.get("etd_grace_days", settings.default_etd_grace_days)),
                cost_of_fund_rate=float(config.get("cost_of_fund_rate", settings.default_cost_of_fund_rate)),
                cost_of_fund_grace_days=int(config.get("cost_of_fund_grace_days", settings.default_cost_of_fund_grace_days)),
            )
            metrics = compute(inp)

            await AnalyticsRepository(session).upsert(
                req.id,
                grace_etd=metrics.grace_etd,
                etd_grace_overdue_days=metrics.etd_grace_overdue_days,
                payment_to_ship_days=metrics.payment_to_ship_days,
                payment_to_request_days=metrics.payment_to_request_days,
                actual_etd_overdue_days=metrics.actual_etd_overdue_days,
                cost_of_fund_applicable=metrics.cost_of_fund_applicable,
                cost_of_fund_amount=metrics.cost_of_fund_amount,
                default_status=metrics.default_status,
            )

            if metrics.etd_grace_overdue_days and metrics.etd_grace_overdue_days > 0:
                existing = await SupplierRepository(session).get_active_default_flag(req.supplier_id)
                if not existing:
                    session.add(DefaultedSupplier(
                        supplier_id=req.supplier_id,
                        outstanding_amount=0,
                        currency=CurrencyCode.USD,
                        default_reason=f"Auto-flagged: {metrics.etd_grace_overdue_days}d past ETD grace period",
                        flagged_date=date.today(),
                        flagged_by=None,
                        is_auto_flagged=True,
                    ))

            await session.commit()
    except Exception as exc:
        logger.error("seed_snapshot_for_request failed", request_id=str(request_id), error=str(exc))
