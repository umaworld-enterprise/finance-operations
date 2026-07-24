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
