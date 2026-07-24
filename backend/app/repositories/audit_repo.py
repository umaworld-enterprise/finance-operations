"""Repository for AuditLog — append-only, with filtering support."""

from datetime import datetime
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

    def _base_query(
        self,
        entity_name: str | None = None,
        action: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
    ):
        q = select(AuditLog).options(selectinload(AuditLog.changed_by_user))
        if entity_name:
            q = q.where(AuditLog.entity_name == entity_name)
        if action:
            q = q.where(AuditLog.action == action)
        if from_date:
            q = q.where(AuditLog.changed_at >= datetime.fromisoformat(from_date))
        if to_date:
            q = q.where(AuditLog.changed_at <= datetime.fromisoformat(to_date + "T23:59:59"))
        return q

    async def list_for_entity(self, entity_name: str, entity_id: UUID) -> list[AuditLog]:
        result = await self._session.execute(
            select(AuditLog)
            .options(selectinload(AuditLog.changed_by_user))
            .where(
                AuditLog.entity_name == entity_name,
                AuditLog.entity_id == entity_id,
            )
            .order_by(AuditLog.changed_at.desc())
        )
        return list(result.scalars().all())

    async def list_all_paginated(
        self,
        offset: int = 0,
        limit: int = 50,
        entity_name: str | None = None,
        action: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> list[AuditLog]:
        q = self._base_query(entity_name, action, from_date, to_date)
        q = q.order_by(AuditLog.changed_at.desc()).offset(offset).limit(limit)
        result = await self._session.execute(q)
        return list(result.scalars().all())

    async def count_all(
        self,
        entity_name: str | None = None,
        action: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> int:
        q = self._base_query(entity_name, action, from_date, to_date)
        count_q = select(func.count()).select_from(q.subquery())
        result = await self._session.execute(count_q)
        return int(result.scalar_one())
