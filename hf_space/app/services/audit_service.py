"""Audit service — thin wrapper that enforces append-only writes to audit_logs."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import AuditAction
from app.repositories.audit_repo import AuditRepository


class AuditService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = AuditRepository(session)

    async def record_create(
        self, entity_name: str, entity_id: UUID, changed_by: UUID, **context: str
    ) -> None:
        await self._repo.log(
            entity_name=entity_name,
            entity_id=entity_id,
            action=AuditAction.CREATE,
            changed_by=changed_by,
            **context,
        )

    async def record_update(
        self,
        entity_name: str,
        entity_id: UUID,
        changed_by: UUID,
        field_name: str,
        old_value: str | None,
        new_value: str | None,
        **context: str,
    ) -> None:
        if old_value == new_value:
            return  # no-op — value unchanged
        await self._repo.log(
            entity_name=entity_name,
            entity_id=entity_id,
            action=AuditAction.UPDATE,
            changed_by=changed_by,
            field_name=field_name,
            old_value=old_value,
            new_value=new_value,
            **context,
        )

    async def record_status_change(
        self,
        entity_name: str,
        entity_id: UUID,
        changed_by: UUID,
        old_status: str | None,
        new_status: str,
        **context: str,
    ) -> None:
        await self._repo.log(
            entity_name=entity_name,
            entity_id=entity_id,
            action=AuditAction.STATUS_CHANGE,
            changed_by=changed_by,
            field_name="status",
            old_value=old_status,
            new_value=new_status,
            **context,
        )

    async def record_delete(
        self, entity_name: str, entity_id: UUID, changed_by: UUID
    ) -> None:
        await self._repo.log(
            entity_name=entity_name,
            entity_id=entity_id,
            action=AuditAction.DELETE,
            changed_by=changed_by,
        )

    async def list_for_entity(self, entity_name: str, entity_id: UUID):  # type: ignore[return]
        return await self._repo.list_for_entity(entity_name, entity_id)

    async def list_all_paginated(self, offset: int = 0, limit: int = 50):  # type: ignore[return]
        return await self._repo.list_all_paginated(offset=offset, limit=limit)

    async def count_all(self) -> int:
        return await self._repo.count_all()
