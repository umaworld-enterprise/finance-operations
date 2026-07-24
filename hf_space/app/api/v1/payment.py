"""Payment endpoints — Accounts-owned."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.dependencies import CurrentUser, get_current_user
from app.schemas.common import MessageResponse
from app.schemas.payment import PaymentCreate, PaymentResponse, PaymentUpdate
from app.services.payment_service import PaymentService

router = APIRouter(prefix="/requests/{request_id}/payment", tags=["payment"])

DB = Annotated[AsyncSession, Depends(get_db_session)]
User = Annotated[CurrentUser, Depends(get_current_user)]


@router.get("", response_model=PaymentResponse | None)
async def get_payment(
    request_id: UUID,
    current_user: User,
    db: DB,
) -> PaymentResponse | None:
    svc = PaymentService(db)
    payment = await svc.get_by_request_id(request_id)
    if not payment:
        return None
    return PaymentResponse.model_validate(payment)


@router.post("", response_model=PaymentResponse)
async def create_payment(
    request_id: UUID,
    data: PaymentCreate,
    current_user: User,
    db: DB,
) -> PaymentResponse:
    svc = PaymentService(db)
    payment = await svc.create_or_update(request_id, data, current_user.id, current_user.role)
    return PaymentResponse.model_validate(payment)


@router.patch("", response_model=PaymentResponse)
async def update_payment(
    request_id: UUID,
    data: PaymentUpdate,
    current_user: User,
    db: DB,
) -> PaymentResponse:
    svc = PaymentService(db)
    payment = await svc.create_or_update(request_id, data, current_user.id, current_user.role)
    return PaymentResponse.model_validate(payment)


@router.post("/process", response_model=MessageResponse)
async def process_payment(
    request_id: UUID,
    current_user: User,
    db: DB,
) -> MessageResponse:
    """Mark payment processed — locks the deposit request."""
    svc = PaymentService(db)
    await svc.process_payment(request_id, current_user.id, current_user.role)
    return MessageResponse(message="Payment processed. Record is now locked.")
