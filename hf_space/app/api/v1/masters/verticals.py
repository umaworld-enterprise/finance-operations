"""Vertical / Category master endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
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


@router.get("", response_model=list[VerticalResponse])
async def list_verticals(db: DB, _: User) -> list[VerticalResponse]:
    repo = BaseRepository(db, Vertical)
    verticals = await repo.list_all(is_active=True)
    return [VerticalResponse.model_validate(v) for v in verticals]


@router.post("", response_model=VerticalResponse, status_code=status.HTTP_201_CREATED)
async def create_vertical(data: VerticalCreate, current_user: FinanceAdmin, db: DB) -> VerticalResponse:
    repo = BaseRepository(db, Vertical)
    vertical = await repo.create(**data.model_dump())
    await AuditService(db).record_create("verticals", vertical.id, current_user.id)
    return VerticalResponse.model_validate(vertical)


@router.patch("/{vertical_id}", response_model=VerticalResponse)
async def update_vertical(
    vertical_id: UUID, data: VerticalUpdate, current_user: FinanceAdmin, db: DB
) -> VerticalResponse:
    repo = BaseRepository(db, Vertical)
    vertical = await repo.get_by_id(vertical_id)
    if not vertical:
        raise NotFoundError(f"Vertical {vertical_id} not found.")
    vertical = await repo.update(vertical, **data.model_dump(exclude_unset=True))
    return VerticalResponse.model_validate(vertical)
