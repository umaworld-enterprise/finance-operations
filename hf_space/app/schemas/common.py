"""Shared schema primitives."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class OrmBase(BaseModel):
    """Base for all ORM-backed response schemas."""
    model_config = ConfigDict(from_attributes=True)


class PaginatedResponse(OrmBase):
    total: int
    offset: int
    limit: int
    items: list


class MessageResponse(BaseModel):
    message: str


class ErrorResponse(BaseModel):
    error_code: str
    message: str
    detail: str | None = None
