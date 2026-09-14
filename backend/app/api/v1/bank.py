"""Banking module endpoints (Aug 2026) — super admin and accounts team.

Upload a bank statement PDF; pages are rendered to images and extracted via
the configured AI vision provider in the background. The dashboard reads the
stored statements, transactions and daily balances.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db_session
from app.core.dependencies import CurrentUser, RequireAccounts
from app.core.exceptions import NotFoundError, ValidationError
from app.models.bank_statement import BankStatement
from app.schemas.bank_statement import (
    BankStatementDetailResponse,
    BankStatementResponse,
)
from app.schemas.common import MessageResponse
from app.services.audit_service import AuditService
from app.services.bank_statement_service import MAX_PAGES, extract_statement

router = APIRouter(prefix="/bank/statements", tags=["bank"])

DB = Annotated[AsyncSession, Depends(get_db_session)]
BankUser = Annotated[CurrentUser, RequireAccounts]

_MAX_PDF_BYTES = 15 * 1024 * 1024


def _ip(req: Request) -> str | None:
    forwarded = req.headers.get("x-forwarded-for")
    return forwarded.split(",")[0].strip() if forwarded else (req.client.host if req.client else None)


@router.get("", response_model=list[BankStatementResponse])
async def list_statements(current_user: BankUser, db: DB) -> list[BankStatementResponse]:
    result = await db.execute(
        select(BankStatement).order_by(
            BankStatement.period_start.desc().nulls_last(),
            BankStatement.created_at.desc(),
        )
    )
    return [BankStatementResponse.model_validate(s) for s in result.scalars().all()]


@router.post("", response_model=BankStatementResponse, status_code=201)
async def upload_statement(
    file: UploadFile,
    current_user: BankUser,
    request: Request,
    db: DB,
    background_tasks: BackgroundTasks,
) -> BankStatementResponse:
    """Accepts a statement PDF, answers immediately with the row in
    `processing`, and extracts in the background (poll the list/detail)."""
    if (file.content_type or "") not in ("application/pdf", "application/x-pdf"):
        raise ValidationError("Only PDF bank statements can be uploaded.")
    content = await file.read()
    if len(content) > _MAX_PDF_BYTES:
        raise ValidationError("The PDF must be 15 MB or smaller.")
    if not content.startswith(b"%PDF"):
        raise ValidationError("The file does not look like a valid PDF.")

    statement = BankStatement(
        bank_name="Bank statement",  # replaced by the extracted header
        original_filename=(file.filename or "statement.pdf")[:300],
        uploaded_by=current_user.id,
    )
    db.add(statement)
    await db.flush()
    await AuditService(db).record_create(
        "bank_statements", statement.id, current_user.id,
        new_value=f"uploaded {statement.original_filename} (max {MAX_PAGES} pages)",
        ip_address=_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    await db.commit()
    background_tasks.add_task(extract_statement, statement.id, content)
    return BankStatementResponse.model_validate(statement)


@router.get("/{statement_id}", response_model=BankStatementDetailResponse)
async def get_statement(
    statement_id: UUID, current_user: BankUser, db: DB
) -> BankStatementDetailResponse:
    result = await db.execute(
        select(BankStatement)
        .where(BankStatement.id == statement_id)
        .options(
            selectinload(BankStatement.transactions),
            selectinload(BankStatement.daily_balances),
        )
    )
    statement = result.scalar_one_or_none()
    if statement is None:
        raise NotFoundError("Bank statement not found.")
    return BankStatementDetailResponse.model_validate(statement)


@router.delete("/{statement_id}", response_model=MessageResponse)
async def delete_statement(
    statement_id: UUID,
    current_user: BankUser,
    request: Request,
    db: DB,
) -> MessageResponse:
    """Remove a statement and its extracted rows (e.g. to re-upload after a
    failed or mismatched extraction)."""
    statement = await db.get(BankStatement, statement_id)
    if statement is None:
        raise NotFoundError("Bank statement not found.")
    await AuditService(db).record_delete(
        "bank_statements", statement.id, current_user.id,
        ip_address=_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    await db.delete(statement)
    await db.commit()
    return MessageResponse(message="Bank statement deleted.")
