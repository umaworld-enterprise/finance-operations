"""Auth endpoints — profile and login recording."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db_session
from app.core.dependencies import CurrentUser, get_current_user
from app.core.rate_limit import limiter
from app.schemas.auth import CurrentUserResponse, PreferencesUpdate, ProfileUpdate
from app.services.user_service import UserService

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


def _ip(req: Request) -> str | None:
    forwarded = req.headers.get("x-forwarded-for")
    return forwarded.split(",")[0].strip() if forwarded else (req.client.host if req.client else None)


@router.get("/me", response_model=CurrentUserResponse)
@limiter.limit(settings.rate_limit_auth_default)
async def get_me(
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> CurrentUserResponse:
    """Return the current authenticated user's profile."""
    svc = UserService(db)
    await svc.record_login(
        current_user.id,
        ip_address=_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return CurrentUserResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        role=current_user.role,
        is_active=True,
        onboarding_completed=current_user.onboarding_completed,
        secondary_email=current_user.secondary_email,
        department=current_user.department,
        font_size=current_user.font_size,
    )


@router.patch("/preferences", response_model=CurrentUserResponse)
@limiter.limit(settings.rate_limit_auth_default)
async def update_preferences(
    request: Request,
    data: PreferencesUpdate,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> CurrentUserResponse:
    """Update display preferences — unlike /profile, touches nothing else."""
    from app.repositories.user_repo import UserRepository
    repo = UserRepository(db)
    user = await repo.get_by_id(current_user.id)
    if user is None:
        from app.core.exceptions import NotFoundError
        raise NotFoundError("User not found")
    user.font_size = data.font_size
    await db.commit()
    await db.refresh(user)
    return CurrentUserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        onboarding_completed=user.onboarding_completed,
        secondary_email=user.secondary_email,
        department=user.department,
        font_size=user.font_size,
    )


@router.patch("/profile", response_model=CurrentUserResponse)
@limiter.limit(settings.rate_limit_auth_default)
async def complete_profile(
    request: Request,
    data: ProfileUpdate,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> CurrentUserResponse:
    """Complete onboarding profile — sets full_name, secondary_email, department."""
    from app.repositories.user_repo import UserRepository
    repo = UserRepository(db)
    user = await repo.get_by_id(current_user.id)
    if user is None:
        from app.core.exceptions import NotFoundError
        raise NotFoundError("User not found")
    user.full_name = data.full_name.strip()
    user.secondary_email = data.secondary_email.strip() if data.secondary_email else None
    user.department = data.department.strip()
    user.onboarding_completed = True
    await db.commit()
    await db.refresh(user)
    return CurrentUserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        onboarding_completed=user.onboarding_completed,
        secondary_email=user.secondary_email,
        department=user.department,
        font_size=user.font_size,
    )
