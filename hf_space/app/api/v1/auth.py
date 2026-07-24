"""Auth endpoints — profile and login recording."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.dependencies import CurrentUser, get_current_user
from app.schemas.auth import CurrentUserResponse
from app.services.user_service import UserService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=CurrentUserResponse)
async def get_me(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> CurrentUserResponse:
    """Return the current authenticated user's profile."""
    svc = UserService(db)
    await svc.record_login(current_user.id)
    return CurrentUserResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        role=current_user.role,
        is_active=True,
    )
