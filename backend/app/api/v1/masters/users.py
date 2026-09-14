"""User / Team Member Master endpoints — Super Admin only."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.dependencies import CurrentUser, RequireSuperAdmin, get_current_user
from app.schemas.masters import UserCreate, UserResponse, UserUpdate
from app.services.user_service import UserService

router = APIRouter(prefix="/masters/users", tags=["masters-users"])

DB = Annotated[AsyncSession, Depends(get_db_session)]
SuperAdmin = Annotated[CurrentUser, RequireSuperAdmin]
AnyUser = Annotated[CurrentUser, Depends(get_current_user)]


@router.get("/merchandisers")
async def list_merchandiser_options(current_user: AnyUser, db: DB) -> list[dict]:
    """Minimal merchandiser list for filter dropdowns (4 Sep 2026 dynamic
    filter module) — any authenticated role; id + name only, active
    merchandiser-role users."""
    from sqlalchemy import select

    from app.models.enums import UserRole
    from app.models.masters import User as UserModel

    rows = (
        await db.execute(
            select(UserModel.id, UserModel.full_name)
            .where(UserModel.role == UserRole.MERCHANDISER, UserModel.is_active == True)  # noqa: E712
            .order_by(UserModel.full_name)
        )
    ).all()
    return [{"id": str(r.id), "full_name": r.full_name} for r in rows]


@router.get("", response_model=list[UserResponse])
async def list_users(current_user: SuperAdmin, db: DB) -> list[UserResponse]:
    """Active AND deactivated (19 Aug 2026 fix) — the admin page shows
    inactive users greyed with an Activate toggle; deactivation previously
    made a user unreachable (hidden here, email still reserved)."""
    svc = UserService(db)
    users = await svc.list_all()
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
