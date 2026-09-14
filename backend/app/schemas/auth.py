"""Auth request/response schemas."""

from datetime import datetime
from typing import Literal
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
    onboarding_completed: bool = False
    secondary_email: str | None = None
    department: str | None = None
    font_size: str = "default"


class GoogleLoginRequest(BaseModel):
    # One-time authorization code from the Google sign-in popup
    code: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int  # seconds
    user: CurrentUserResponse


class ProfileUpdate(BaseModel):
    full_name: str
    secondary_email: str | None = None
    department: str


class PreferencesUpdate(BaseModel):
    font_size: Literal["default", "large", "xlarge"]
