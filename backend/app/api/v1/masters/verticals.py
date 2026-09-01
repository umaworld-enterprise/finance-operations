"""Vertical / Category master endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.dependencies import CurrentUser, RequireFinanceAdmin, get_current_user
from app.core.exceptions import NotFoundError
from app.models.masters import Vertical
from app.repositories.base import BaseRepository
from app.schemas.masters import VerticalCreate, VerticalResponse, VerticalUpdate
from app.services.audit_service import AuditService

router = APIRouter(prefix="/masters/verticals", tags=["masters-verticals"])

DB = Annotated[AsyncSession, Depends(get_db_session)]
User = Annotated[CurrentUser, Depends(get_current_user)]
FinanceAdmin = Annotated[CurrentUser, RequireFinanceAdmin]


def _ip(req: Request) -> str | None:
    forwarded = req.headers.get("x-forwarded-for")
    return forwarded.split(",")[0].strip() if forwarded else (req.client.host if req.client else None)


@router.get("", response_model=list[VerticalResponse])
async def list_verticals(db: DB, _: User) -> list[VerticalResponse]:
    repo = BaseRepository(db, Vertical)
    verticals = await repo.list_all(is_active=True)
    return [VerticalResponse.model_validate(v) for v in verticals]


@router.get("/all", response_model=list[VerticalResponse])
async def list_all_verticals(db: DB, _: FinanceAdmin) -> list[VerticalResponse]:
    """Admin endpoint (19 Aug 2026 masters page) — active AND inactive."""
    from sqlalchemy import select

    result = await db.execute(select(Vertical).order_by(Vertical.name))
    return [VerticalResponse.model_validate(v) for v in result.scalars().all()]


@router.post("", response_model=VerticalResponse, status_code=status.HTTP_201_CREATED)
async def create_vertical(data: VerticalCreate, current_user: FinanceAdmin, db: DB, request: Request) -> VerticalResponse:
    repo = BaseRepository(db, Vertical)
    vertical = await repo.create(**data.model_dump())
    await AuditService(db).record_create(
        "verticals", vertical.id, current_user.id,
        ip_address=_ip(request),
        user_agent=request.headers.get("user-agent"),
        new_value=data.name,
    )
    return VerticalResponse.model_validate(vertical)


@router.patch("/{vertical_id}", response_model=VerticalResponse)
async def update_vertical(
    vertical_id: UUID, data: VerticalUpdate, current_user: FinanceAdmin, db: DB, request: Request
) -> VerticalResponse:
    repo = BaseRepository(db, Vertical)
    vertical = await repo.get_by_id(vertical_id)
    if not vertical:
        raise NotFoundError(f"Vertical {vertical_id} not found.")

    audit = AuditService(db)
    ip = _ip(request)
    ua = request.headers.get("user-agent")
    update_data = data.model_dump(exclude_unset=True)

    for field, new_val in update_data.items():
        await audit.record_update(
            "verticals", vertical.id, current_user.id,
            field_name=field,
            old_value=str(getattr(vertical, field, "")),
            new_value=str(new_val),
            ip_address=ip,
            user_agent=ua,
        )

    vertical = await repo.update(vertical, **update_data)
    return VerticalResponse.model_validate(vertical)
