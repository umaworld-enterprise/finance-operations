"""Repository for PaymentTranche and InvoiceAdjustment."""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.enums import AdjustmentStatus, TrancheStatus
from app.models.tranche import InvoiceAdjustment, PaymentTranche
from app.repositories.base import BaseRepository


class TrancheRepository(BaseRepository[PaymentTranche]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, PaymentTranche)

    async def list_for_request(self, deposit_request_id: UUID) -> list[PaymentTranche]:
        result = await self._session.execute(
            select(PaymentTranche)
            .where(PaymentTranche.deposit_request_id == deposit_request_id)
            .order_by(PaymentTranche.tranche_number)
        )
        return list(result.scalars().all())

    async def get_with_lock(self, tranche_id: UUID) -> PaymentTranche | None:
        """Row-level lock (SELECT … FOR UPDATE) — serialises concurrent pay /
        TT-upload / adjustment calls against the same tranche. SQLite (unit
        tests) ignores FOR UPDATE; its whole-database lock covers the same
        race."""
        result = await self._session.execute(
            select(PaymentTranche).where(PaymentTranche.id == tranche_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_with_request(self, tranche_id: UUID) -> PaymentTranche | None:
        result = await self._session.execute(
            select(PaymentTranche)
            .where(PaymentTranche.id == tranche_id)
            .options(selectinload(PaymentTranche.deposit_request))
        )
        return result.scalar_one_or_none()

    async def sum_amounts_for_request(self, deposit_request_id: UUID) -> Decimal:
        result = await self._session.execute(
            select(func.coalesce(func.sum(PaymentTranche.amount), 0)).where(
                PaymentTranche.deposit_request_id == deposit_request_id
            )
        )
        return Decimal(str(result.scalar_one()))

    async def count_unpaid_for_request(self, deposit_request_id: UUID) -> int:
        result = await self._session.execute(
            select(func.count(PaymentTranche.id)).where(
                PaymentTranche.deposit_request_id == deposit_request_id,
                PaymentTranche.status == TrancheStatus.UNPAID,
            )
        )
        return result.scalar_one()


class AdjustmentRepository(BaseRepository[InvoiceAdjustment]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, InvoiceAdjustment)

    async def adjusted_out_total(self, source_tranche_id: UUID) -> Decimal:
        """Total value already reallocated away from a paid tranche.

        Both completed and pending-approval adjustments reserve balance so a
        future approval workflow cannot over-allocate."""
        result = await self._session.execute(
            select(func.coalesce(func.sum(InvoiceAdjustment.amount), 0)).where(
                InvoiceAdjustment.source_tranche_id == source_tranche_id,
                InvoiceAdjustment.status != AdjustmentStatus.REJECTED,
            )
        )
        return Decimal(str(result.scalar_one()))

    async def adjusted_in_total(self, destination_tranche_id: UUID) -> Decimal:
        result = await self._session.execute(
            select(func.coalesce(func.sum(InvoiceAdjustment.amount), 0)).where(
                InvoiceAdjustment.destination_tranche_id == destination_tranche_id,
                InvoiceAdjustment.status == AdjustmentStatus.COMPLETED,
            )
        )
        return Decimal(str(result.scalar_one()))

    async def list_for_tranche_ids(self, tranche_ids: list[UUID]) -> list[InvoiceAdjustment]:
        if not tranche_ids:
            return []
        result = await self._session.execute(
            select(InvoiceAdjustment)
            .where(
                (InvoiceAdjustment.source_tranche_id.in_(tranche_ids))
                | (InvoiceAdjustment.destination_tranche_id.in_(tranche_ids))
            )
            .order_by(InvoiceAdjustment.created_at.desc())
        )
        return list(result.scalars().all())
