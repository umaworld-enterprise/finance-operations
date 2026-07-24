"""Repository for DepositRequest with role-scoped queries."""

from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.deposit_request import DepositRequest
from app.models.enums import RequestStatus, UserRole
from app.repositories.base import BaseRepository


class DepositRequestRepository(BaseRepository[DepositRequest]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, DepositRequest)

    def _base_query(self) -> select:
        return (
            select(DepositRequest)
            .where(DepositRequest.is_deleted == False)  # noqa: E712
            .options(
                selectinload(DepositRequest.supplier),
                selectinload(DepositRequest.customer),
                selectinload(DepositRequest.vertical),
                selectinload(DepositRequest.creator),
                selectinload(DepositRequest.payment),
            )
        )

    async def list_for_role(
        self,
        role: UserRole,
        user_id: UUID,
        status: RequestStatus | None = None,
        supplier_id: UUID | None = None,
        customer_id: UUID | None = None,
        vertical_id: UUID | None = None,
        created_by: UUID | None = None,
    ) -> list[DepositRequest]:
        stmt = self._base_query()

        # Merchandisers see only their own records
        if role == UserRole.MERCHANDISER:
            stmt = stmt.where(DepositRequest.created_by == user_id)

        if status:
            stmt = stmt.where(DepositRequest.current_status == status)
        if supplier_id:
            stmt = stmt.where(DepositRequest.supplier_id == supplier_id)
        if customer_id:
            stmt = stmt.where(DepositRequest.customer_id == customer_id)
        if vertical_id:
            stmt = stmt.where(DepositRequest.vertical_id == vertical_id)
        if created_by:
            stmt = stmt.where(DepositRequest.created_by == created_by)

        stmt = stmt.order_by(DepositRequest.created_at.desc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_with_relations(self, id: UUID) -> DepositRequest | None:
        result = await self._session.execute(
            self._base_query()
            .where(DepositRequest.id == id)
            .options(
                selectinload(DepositRequest.status_history),
                selectinload(DepositRequest.merchandiser_actions),
                selectinload(DepositRequest.accounts_actions),
            )
        )
        return result.scalar_one_or_none()

    async def get_pending_payment_queue(self) -> list[DepositRequest]:
        """Pending requests sorted oldest first — for Accounts dashboard."""
        result = await self._session.execute(
            self._base_query()
            .where(DepositRequest.current_status == RequestStatus.PENDING_PAYMENT)
            .order_by(DepositRequest.created_at.asc())
        )
        return list(result.scalars().all())

    async def generate_request_number(self) -> str:
        """Generate next sequential request number: ADT-YYYY-NNNNN."""
        from datetime import datetime, timezone
        year = datetime.now(timezone.utc).year
        prefix = f"ADT-{year}-"
        result = await self._session.execute(
            select(func.count(DepositRequest.id)).where(
                DepositRequest.request_number.like(f"{prefix}%")
            )
        )
        count = result.scalar_one() or 0
        return f"{prefix}{count + 1:05d}"
