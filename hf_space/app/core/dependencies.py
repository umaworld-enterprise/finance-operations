"""FastAPI dependency injection: current user, RBAC guards."""

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.exceptions import AuthenticationError, AuthorizationError
from app.core.security import decode_supabase_token
from app.models.enums import UserRole
from app.repositories.user_repo import UserRepository

# ── Token extraction ──────────────────────────────────────────────────────────


async def get_token_payload(
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    """Extract and validate Bearer token from Authorization header."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.split(" ", 1)[1]
    try:
        return decode_supabase_token(token)
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=exc.message,
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


# ── Current user ──────────────────────────────────────────────────────────────


class CurrentUser:
    """Resolved application user attached to each request."""

    def __init__(
        self,
        id: UUID,
        email: str,
        full_name: str,
        role: UserRole,
        supabase_uid: UUID,
    ) -> None:
        self.id = id
        self.email = email
        self.full_name = full_name
        self.role = role
        self.supabase_uid = supabase_uid

    def has_role(self, *roles: UserRole) -> bool:
        return self.role in roles

    def is_super_admin(self) -> bool:
        return self.role == UserRole.SUPER_ADMIN


async def get_current_user(
    payload: Annotated[dict, Depends(get_token_payload)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> CurrentUser:
    """Resolve Supabase JWT → application user record."""
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
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User not registered in the system. Contact your administrator.",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been deactivated.",
        )

    return CurrentUser(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        supabase_uid=user.supabase_uid,
    )


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
