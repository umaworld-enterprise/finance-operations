"""Repository for AuditLog — append-only."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.audit import AuditLog
from app.models.enums import AuditAction
from app.repositories.base import BaseRepository


class AuditRepository(BaseRepository[AuditLog]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, AuditLog)

    async def log(
        self,
        entity_name: str,
        entity_id: UUID,
        action: AuditAction,
        changed_by: UUID,
        field_name: str | None = None,
        old_value: str | None = None,
        new_value: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AuditLog:
        return await self.create(
            entity_name=entity_name,
            entity_id=entity_id,
            action=action,
            changed_by=changed_by,
            field_name=field_name,
            old_value=old_value,
            new_value=new_value,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    async def list_for_entity(
        self, entity_name: str, entity_id: UUID
    ) -> list[AuditLog]:
        result = await self._session.execute(
            select(AuditLog)
            .where(
                AuditLog.entity_name == entity_name,
                AuditLog.entity_id == entity_id,
            )
            .order_by(AuditLog.changed_at.desc())
        )
        return list(result.scalars().all())

    async def list_all_paginated(
        self, offset: int = 0, limit: int = 50
    ) -> list[AuditLog]:
        result = await self._session.execute(
            select(AuditLog)
            .options(selectinload(AuditLog.changed_by_user))
            .order_by(AuditLog.changed_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_all(self) -> int:
        result = await self._session.execute(
            select(func.count()).select_from(AuditLog)
        )
        return int(result.scalar_one())
