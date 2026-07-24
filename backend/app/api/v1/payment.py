"""Payment endpoints — Accounts-owned."""

import asyncio
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.snapshot_job import seed_snapshot_for_request
from app.core.database import get_db_session
from app.core.dependencies import CurrentUser, get_current_user
from app.core.exceptions import AuthorizationError, ValidationError
from app.integrations.google_drive.drive_service import (
    build_tt_copy_filename,
    upload_tt_copy_to_drive,
    validate_tt_copy,
)
from app.models.enums import UserRole
from app.schemas.common import MessageResponse
from app.schemas.payment import PaymentCreate, PaymentResponse, PaymentUpdate, ShipDateUpdate
from app.services.notification_service import (
    notify_payment_processed_if_ready,
    notify_tt_copy_uploaded,
)
from app.services.payment_service import PaymentService

router = APIRouter(prefix="/requests/{request_id}/payment", tags=["payment"])

DB = Annotated[AsyncSession, Depends(get_db_session)]
User = Annotated[CurrentUser, Depends(get_current_user)]


def _ip(req: Request) -> str | None:
    forwarded = req.headers.get("x-forwarded-for")
    return forwarded.split(",")[0].strip() if forwarded else (req.client.host if req.client else None)


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


# Kept in sync with PaymentService, which only permits these two roles —
# FINANCE_ADMIN passing the endpoint guard would still 403 in the service.
_PAYMENT_WRITE_ROLES = {UserRole.SUPER_ADMIN, UserRole.ACCOUNTS_TEAM}


@router.post("", response_model=PaymentResponse)
async def create_payment(
    request_id: UUID,
    data: PaymentCreate,
    current_user: User,
    request: Request,
    db: DB,
    background_tasks: BackgroundTasks,
) -> PaymentResponse:
    if current_user.role not in _PAYMENT_WRITE_ROLES:
        raise AuthorizationError("Only Finance Admin or Accounts Team can record payments.")
    svc = PaymentService(db)
    payment = await svc.create_or_update(
        request_id, data, current_user.id, current_user.role,
        ip_address=_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    background_tasks.add_task(seed_snapshot_for_request, request_id)
    return PaymentResponse.model_validate(payment)


@router.patch("", response_model=PaymentResponse)
async def update_payment(
    request_id: UUID,
    data: PaymentUpdate,
    current_user: User,
    request: Request,
    db: DB,
    background_tasks: BackgroundTasks,
) -> PaymentResponse:
    if current_user.role not in _PAYMENT_WRITE_ROLES:
        raise AuthorizationError("Only Finance Admin or Accounts Team can update payments.")
    svc = PaymentService(db)
    payment = await svc.create_or_update(
        request_id, data, current_user.id, current_user.role,
        ip_address=_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    background_tasks.add_task(seed_snapshot_for_request, request_id)
    return PaymentResponse.model_validate(payment)


@router.post("/process", response_model=MessageResponse)
async def process_payment(
    request_id: UUID,
    current_user: User,
    request: Request,
    db: DB,
    background_tasks: BackgroundTasks,
) -> MessageResponse:
    """Mark payment processed — locks the deposit request."""
    svc = PaymentService(db)
    await svc.process_payment(
        request_id, current_user.id, current_user.role,
        ip_address=_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    background_tasks.add_task(seed_snapshot_for_request, request_id)
    # Notifies immediately only if the TT copy was uploaded before processing;
    # otherwise the TT upload (or the fallback job) triggers the notification.
    background_tasks.add_task(notify_payment_processed_if_ready, request_id)
    return MessageResponse(message="Payment processed. Record is now locked.")


# Ship date is recordable after lock, so it gets its own role set — wider than
# _PAYMENT_WRITE_ROLES but limited to this single field (see set_ship_date).
_SHIP_DATE_ROLES = {UserRole.SUPER_ADMIN, UserRole.FINANCE_ADMIN, UserRole.ACCOUNTS_TEAM}


@router.post("/ship-date", response_model=PaymentResponse)
async def set_ship_date(
    request_id: UUID,
    data: ShipDateUpdate,
    current_user: User,
    request: Request,
    db: DB,
    background_tasks: BackgroundTasks,
) -> PaymentResponse:
    """Record the final ship date — stops Cost of Fund accrual.

    Works on locked (processed) records — payment is processed and locked long
    before the goods ship, so this is the designed post-lock action.
    """
    if current_user.role not in _SHIP_DATE_ROLES:
        raise AuthorizationError(
            "Only Super Admin, Finance Admin or Accounts Team can record the ship date."
        )
    svc = PaymentService(db)
    payment = await svc.set_ship_date(
        request_id, data.ship_date, current_user.id, current_user.role,
        ip_address=_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    background_tasks.add_task(seed_snapshot_for_request, request_id)
    return PaymentResponse.model_validate(payment)


@router.post("/tt-copy", response_model=PaymentResponse)
async def upload_tt_copy(
    request_id: UUID,
    file: UploadFile,
    current_user: User,
    request: Request,
    db: DB,
    background_tasks: BackgroundTasks,
) -> PaymentResponse:
    """Upload the bank's TT copy to Google Drive and attach the link.

    Works on locked (processed) records — the flow is process, then upload.
    """
    if current_user.role not in _PAYMENT_WRITE_ROLES:
        raise AuthorizationError("Only Finance Admin or Accounts Team can upload the TT copy.")

    content = await file.read()
    error = validate_tt_copy(file.content_type, len(content))
    if error:
        raise ValidationError(error)

    from app.repositories.deposit_request_repo import DepositRequestRepository
    from app.core.exceptions import NotFoundError
    deposit_request = await DepositRequestRepository(db).get_for_validation(request_id)
    if not deposit_request:
        raise NotFoundError(f"Request {request_id} not found.")

    filename = build_tt_copy_filename(deposit_request.request_number, file.content_type)
    file_id, link = await asyncio.to_thread(
        upload_tt_copy_to_drive, content, filename, file.content_type
    )

    svc = PaymentService(db)
    payment = await svc.attach_tt_copy(
        request_id,
        tt_copy_url=link,
        tt_copy_file_id=file_id,
        tt_copy_filename=filename,
        user_id=current_user.id,
        role=current_user.role,
        ip_address=_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    background_tasks.add_task(notify_tt_copy_uploaded, request_id)
    return PaymentResponse.model_validate(payment)
