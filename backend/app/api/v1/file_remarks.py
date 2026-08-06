"""File Remarks endpoints (CIO batch 2, Aug 2026).

Merchandisers raise structured remarks against their own files — including
paid & processed (locked) ones — for invoice-number changes and invoice
splits; Accounts get notified, act manually, and resolve with an optional
response. Bypasses the Adjust Invoices module for the time being; moves no
money.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.dependencies import CurrentUser, get_current_user
from app.schemas.file_remark import FileRemarkCreate, FileRemarkResolve, FileRemarkResponse
from app.services.file_remark_service import FileRemarkService
from app.services.notification_service import (
    notify_file_remark_raised,
    notify_file_remark_resolved,
)

router = APIRouter(prefix="/file-remarks", tags=["file-remarks"])

DB = Annotated[AsyncSession, Depends(get_db_session)]
User = Annotated[CurrentUser, Depends(get_current_user)]


def _ip(req: Request) -> str | None:
    forwarded = req.headers.get("x-forwarded-for")
    return forwarded.split(",")[0].strip() if forwarded else (req.client.host if req.client else None)


@router.get("", response_model=list[FileRemarkResponse])
async def list_file_remarks(
    current_user: User,
    db: DB,
    status: str | None = Query(None, pattern="^(open|resolved)$"),
    request_id: UUID | None = Query(None),
    limit: int = Query(200, ge=1, le=500),
) -> list[FileRemarkResponse]:
    """Merchandisers see their own remarks; Accounts/Finance/Super see all."""
    return await FileRemarkService(db).list(
        current_user.id, current_user.role,
        status=status, deposit_request_id=request_id, limit=limit,
    )


@router.post("", response_model=FileRemarkResponse, status_code=201)
async def create_file_remark(
    data: FileRemarkCreate,
    current_user: User,
    request: Request,
    db: DB,
    background_tasks: BackgroundTasks,
) -> FileRemarkResponse:
    """Raise a file remark — merchandisers on their own requests (any status,
    locked files included). Accounts Team is notified."""
    svc = FileRemarkService(db)
    remark = await svc.create(
        data, current_user.id, current_user.role,
        ip_address=_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    background_tasks.add_task(notify_file_remark_raised, remark.id)
    results = await svc.list(
        current_user.id, current_user.role, deposit_request_id=remark.deposit_request_id
    )
    return next(r for r in results if r.id == remark.id)


@router.post("/{remark_id}/resolve", response_model=FileRemarkResponse)
async def resolve_file_remark(
    remark_id: UUID,
    body: FileRemarkResolve,
    current_user: User,
    request: Request,
    db: DB,
    background_tasks: BackgroundTasks,
) -> FileRemarkResponse:
    """Accounts resolve a remark; the raiser is notified (response note
    included when given)."""
    svc = FileRemarkService(db)
    remark = await svc.resolve(
        remark_id, current_user.id, current_user.role, body.response_note,
        ip_address=_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    background_tasks.add_task(notify_file_remark_resolved, remark.id)
    results = await svc.list(
        current_user.id, current_user.role, deposit_request_id=remark.deposit_request_id
    )
    return next(r for r in results if r.id == remark.id)
