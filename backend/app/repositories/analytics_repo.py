"""Repository for AnalyticsSnapshot."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analytics import AnalyticsSnapshot
from app.repositories.base import BaseRepository


class AnalyticsRepository(BaseRepository[AnalyticsSnapshot]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, AnalyticsSnapshot)

    async def get_by_request_id(self, deposit_request_id: UUID) -> AnalyticsSnapshot | None:
        result = await self._session.execute(
            select(AnalyticsSnapshot).where(
                AnalyticsSnapshot.deposit_request_id == deposit_request_id
            )
        )
        return result.scalar_one_or_none()

    async def upsert(self, deposit_request_id: UUID, **fields) -> AnalyticsSnapshot:  # type: ignore[no-untyped-def]
        """Create or update snapshot for a given request."""
        from datetime import datetime, timezone
        from sqlalchemy.dialects.postgresql import insert

        stmt = (
            insert(AnalyticsSnapshot)
            .values(deposit_request_id=deposit_request_id, **fields)
            .on_conflict_do_update(
                index_elements=["deposit_request_id"],
                set_={**fields, "calculated_at": datetime.now(timezone.utc)},
            )
            .returning(AnalyticsSnapshot)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()
