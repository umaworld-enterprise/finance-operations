"""Repository for User / Team Member Master."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.masters import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, User)

    async def get_by_email(self, email: str) -> User | None:
        result = await self._session.execute(
            select(User).where(User.email == email, User.is_deleted == False)  # noqa: E712
            if hasattr(User, "is_deleted")
            else select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()

    async def get_by_supabase_uid(self, supabase_uid: UUID) -> User | None:
        result = await self._session.execute(
            select(User).where(User.supabase_uid == supabase_uid)
        )
        return result.scalar_one_or_none()

    async def list_active(self) -> list[User]:
        result = await self._session.execute(
            select(User).where(User.is_active == True).order_by(User.full_name)  # noqa: E712
        )
        return list(result.scalars().all())
