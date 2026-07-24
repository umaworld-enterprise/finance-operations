"""User / Team Member Master service."""

import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError

log = logging.getLogger(__name__)
from app.models.masters import User
from app.repositories.user_repo import UserRepository
from app.schemas.masters import UserCreate, UserUpdate
from app.services.audit_service import AuditService


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = UserRepository(session)
        self._audit = AuditService(session)

    async def create(self, data: UserCreate, created_by: UUID) -> User:
        existing = await self._repo.get_by_email(data.email)
        if existing:
            raise ConflictError(f"A user with email '{data.email}' already exists.")
        user = await self._repo.create(**data.model_dump())
        await self._audit.record_create("users", user.id, created_by)
        return user

    async def update(self, user_id: UUID, data: UserUpdate, updated_by: UUID) -> User:
        user = await self._get_or_404(user_id)
        changes = data.model_dump(exclude_unset=True)
        for field, new_val in changes.items():
            await self._audit.record_update(
                "users", user_id, updated_by,
                field_name=field,
                old_value=str(getattr(user, field)),
                new_value=str(new_val),
            )
        return await self._repo.update(user, **changes)

    async def list_active(self) -> list[User]:
        return await self._repo.list_active()

    async def get(self, user_id: UUID) -> User:
        return await self._get_or_404(user_id)

    async def record_login(
        self,
        user_id: UUID,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        user = await self._repo.get_by_id(user_id)
        if not user:
            log.warning("record_login: user %s not found in DB — skipping", user_id)
            return
        await self._repo.update(user, last_login_at=datetime.now(timezone.utc))
        await self._audit.record_login(
            entity_id=user_id,
            changed_by=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    async def _get_or_404(self, user_id: UUID) -> User:
        user = await self._repo.get_by_id(user_id)
        if not user:
            raise NotFoundError(f"User {user_id} not found.")
        return user
