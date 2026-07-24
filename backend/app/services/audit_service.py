"""Audit service — append-only writes to audit_logs, synced to Supabase."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import AuditAction
from app.repositories.audit_repo import AuditRepository


class AuditService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = AuditRepository(session)

    async def record_create(
        self,
        entity_name: str,
        entity_id: UUID,
        changed_by: UUID,
        ip_address: str | None = None,
        user_agent: str | None = None,
        new_value: str | None = None,
    ) -> None:
        await self._repo.log(
            entity_name=entity_name,
            entity_id=entity_id,
            action=AuditAction.CREATE,
            changed_by=changed_by,
            ip_address=ip_address,
            user_agent=user_agent,
            new_value=new_value,
        )

    async def record_update(
        self,
        entity_name: str,
        entity_id: UUID,
        changed_by: UUID,
        field_name: str,
        old_value: str | None,
        new_value: str | None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        if str(old_value) == str(new_value):
            return
        await self._repo.log(
            entity_name=entity_name,
            entity_id=entity_id,
            action=AuditAction.UPDATE,
            changed_by=changed_by,
            field_name=field_name,
            old_value=str(old_value) if old_value is not None else None,
            new_value=str(new_value) if new_value is not None else None,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    async def record_status_change(
        self,
        entity_name: str,
        entity_id: UUID,
        changed_by: UUID,
        old_status: str | None,
        new_status: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        await self._repo.log(
            entity_name=entity_name,
            entity_id=entity_id,
            action=AuditAction.STATUS_CHANGE,
            changed_by=changed_by,
            field_name="status",
            old_value=old_status,
            new_value=new_status,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    async def record_delete(
        self,
        entity_name: str,
        entity_id: UUID,
        changed_by: UUID,
        old_value: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        await self._repo.log(
            entity_name=entity_name,
            entity_id=entity_id,
            action=AuditAction.DELETE,
            changed_by=changed_by,
            old_value=old_value,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    async def record_login(
        self,
        entity_id: UUID,
        changed_by: UUID,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        await self._repo.log(
            entity_name="users",
            entity_id=entity_id,
            action=AuditAction.LOGIN,
            changed_by=changed_by,
            field_name="last_login_at",
            ip_address=ip_address,
            user_agent=user_agent,
        )

    async def record_ai_query(
        self,
        changed_by: UUID,
        question: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        from uuid import uuid4
        await self._repo.log(
            entity_name="ai_bi",
            entity_id=uuid4(),
            action=AuditAction.AI_QUERY,
            changed_by=changed_by,
            field_name="question",
            new_value=question[:500],
            ip_address=ip_address,
            user_agent=user_agent,
        )

    async def list_for_entity(self, entity_name: str, entity_id: UUID):  # type: ignore[return]
        return await self._repo.list_for_entity(entity_name, entity_id)

    async def list_all_paginated(
        self,
        offset: int = 0,
        limit: int = 50,
        entity_name: str | None = None,
        action: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
    ):  # type: ignore[return]
        return await self._repo.list_all_paginated(
            offset=offset,
            limit=limit,
            entity_name=entity_name,
            action=action,
            from_date=from_date,
            to_date=to_date,
        )

    async def count_all(
        self,
        entity_name: str | None = None,
        action: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> int:
        return await self._repo.count_all(
            entity_name=entity_name,
            action=action,
            from_date=from_date,
            to_date=to_date,
        )
