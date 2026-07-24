"""Repository for PaymentDetails."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payment import PaymentDetails
from app.repositories.base import BaseRepository


class PaymentRepository(BaseRepository[PaymentDetails]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, PaymentDetails)

    async def get_by_request_id(self, deposit_request_id: UUID) -> PaymentDetails | None:
        result = await self._session.execute(
            select(PaymentDetails).where(
                PaymentDetails.deposit_request_id == deposit_request_id
            )
        )
        return result.scalar_one_or_none()

    async def get_by_request_id_with_lock(self, deposit_request_id: UUID) -> PaymentDetails | None:
        """Fetch the PaymentDetails row with a row-level lock (SELECT … FOR UPDATE)
        to prevent double-processing under concurrent requests."""
        stmt = (
            select(PaymentDetails)
            .where(PaymentDetails.deposit_request_id == deposit_request_id)
            .with_for_update()
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
