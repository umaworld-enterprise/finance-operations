"""Repository for Supplier and DefaultedSupplier."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.integrations import DefaultedSupplier
from app.models.masters import Supplier
from app.repositories.base import BaseRepository


class SupplierRepository(BaseRepository[Supplier]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Supplier)

    async def list_active(self) -> list[Supplier]:
        result = await self._session.execute(
            select(Supplier).where(Supplier.is_active == True).order_by(Supplier.name)  # noqa: E712
        )
        return list(result.scalars().all())

    async def get_active_default_flag(self, supplier_id: UUID) -> DefaultedSupplier | None:
        """Return the active defaulted-supplier record if supplier is flagged, else None."""
        result = await self._session.execute(
            select(DefaultedSupplier)
            .where(
                DefaultedSupplier.supplier_id == supplier_id,
                DefaultedSupplier.is_active == True,  # noqa: E712
            )
            .options(selectinload(DefaultedSupplier.supplier))
        )
        return result.scalar_one_or_none()


class DefaultedSupplierRepository(BaseRepository[DefaultedSupplier]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, DefaultedSupplier)

    async def list_active(self) -> list[DefaultedSupplier]:
        result = await self._session.execute(
            select(DefaultedSupplier)
            .where(DefaultedSupplier.is_active == True)  # noqa: E712
            .options(selectinload(DefaultedSupplier.supplier))
            .order_by(DefaultedSupplier.flagged_date.desc())
        )
        return list(result.scalars().all())

    async def resolve(
        self, flag: DefaultedSupplier, resolved_by: UUID
    ) -> DefaultedSupplier:
        from datetime import date
        return await self.update(
            flag,
            is_active=False,
            resolved_date=date.today(),
            resolved_by=resolved_by,
        )
