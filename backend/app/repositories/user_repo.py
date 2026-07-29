"""Repository for User / Team Member Master."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.masters import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, User)

    async def get_by_email(self, email: str) -> User | None:
        # Case-insensitive: Google reports lowercase addresses while admins may
        # register users with mixed case.
        result = await self._session.execute(
            select(User).where(func.lower(User.email) == email.strip().lower())
        )
        return result.scalar_one_or_none()

    async def list_active(self) -> list[User]:
        result = await self._session.execute(
            select(User).where(User.is_active == True).order_by(User.full_name)  # noqa: E712
        )
        return list(result.scalars().all())
