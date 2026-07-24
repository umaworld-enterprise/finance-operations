"""Notification endpoints — bell feed, mark-read, push subscriptions."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.dependencies import CurrentUser, get_current_user
from app.repositories.notification_repo import (
    NotificationRepository,
    PushSubscriptionRepository,
)
from app.schemas.common import MessageResponse
from app.schemas.notification import (
    MarkReadRequest,
    NotificationListResponse,
    NotificationResponse,
    PushSubscribeRequest,
    PushUnsubscribeRequest,
)

router = APIRouter(prefix="/notifications", tags=["notifications"])

DB = Annotated[AsyncSession, Depends(get_db_session)]
User = Annotated[CurrentUser, Depends(get_current_user)]


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    current_user: User,
    db: DB,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> NotificationListResponse:
    repo = NotificationRepository(db)
    items, total, unread = await repo.list_for_user(current_user.id, page, page_size)
    return NotificationListResponse(
        items=[NotificationResponse.model_validate(n) for n in items],
        total=total,
        unread_count=unread,
    )


@router.post("/read", response_model=MessageResponse)
async def mark_read(
    data: MarkReadRequest,
    current_user: User,
    db: DB,
) -> MessageResponse:
    repo = NotificationRepository(db)
    count = await repo.mark_read(current_user.id, data.ids)
    await db.commit()
    return MessageResponse(message=f"{count} notification(s) marked as read.")


@router.post("/push/subscribe", response_model=MessageResponse)
async def push_subscribe(
    data: PushSubscribeRequest,
    current_user: User,
    request: Request,
    db: DB,
) -> MessageResponse:
    repo = PushSubscriptionRepository(db)
    await repo.upsert(
        user_id=current_user.id,
        endpoint=data.endpoint,
        p256dh=data.p256dh,
        auth=data.auth,
        user_agent=(request.headers.get("user-agent") or "")[:500] or None,
    )
    await db.commit()
    return MessageResponse(message="Push subscription saved.")


# POST (not DELETE) — DELETE with a request body is unreliable across proxies.
@router.post("/push/unsubscribe", response_model=MessageResponse)
async def push_unsubscribe(
    data: PushUnsubscribeRequest,
    current_user: User,
    db: DB,
) -> MessageResponse:
    repo = PushSubscriptionRepository(db)
    await repo.delete_by_endpoints([data.endpoint])
    await db.commit()
    return MessageResponse(message="Push subscription removed.")
