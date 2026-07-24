"""Auth request/response schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr

from app.models.enums import UserRole
from app.schemas.common import OrmBase


class CurrentUserResponse(OrmBase):
    id: UUID
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    last_login_at: datetime | None = None
