"""FastAPI dependency injection: current user, RBAC guards."""

import types
from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db_session
from app.core.exceptions import AuthenticationError
from app.core.security import decode_supabase_token
from app.models.enums import UserRole
from app.repositories.user_repo import UserRepository


# ── Current user ──────────────────────────────────────────────────────────────


class CurrentUser:
    """Thin wrapper around a User-like object.

    Delegates every attribute read to the underlying object so that any new
    column added to the User ORM model is automatically available here —
    no second place to update.
    """

    def __init__(self, user: object) -> None:
        self._user = user

    @property
    def id(self) -> UUID:
        return self._user.id  # type: ignore[union-attr]

    @property
    def email(self) -> str:
        return self._user.email  # type: ignore[union-attr]

    @property
    def full_name(self) -> str:
        return self._user.full_name  # type: ignore[union-attr]

    @property
    def role(self) -> UserRole:
        return self._user.role  # type: ignore[union-attr]

    @property
    def supabase_uid(self) -> UUID:
        return self._user.supabase_uid  # type: ignore[union-attr]

    @property
    def onboarding_completed(self) -> bool:
        return self._user.onboarding_completed  # type: ignore[union-attr]

    @property
    def secondary_email(self) -> str | None:
        return self._user.secondary_email  # type: ignore[union-attr]

    @property
    def department(self) -> str | None:
        return self._user.department  # type: ignore[union-attr]

    @property
    def font_size(self) -> str:
        return self._user.font_size  # type: ignore[union-attr]

    def has_role(self, *roles: UserRole) -> bool:
        return self._user.role in roles  # type: ignore[union-attr]

    def is_super_admin(self) -> bool:
        return self._user.role == UserRole.SUPER_ADMIN  # type: ignore[union-attr]


_DEV_USER_ID = UUID("00000000-0000-0000-0000-000000000001")

_DEV_USER = CurrentUser(
    types.SimpleNamespace(
        id=_DEV_USER_ID,
        email="admin@sunshine.dev",
        full_name="Dev Admin",
        role=UserRole.SUPER_ADMIN,
        supabase_uid=UUID("00000000-0000-0000-0000-000000000002"),
        onboarding_completed=True,
        secondary_email=None,
        department=None,
        font_size="default",
    )
)


async def _get_or_create_dev_user(db: AsyncSession) -> CurrentUser:
    """Development bypass with a REAL users row.

    Audit logs, tranche payments and adjustments all carry FK references to
    users.id — an in-memory fake identity breaks every write path with a
    ForeignKeyViolation. Persist the dev admin on first use instead.
    """
    from app.models.masters import User

    user = await db.get(User, _DEV_USER_ID)
    if user is None:
        user = User(
            id=_DEV_USER_ID,
            email=_DEV_USER.email,
            full_name=_DEV_USER.full_name,
            role=UserRole.SUPER_ADMIN,
            supabase_uid=_DEV_USER.supabase_uid,
            is_active=True,
            onboarding_completed=True,
        )
        db.add(user)
        await db.flush()
    return CurrentUser(user)


async def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
    db: Annotated[AsyncSession, Depends(get_db_session)] = None,
) -> CurrentUser:
    """Resolve Supabase JWT → application user record. Bypassed in development."""
    settings = get_settings()
    if settings.app_env == "development":
        return await _get_or_create_dev_user(db)

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.split(" ", 1)[1]
    try:
        payload = decode_supabase_token(token)
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=exc.message,
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    supabase_uid_str: str | None = payload.get("sub")
    if not supabase_uid_str:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token subject")

    try:
        supabase_uid = UUID(supabase_uid_str)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token subject")

    repo = UserRepository(db)
    user = await repo.get_by_supabase_uid(supabase_uid)

    if not user:
        email = payload.get("email")
        if email:
            by_email = await repo.get_by_email(email)
            if by_email and by_email.supabase_uid is None:
                user = await repo.update(by_email, supabase_uid=supabase_uid)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User not registered in the system. Contact your administrator.",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been deactivated.",
        )

    return CurrentUser(user)


# ── RBAC guards ───────────────────────────────────────────────────────────────


def require_roles(*roles: UserRole) -> Callable:
    """Factory that returns a FastAPI dependency enforcing role membership."""

    async def guard(
        current_user: Annotated[CurrentUser, Depends(get_current_user)],
    ) -> CurrentUser:
        if not current_user.has_role(*roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required roles: {[r.value for r in roles]}",
            )
        return current_user

    return guard


# Convenience aliases
RequireAnyRole = Depends(get_current_user)  # just authenticated
RequireSuperAdmin = Depends(require_roles(UserRole.SUPER_ADMIN))
RequireFinanceAdmin = Depends(require_roles(UserRole.SUPER_ADMIN, UserRole.FINANCE_ADMIN))
RequireAccounts = Depends(require_roles(UserRole.SUPER_ADMIN, UserRole.ACCOUNTS_TEAM))
RequireMerchandiser = Depends(require_roles(UserRole.SUPER_ADMIN, UserRole.MERCHANDISER))
