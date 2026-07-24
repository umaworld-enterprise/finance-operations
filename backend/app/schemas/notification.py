"""Schemas for notifications and push subscriptions."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.schemas.common import OrmBase


class NotificationResponse(OrmBase):
    id: UUID
    type: str
    title: str
    body: str | None
    url: str | None
    attachment_url: str | None
    deposit_request_id: UUID | None
    is_read: bool
    created_at: datetime


class NotificationListResponse(BaseModel):
    items: list[NotificationResponse]
    total: int
    unread_count: int


class MarkReadRequest(BaseModel):
    ids: list[UUID] | None = None  # None → mark all read


class PushSubscribeRequest(BaseModel):
    endpoint: str
    p256dh: str
    auth: str


class PushUnsubscribeRequest(BaseModel):
    endpoint: str
