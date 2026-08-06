"""Bank name master endpoints (Aug 2026).

The master stores bank NAMES only — the tranche payment-details form composes
the dropdown option as '{name} ({currency})' from the request's currency.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.dependencies import CurrentUser, RequireFinanceAdmin, get_current_user
from app.core.exceptions import ConflictError, NotFoundError
from app.models.masters import BankMaster
from app.repositories.base import BaseRepository
from app.schemas.masters import BankCreate, BankResponse, BankUpdate
from app.services.audit_service import AuditService

router = APIRouter(prefix="/masters/banks", tags=["masters-banks"])

DB = Annotated[AsyncSession, Depends(get_db_session)]
User = Annotated[CurrentUser, Depends(get_current_user)]
FinanceAdmin = Annotated[CurrentUser, RequireFinanceAdmin]


def _ip(req: Request) -> str | None:
    forwarded = req.headers.get("x-forwarded-for")
    return forwarded.split(",")[0].strip() if forwarded else (req.client.host if req.client else None)


@router.get("", response_model=list[BankResponse])
async def list_banks(db: DB, _: User) -> list[BankResponse]:
    result = await db.execute(
        select(BankMaster)
        .where(BankMaster.is_active == True)  # noqa: E712
        .order_by(BankMaster.sort_order, BankMaster.name)
    )
    return [BankResponse.model_validate(b) for b in result.scalars().all()]


@router.get("/all", response_model=list[BankResponse])
async def list_all_banks(db: DB, _: FinanceAdmin) -> list[BankResponse]:
    """Admin endpoint — returns active and inactive banks."""
    result = await db.execute(
        select(BankMaster).order_by(BankMaster.sort_order, BankMaster.name)
    )
    return [BankResponse.model_validate(b) for b in result.scalars().all()]


@router.post("", response_model=BankResponse, status_code=status.HTTP_201_CREATED)
async def create_bank(
    data: BankCreate, current_user: FinanceAdmin, db: DB, request: Request
) -> BankResponse:
    existing = await db.execute(
        select(BankMaster).where(func.lower(BankMaster.name) == func.lower(data.name))
    )
    if existing.scalar_one_or_none():
        raise ConflictError(f"A bank '{data.name}' already exists.")
    repo = BaseRepository(db, BankMaster)
    bank = await repo.create(**data.model_dump())
    await AuditService(db).record_create(
        "banks_master", bank.id, current_user.id,
        ip_address=_ip(request),
        user_agent=request.headers.get("user-agent"),
        new_value=data.name,
    )
    return BankResponse.model_validate(bank)


@router.patch("/{bank_id}", response_model=BankResponse)
async def update_bank(
    bank_id: UUID, data: BankUpdate, current_user: FinanceAdmin, db: DB, request: Request
) -> BankResponse:
    repo = BaseRepository(db, BankMaster)
    bank = await repo.get_by_id(bank_id)
    if not bank:
        raise NotFoundError(f"Bank {bank_id} not found.")

    update_data = data.model_dump(exclude_unset=True)
    if "name" in update_data:
        clash = await db.execute(
            select(BankMaster).where(
                func.lower(BankMaster.name) == func.lower(update_data["name"]),
                BankMaster.id != bank_id,
            )
        )
        if clash.scalar_one_or_none():
            raise ConflictError(f"A bank '{update_data['name']}' already exists.")

    audit = AuditService(db)
    ip = _ip(request)
    ua = request.headers.get("user-agent")
    for field, new_val in update_data.items():
        await audit.record_update(
            "banks_master", bank.id, current_user.id,
            field_name=field,
            old_value=str(getattr(bank, field, "")),
            new_value=str(new_val),
            ip_address=ip, user_agent=ua,
        )
    bank = await repo.update(bank, **update_data)
    return BankResponse.model_validate(bank)


@router.delete("/{bank_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bank(
    bank_id: UUID, current_user: FinanceAdmin, db: DB, request: Request
) -> None:
    repo = BaseRepository(db, BankMaster)
    bank = await repo.get_by_id(bank_id)
    if not bank:
        raise NotFoundError(f"Bank {bank_id} not found.")
    await repo.update(bank, is_active=False)
    await AuditService(db).record_update(
        "banks_master", bank_id, current_user.id,
        field_name="is_active", old_value="True", new_value="False",
        ip_address=_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
