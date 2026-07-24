"""Deposit request endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.dependencies import CurrentUser, get_current_user
from app.core.exceptions import AppError
from app.models.enums import RequestStatus
from app.schemas.deposit_request import (
    DepositRequestCreate,
    DepositRequestDetailResponse,
    DepositRequestResponse,
    DepositRequestUpdate,
    StatusChangeRequest,
)
from app.schemas.common import MessageResponse
from app.services.deposit_request_service import DepositRequestService

router = APIRouter(prefix="/requests", tags=["deposit-requests"])

DB = Annotated[AsyncSession, Depends(get_db_session)]
User = Annotated[CurrentUser, Depends(get_current_user)]


@router.get("", response_model=list[DepositRequestResponse])
async def list_requests(
    current_user: User,
    db: DB,
    status_filter: RequestStatus | None = Query(None, alias="status"),
    supplier_id: UUID | None = None,
    customer_id: UUID | None = None,
    vertical_id: UUID | None = None,
    created_by: UUID | None = None,
) -> list[DepositRequestResponse]:
    svc = DepositRequestService(db)
    requests = await svc.list_for_role(
        current_user.role,
        current_user.id,
        status=status_filter,
        supplier_id=supplier_id,
        customer_id=customer_id,
        vertical_id=vertical_id,
        created_by=created_by,
    )
    return [DepositRequestResponse.model_validate(r) for r in requests]


@router.post("", response_model=DepositRequestResponse, status_code=status.HTTP_201_CREATED)
async def create_request(
    data: DepositRequestCreate,
    current_user: User,
    db: DB,
) -> DepositRequestResponse:
    svc = DepositRequestService(db)
    request = await svc.create(data, current_user.id)
    return DepositRequestResponse.model_validate(request)


@router.get("/pending-payment-queue", response_model=list[DepositRequestResponse])
async def pending_payment_queue(
    current_user: User,
    db: DB,
) -> list[DepositRequestResponse]:
    """Oldest-first queue for Accounts Team dashboard."""
    svc = DepositRequestService(db)
    requests = await svc.get_pending_payment_queue()
    return [DepositRequestResponse.model_validate(r) for r in requests]


@router.get("/{request_id}", response_model=DepositRequestDetailResponse)
async def get_request(
    request_id: UUID,
    current_user: User,
    db: DB,
) -> DepositRequestDetailResponse:
    svc = DepositRequestService(db)
    request = await svc.get_detail(request_id)
    return DepositRequestDetailResponse.model_validate(request)


@router.patch("/{request_id}", response_model=DepositRequestResponse)
async def update_request(
    request_id: UUID,
    data: DepositRequestUpdate,
    current_user: User,
    db: DB,
) -> DepositRequestResponse:
    svc = DepositRequestService(db)
    request = await svc.update(request_id, data, current_user.id, current_user.role)
    return DepositRequestResponse.model_validate(request)


@router.delete("/{request_id}", response_model=MessageResponse)
async def delete_request(
    request_id: UUID,
    current_user: User,
    db: DB,
) -> MessageResponse:
    svc = DepositRequestService(db)
    await svc.soft_delete(request_id, current_user.id, current_user.role)
    return MessageResponse(message="Request deleted.")


@router.post("/{request_id}/hold", response_model=DepositRequestResponse)
async def hold_request(
    request_id: UUID,
    body: StatusChangeRequest,
    current_user: User,
    db: DB,
) -> DepositRequestResponse:
    from app.models.enums import RequestStatus, UserRole
    svc = DepositRequestService(db)
    target = (
        RequestStatus.HOLD_BY_MERCHANDISER
        if current_user.role in {UserRole.MERCHANDISER}
        else RequestStatus.HOLD_BY_ACCOUNTS
    )
    request = await svc.transition_status(
        request_id, target, current_user.id, current_user.role, body.remarks
    )
    return DepositRequestResponse.model_validate(request)


@router.post("/{request_id}/resume", response_model=DepositRequestResponse)
async def resume_request(
    request_id: UUID,
    body: StatusChangeRequest,
    current_user: User,
    db: DB,
) -> DepositRequestResponse:
    svc = DepositRequestService(db)
    request = await svc.transition_status(
        request_id,
        RequestStatus.PENDING_PAYMENT,
        current_user.id,
        current_user.role,
        body.remarks,
    )
    return DepositRequestResponse.model_validate(request)


@router.post("/{request_id}/cancel", response_model=DepositRequestResponse)
async def cancel_request(
    request_id: UUID,
    body: StatusChangeRequest,
    current_user: User,
    db: DB,
) -> DepositRequestResponse:
    from app.models.enums import UserRole
    svc = DepositRequestService(db)
    target = (
        RequestStatus.CANCELLED_BY_MERCHANDISER
        if current_user.role == UserRole.MERCHANDISER
        else RequestStatus.CANCELLED_BY_ACCOUNTS
    )
    request = await svc.transition_status(
        request_id, target, current_user.id, current_user.role, body.remarks
    )
    return DepositRequestResponse.model_validate(request)


@router.post("/{request_id}/reopen", response_model=DepositRequestResponse)
async def reopen_request(
    request_id: UUID,
    body: StatusChangeRequest,
    current_user: User,
    db: DB,
) -> DepositRequestResponse:
    svc = DepositRequestService(db)
    request = await svc.transition_status(
        request_id,
        RequestStatus.REOPENED,
        current_user.id,
        current_user.role,
        body.remarks,
    )
    return DepositRequestResponse.model_validate(request)
