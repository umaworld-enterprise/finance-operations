"""Generic async repository with common CRUD operations."""

from typing import Any, Generic, TypeVar
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    def __init__(self, session: AsyncSession, model: type[ModelT]) -> None:
        self._session = session
        self._model = model

    async def get_by_id(self, id: UUID) -> ModelT | None:
        return await self._session.get(self._model, id)

    async def list_all(self, **filters: Any) -> list[ModelT]:
        stmt = select(self._model)
        for field, value in filters.items():
            stmt = stmt.where(getattr(self._model, field) == value)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, **kwargs: Any) -> ModelT:
        instance = self._model(**kwargs)
        self._session.add(instance)
        await self._session.flush()
        await self._session.refresh(instance)
        return instance

    async def update(self, instance: ModelT, **kwargs: Any) -> ModelT:
        for field, value in kwargs.items():
            setattr(instance, field, value)
        await self._session.flush()
        await self._session.refresh(instance)
        return instance

    async def soft_delete(self, instance: ModelT, deleted_by: UUID) -> ModelT:
        from datetime import datetime, timezone
        setattr(instance, "is_deleted", True)
        setattr(instance, "deleted_by", deleted_by)
        setattr(instance, "deleted_at", datetime.now(timezone.utc))
        await self._session.flush()
        return instance
