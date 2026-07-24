"""User / Team Member Master endpoints — Super Admin only."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.dependencies import CurrentUser, RequireSuperAdmin
from app.schemas.masters import UserCreate, UserResponse, UserUpdate
from app.services.user_service import UserService

router = APIRouter(prefix="/masters/users", tags=["masters-users"])

DB = Annotated[AsyncSession, Depends(get_db_session)]
SuperAdmin = Annotated[CurrentUser, RequireSuperAdmin]


@router.get("", response_model=list[UserResponse])
async def list_users(current_user: SuperAdmin, db: DB) -> list[UserResponse]:
    svc = UserService(db)
    users = await svc.list_active()
    return [UserResponse.model_validate(u) for u in users]


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(data: UserCreate, current_user: SuperAdmin, db: DB) -> UserResponse:
    svc = UserService(db)
    user = await svc.create(data, current_user.id)
    return UserResponse.model_validate(user)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: UUID, current_user: SuperAdmin, db: DB) -> UserResponse:
    svc = UserService(db)
    user = await svc.get(user_id)
    return UserResponse.model_validate(user)


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: UUID, data: UserUpdate, current_user: SuperAdmin, db: DB
) -> UserResponse:
    svc = UserService(db)
    user = await svc.update(user_id, data, current_user.id)
    return UserResponse.model_validate(user)
