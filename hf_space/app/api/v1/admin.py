"""Admin endpoints — audit logs, system config, integrations."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.dependencies import CurrentUser, RequireFinanceAdmin, RequireSuperAdmin
from app.core.exceptions import NotFoundError
from app.models.masters import SystemConfig
from app.repositories.audit_repo import AuditRepository
from app.schemas.common import MessageResponse
from app.schemas.masters import SystemConfigResponse, SystemConfigUpdate
from app.services.audit_service import AuditService

router = APIRouter(prefix="/admin", tags=["admin"])

DB = Annotated[AsyncSession, Depends(get_db_session)]
SuperAdmin = Annotated[CurrentUser, RequireSuperAdmin]
FinanceAdmin = Annotated[CurrentUser, RequireFinanceAdmin]


@router.get("/audit-logs")
async def list_audit_logs(
    current_user: FinanceAdmin,
    db: DB,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> dict:
    offset = (page - 1) * page_size
    svc = AuditService(db)
    logs = await svc.list_all_paginated(offset=offset, limit=page_size)
    total = await svc.count_all()
    items = [
        {
            "id": str(log.id),
            "entity_name": log.entity_name,
            "entity_id": str(log.entity_id),
            "field_name": log.field_name,
            "old_value": log.old_value,
            "new_value": log.new_value,
            "action": log.action.value,
            "changed_by_email": log.changed_by_user.email if log.changed_by_user else None,
            "changed_at": log.changed_at.isoformat(),
            "ip_address": str(log.ip_address) if log.ip_address else None,
        }
        for log in logs
    ]
    return {"items": items, "total": total}


@router.get("/system-config", response_model=list[SystemConfigResponse])
async def get_system_config(current_user: SuperAdmin, db: DB) -> list[SystemConfigResponse]:
    result = await db.execute(select(SystemConfig).order_by(SystemConfig.config_key))
    configs = list(result.scalars().all())
    return [SystemConfigResponse.model_validate(c) for c in configs]


@router.patch("/system-config/{config_key}", response_model=SystemConfigResponse)
async def update_system_config(
    config_key: str,
    data: SystemConfigUpdate,
    current_user: SuperAdmin,
    db: DB,
) -> SystemConfigResponse:
    result = await db.execute(
        select(SystemConfig).where(SystemConfig.config_key == config_key)
    )
    config = result.scalar_one_or_none()
    if not config:
        raise NotFoundError(f"Config key '{config_key}' not found.")

    old_value = config.config_value
    config.config_value = data.config_value
    config.updated_by = current_user.id
    if data.description:
        config.description = data.description

    await AuditService(db).record_update(
        "system_config", config.id, current_user.id,
        field_name=config_key, old_value=old_value, new_value=data.config_value,
    )
    return SystemConfigResponse.model_validate(config)


@router.post("/integrations/google-sheet/sync", response_model=MessageResponse)
async def trigger_sheet_sync(current_user: SuperAdmin, db: DB) -> MessageResponse:
    """Manually trigger a Google Sheet sync cycle."""
    from app.core.database import AsyncSessionFactory
    from app.integrations.google_sheets.sync_service import sync_from_sheet
    count = await sync_from_sheet(AsyncSessionFactory)
    return MessageResponse(message=f"Synced {count} new records from Google Sheet.")


@router.get("/integrations/sync-logs")
async def list_sync_logs(current_user: FinanceAdmin, db: DB) -> list[dict]:
    from app.models.integrations import SyncLog
    result = await db.execute(select(SyncLog).order_by(SyncLog.synced_at.desc()).limit(100))
    logs = list(result.scalars().all())
    return [
        {
            "id": str(log.id),
            "source_type": log.source_type.value,
            "source_reference": log.source_reference,
            "sync_status": log.sync_status.value,
            "records_synced": log.records_synced,
            "error_message": log.error_message,
            "synced_at": log.synced_at.isoformat(),
        }
        for log in logs
    ]
