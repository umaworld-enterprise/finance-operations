"""Payment Terms master endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.dependencies import CurrentUser, RequireFinanceAdmin, get_current_user
from app.core.exceptions import ConflictError, NotFoundError
from app.models.masters import PaymentTermsMaster
from app.repositories.base import BaseRepository
from app.schemas.masters import PaymentTermCreate, PaymentTermResponse, PaymentTermUpdate
from app.services.audit_service import AuditService

router = APIRouter(prefix="/masters/payment-terms", tags=["masters-payment-terms"])

DB = Annotated[AsyncSession, Depends(get_db_session)]
User = Annotated[CurrentUser, Depends(get_current_user)]
FinanceAdmin = Annotated[CurrentUser, RequireFinanceAdmin]


def _ip(req: Request) -> str | None:
    forwarded = req.headers.get("x-forwarded-for")
    return forwarded.split(",")[0].strip() if forwarded else (req.client.host if req.client else None)


@router.get("", response_model=list[PaymentTermResponse])
async def list_payment_terms(db: DB, _: User) -> list[PaymentTermResponse]:
    result = await db.execute(
        select(PaymentTermsMaster)
        .where(PaymentTermsMaster.is_active == True)  # noqa: E712
        .order_by(PaymentTermsMaster.sort_order, PaymentTermsMaster.label)
    )
    terms = result.scalars().all()
    return [PaymentTermResponse.model_validate(t) for t in terms]


@router.get("/all", response_model=list[PaymentTermResponse])
async def list_all_payment_terms(db: DB, _: FinanceAdmin) -> list[PaymentTermResponse]:
    """Admin endpoint — returns active and inactive terms."""
    result = await db.execute(
        select(PaymentTermsMaster).order_by(PaymentTermsMaster.sort_order, PaymentTermsMaster.label)
    )
    terms = result.scalars().all()
    return [PaymentTermResponse.model_validate(t) for t in terms]


@router.post("", response_model=PaymentTermResponse, status_code=status.HTTP_201_CREATED)
async def create_payment_term(
    data: PaymentTermCreate, current_user: FinanceAdmin, db: DB, request: Request
) -> PaymentTermResponse:
    existing = await db.execute(
        select(PaymentTermsMaster).where(func.lower(PaymentTermsMaster.label) == func.lower(data.label))
    )
    if existing.scalar_one_or_none():
        raise ConflictError(f"A payment term '{data.label}' already exists.")
    repo = BaseRepository(db, PaymentTermsMaster)
    term = await repo.create(**data.model_dump())
    await AuditService(db).record_create(
        "payment_terms_master", term.id, current_user.id,
        ip_address=_ip(request),
        user_agent=request.headers.get("user-agent"),
        new_value=data.label,
    )
    return PaymentTermResponse.model_validate(term)


@router.patch("/{term_id}", response_model=PaymentTermResponse)
async def update_payment_term(
    term_id: UUID, data: PaymentTermUpdate, current_user: FinanceAdmin, db: DB, request: Request
) -> PaymentTermResponse:
    repo = BaseRepository(db, PaymentTermsMaster)
    term = await repo.get_by_id(term_id)
    if not term:
        raise NotFoundError(f"Payment term {term_id} not found.")

    update_data = data.model_dump(exclude_unset=True)
    if "label" in update_data:
        clash = await db.execute(
            select(PaymentTermsMaster).where(
                func.lower(PaymentTermsMaster.label) == func.lower(update_data["label"]),
                PaymentTermsMaster.id != term_id,
            )
        )
        if clash.scalar_one_or_none():
            raise ConflictError(f"A payment term '{update_data['label']}' already exists.")

    audit = AuditService(db)
    ip = _ip(request)
    ua = request.headers.get("user-agent")
    for field, new_val in update_data.items():
        await audit.record_update(
            "payment_terms_master", term.id, current_user.id,
            field_name=field,
            old_value=str(getattr(term, field, "")),
            new_value=str(new_val),
            ip_address=ip,
            user_agent=ua,
        )

    term = await repo.update(term, **update_data)
    return PaymentTermResponse.model_validate(term)


@router.delete("/{term_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_payment_term(
    term_id: UUID, current_user: FinanceAdmin, db: DB, request: Request
) -> None:
    repo = BaseRepository(db, PaymentTermsMaster)
    term = await repo.get_by_id(term_id)
    if not term:
        raise NotFoundError(f"Payment term {term_id} not found.")
    await repo.update(term, is_active=False)
    await AuditService(db).record_update(
        "payment_terms_master", term_id, current_user.id,
        field_name="is_active", old_value="True", new_value="False",
        ip_address=_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
