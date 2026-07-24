"""Google Form webhook endpoint."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.security import verify_webhook_signature
from app.integrations.google_form.handler import handle_form_submission
from app.schemas.common import MessageResponse

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

DB = Annotated[AsyncSession, Depends(get_db_session)]


@router.post("/google-form", response_model=MessageResponse)
async def google_form_webhook(
    request: Request,
    db: DB,
    x_signature: Annotated[str | None, Header()] = None,
) -> MessageResponse:
    """
    Receives Google Form submissions from Google Apps Script.

    Authentication: HMAC-SHA256 signature in X-Signature header.
    Payload: JSON with response_id, respondent_email, and items array.
    """
    body = await request.body()

    if not x_signature:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Signature header.",
        )
    if not verify_webhook_signature(body, x_signature):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature.",
        )

    payload = await request.json()
    result = await handle_form_submission(payload, db)

    if result == "duplicate":
        return MessageResponse(message="Duplicate submission — ignored.")
    return MessageResponse(message=f"Request created: {result}")
