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
    current_user: SuperAdmin,
    db: DB,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    entity: str | None = Query(None),
    action: str | None = Query(None),
    from_date: str | None = Query(None),
    to_date: str | None = Query(None),
) -> dict:
    offset = (page - 1) * page_size
    svc = AuditService(db)
    logs = await svc.list_all_paginated(
        offset=offset, limit=page_size,
        entity_name=entity, action=action,
        from_date=from_date, to_date=to_date,
    )
    total = await svc.count_all(
        entity_name=entity, action=action,
        from_date=from_date, to_date=to_date,
    )
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
            "changed_by_name": log.changed_by_user.full_name if log.changed_by_user else None,
            "changed_at": log.changed_at.isoformat(),
            "ip_address": str(log.ip_address) if log.ip_address else None,
            "user_agent": log.user_agent,
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


@router.get("/analytics-permissions")
async def get_analytics_permissions_endpoint(current_user: SuperAdmin, db: DB) -> dict:
    """Get the current analytics section → allowed roles mapping."""
    from app.services.analytics_service import get_analytics_permissions, ANALYTICS_SECTIONS, DEFAULT_PERMISSIONS
    perms = await get_analytics_permissions(db)
    # Ensure all sections are present
    return {s: perms.get(s, DEFAULT_PERMISSIONS.get(s, [])) for s in ANALYTICS_SECTIONS}


@router.put("/analytics-permissions")
async def set_analytics_permissions_endpoint(
    body: dict,
    current_user: SuperAdmin,
    db: DB,
) -> dict:
    """Set analytics section → allowed roles mapping. Super Admin only."""
    from app.services.analytics_service import (
        save_analytics_permissions, ANALYTICS_SECTIONS, DEFAULT_PERMISSIONS
    )
    from app.models.enums import UserRole

    valid_roles = {r.value for r in UserRole if r != UserRole.SUPER_ADMIN}
    valid_sections = set(ANALYTICS_SECTIONS)

    cleaned: dict[str, list[str]] = {}
    for section, roles in body.items():
        if section not in valid_sections:
            continue
        if not isinstance(roles, list):
            continue
        cleaned[section] = [r for r in roles if r in valid_roles]

    # Fill missing sections with defaults
    for s in ANALYTICS_SECTIONS:
        if s not in cleaned:
            cleaned[s] = DEFAULT_PERMISSIONS.get(s, [])

    await save_analytics_permissions(db, cleaned)
    await db.commit()
    return cleaned


@router.get("/field-visibility")
async def get_field_visibility_endpoint(current_user: SuperAdmin, db: DB) -> dict:
    """Get the field-level visibility config for all roles."""
    from app.services.analytics_service import get_field_visibility, FIELD_VISIBILITY_DEFAULTS
    config = await get_field_visibility(db)
    return {k: config.get(k, FIELD_VISIBILITY_DEFAULTS.get(k, {})) for k in FIELD_VISIBILITY_DEFAULTS}


@router.put("/field-visibility")
async def set_field_visibility_endpoint(body: dict, current_user: SuperAdmin, db: DB) -> dict:
    """Save the field-level visibility config. Super Admin only."""
    from app.services.analytics_service import save_field_visibility, FIELD_VISIBILITY_DEFAULTS
    valid_roles = {"merchandiser", "accounts_team", "finance_admin"}
    cleaned: dict[str, dict[str, bool]] = {}
    for field_key, role_map in body.items():
        if field_key not in FIELD_VISIBILITY_DEFAULTS:
            continue
        if not isinstance(role_map, dict):
            continue
        cleaned[field_key] = {r: bool(v) for r, v in role_map.items() if r in valid_roles}
    for k in FIELD_VISIBILITY_DEFAULTS:
        if k not in cleaned:
            cleaned[k] = FIELD_VISIBILITY_DEFAULTS[k]
    await save_field_visibility(db, cleaned)
    await db.commit()
    return cleaned


@router.get("/form-config")
async def get_form_config(current_user: SuperAdmin, db: DB) -> dict:
    """Return the public form field configuration."""
    result = await db.execute(
        select(SystemConfig).where(SystemConfig.config_key == "public_form_fields")
    )
    cfg = result.scalar_one_or_none()
    if not cfg:
        return {}
    import json
    try:
        return json.loads(cfg.config_value)
    except (ValueError, Exception):
        return {}


@router.put("/form-config")
async def set_form_config(body: dict, current_user: SuperAdmin, db: DB) -> dict:
    """Save the public form field configuration. Super Admin only."""
    import json
    from app.services.audit_service import AuditService

    result = await db.execute(
        select(SystemConfig).where(SystemConfig.config_key == "public_form_fields")
    )
    cfg = result.scalar_one_or_none()
    new_value = json.dumps(body)
    if cfg:
        old_value = cfg.config_value
        cfg.config_value = new_value
        cfg.updated_by = current_user.id
        await AuditService(db).record_update(
            "system_config", cfg.id, current_user.id,
            field_name="public_form_fields",
            old_value=old_value,
            new_value=new_value,
        )
    else:
        cfg = SystemConfig(
            config_key="public_form_fields",
            config_value=new_value,
            description="Public form field visibility, required state, and label configuration",
            updated_by=current_user.id,
        )
        db.add(cfg)
    await db.commit()
    return body


@router.get("/form-links")
async def list_form_links(current_user: SuperAdmin, db: DB) -> list[dict]:
    """List all shareable form links."""
    from app.models.masters import FormLink
    result = await db.execute(select(FormLink).order_by(FormLink.created_at))
    links = list(result.scalars().all())
    return [
        {
            "id": str(link.id),
            "slug": link.slug,
            "label": link.label,
            "is_active": link.is_active,
            "created_at": link.created_at.isoformat(),
        }
        for link in links
    ]


@router.post("/form-links")
async def create_form_link(body: dict, current_user: SuperAdmin, db: DB) -> dict:
    """Create a new shareable form link. Super Admin only."""
    import re
    from fastapi import HTTPException
    from app.models.masters import FormLink
    slug = str(body.get("slug", "")).strip().lower()
    label = str(body.get("label", "")).strip()
    if not slug or not label:
        raise HTTPException(status_code=422, detail="slug and label are required")
    if not re.match(r'^[a-z0-9][a-z0-9-]{1,48}[a-z0-9]$', slug):
        raise HTTPException(status_code=422, detail="slug must be 3–50 lowercase alphanumeric chars and hyphens")
    link = FormLink(slug=slug, label=label, created_by=current_user.id)
    db.add(link)
    await db.commit()
    await db.refresh(link)
    return {"id": str(link.id), "slug": link.slug, "label": link.label, "is_active": link.is_active, "created_at": link.created_at.isoformat()}


@router.patch("/form-links/{link_id}")
async def toggle_form_link(link_id: UUID, body: dict, current_user: SuperAdmin, db: DB) -> dict:
    """Toggle is_active on a form link."""
    from app.models.masters import FormLink
    result = await db.execute(select(FormLink).where(FormLink.id == link_id))
    link = result.scalar_one_or_none()
    if not link:
        raise NotFoundError("Form link not found")
    link.is_active = bool(body.get("is_active", not link.is_active))
    await db.commit()
    return {"id": str(link.id), "slug": link.slug, "label": link.label, "is_active": link.is_active}


@router.delete("/form-links/{link_id}", response_model=MessageResponse)
async def delete_form_link(link_id: UUID, current_user: SuperAdmin, db: DB) -> MessageResponse:
    """Delete a form link."""
    from app.models.masters import FormLink
    result = await db.execute(select(FormLink).where(FormLink.id == link_id))
    link = result.scalar_one_or_none()
    if not link:
        raise NotFoundError("Form link not found")
    await db.delete(link)
    await db.commit()
    return MessageResponse(message="Form link deleted.")
