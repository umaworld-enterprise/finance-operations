"""Shared schema primitives."""

from datetime import datetime
from typing import Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class OrmBase(BaseModel):
    """Base for all ORM-backed response schemas."""
    model_config = ConfigDict(from_attributes=True)


class PaginatedResponse(BaseModel, Generic[T]):
    total: int
    page: int
    page_size: int
    items: list[T]


class MessageResponse(BaseModel):
    message: str


class ErrorResponse(BaseModel):
    error_code: str
    message: str
    detail: str | None = None
