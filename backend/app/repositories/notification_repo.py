"""Repository for Notification and PushSubscription."""

from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification, PushSubscription
from app.repositories.base import BaseRepository


class NotificationRepository(BaseRepository[Notification]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Notification)

    async def list_for_user(
        self, user_id: UUID, page: int = 1, page_size: int = 20
    ) -> tuple[list[Notification], int, int]:
        """Returns (items, total, unread_count) for the user, newest first."""
        base = select(Notification).where(Notification.user_id == user_id)
        total = (
            await self._session.execute(
                select(func.count()).select_from(base.subquery())
            )
        ).scalar_one()
        unread = (
            await self._session.execute(
                select(func.count()).where(
                    Notification.user_id == user_id, Notification.is_read == False  # noqa: E712
                )
            )
        ).scalar_one()
        result = await self._session.execute(
            base.order_by(Notification.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars().all()), total, unread

    async def mark_read(self, user_id: UUID, ids: list[UUID] | None) -> int:
        """Mark the given notifications (or all of the user's) as read."""
        stmt = (
            update(Notification)
            .where(Notification.user_id == user_id, Notification.is_read == False)  # noqa: E712
            .values(is_read=True)
        )
        if ids:
            stmt = stmt.where(Notification.id.in_(ids))
        result = await self._session.execute(stmt)
        return result.rowcount or 0

    async def exists_for_request(self, deposit_request_id: UUID, type_: str) -> bool:
        result = await self._session.execute(
            select(Notification.id)
            .where(
                Notification.deposit_request_id == deposit_request_id,
                Notification.type == type_,
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None


class PushSubscriptionRepository(BaseRepository[PushSubscription]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, PushSubscription)

    async def upsert(
        self, user_id: UUID, endpoint: str, p256dh: str, auth: str, user_agent: str | None
    ) -> PushSubscription:
        """Endpoint is globally unique — re-subscribing (possibly as a different
        user on a shared device) re-points the existing row."""
        result = await self._session.execute(
            select(PushSubscription).where(PushSubscription.endpoint == endpoint)
        )
        existing = result.scalar_one_or_none()
        if existing:
            return await self.update(
                existing, user_id=user_id, p256dh=p256dh, auth=auth, user_agent=user_agent
            )
        return await self.create(
            user_id=user_id, endpoint=endpoint, p256dh=p256dh, auth=auth, user_agent=user_agent
        )

    async def list_for_user(self, user_id: UUID) -> list[PushSubscription]:
        result = await self._session.execute(
            select(PushSubscription).where(PushSubscription.user_id == user_id)
        )
        return list(result.scalars().all())

    async def delete_by_endpoints(self, endpoints: list[str]) -> int:
        if not endpoints:
            return 0
        result = await self._session.execute(
            delete(PushSubscription).where(PushSubscription.endpoint.in_(endpoints))
        )
        return result.rowcount or 0
