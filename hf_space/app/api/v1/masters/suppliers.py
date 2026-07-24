"""Supplier and Defaulted Supplier master endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.dependencies import CurrentUser, RequireFinanceAdmin, get_current_user
from app.core.exceptions import ConflictError, NotFoundError
from app.models.integrations import DefaultedSupplier
from app.models.masters import Supplier
from app.repositories.supplier_repo import DefaultedSupplierRepository, SupplierRepository
from app.schemas.common import MessageResponse
from app.schemas.masters import (
    DefaultedSupplierCreate,
    DefaultedSupplierResponse,
    SupplierCreate,
    SupplierDefaultStatusResponse,
    SupplierResponse,
    SupplierUpdate,
)
from app.services.audit_service import AuditService

router = APIRouter(prefix="/masters/suppliers", tags=["masters-suppliers"])

DB = Annotated[AsyncSession, Depends(get_db_session)]
User = Annotated[CurrentUser, Depends(get_current_user)]
FinanceAdmin = Annotated[CurrentUser, RequireFinanceAdmin]


@router.get("", response_model=list[SupplierResponse])
async def list_suppliers(db: DB, _: User) -> list[SupplierResponse]:
    repo = SupplierRepository(db)
    suppliers = await repo.list_active()
    return [SupplierResponse.model_validate(s) for s in suppliers]


@router.post("", response_model=SupplierResponse, status_code=status.HTTP_201_CREATED)
async def create_supplier(data: SupplierCreate, current_user: FinanceAdmin, db: DB) -> SupplierResponse:
    repo = SupplierRepository(db)
    result = await db.execute(select(Supplier).where(Supplier.supplier_code == data.supplier_code))
    if result.scalar_one_or_none():
        raise ConflictError(f"Supplier code '{data.supplier_code}' already exists.")
    supplier = await repo.create(**data.model_dump())
    audit = AuditService(db)
    await audit.record_create("suppliers", supplier.id, current_user.id)
    return SupplierResponse.model_validate(supplier)


@router.patch("/{supplier_id}", response_model=SupplierResponse)
async def update_supplier(
    supplier_id: UUID, data: SupplierUpdate, current_user: FinanceAdmin, db: DB
) -> SupplierResponse:
    repo = SupplierRepository(db)
    supplier = await repo.get_by_id(supplier_id)
    if not supplier:
        raise NotFoundError(f"Supplier {supplier_id} not found.")
    supplier = await repo.update(supplier, **data.model_dump(exclude_unset=True))
    return SupplierResponse.model_validate(supplier)


@router.get("/{supplier_id}/default-status", response_model=SupplierDefaultStatusResponse)
async def get_supplier_default_status(supplier_id: UUID, db: DB, _: User) -> SupplierDefaultStatusResponse:
    """Real-time check — called by the new request form on supplier selection."""
    repo = SupplierRepository(db)
    flag = await repo.get_active_default_flag(supplier_id)
    if flag:
        return SupplierDefaultStatusResponse(
            supplier_id=supplier_id,
            is_defaulted=True,
            outstanding_amount=flag.outstanding_amount,
            currency=flag.currency,
            default_reason=flag.default_reason,
        )
    return SupplierDefaultStatusResponse(supplier_id=supplier_id, is_defaulted=False)


# ── Defaulted Suppliers ───────────────────────────────────────────────────────

@router.get("/defaulted", response_model=list[DefaultedSupplierResponse])
async def list_defaulted_suppliers(db: DB, _: User) -> list[DefaultedSupplierResponse]:
    repo = DefaultedSupplierRepository(db)
    flags = await repo.list_active()
    return [DefaultedSupplierResponse.from_orm_obj(f) for f in flags]


@router.post("/defaulted", response_model=DefaultedSupplierResponse, status_code=status.HTTP_201_CREATED)
async def flag_defaulted_supplier(
    data: DefaultedSupplierCreate, current_user: FinanceAdmin, db: DB
) -> DefaultedSupplierResponse:
    repo = SupplierRepository(db)
    existing_flag = await repo.get_active_default_flag(data.supplier_id)
    if existing_flag:
        raise ConflictError("Supplier already has an active default flag.")
    from datetime import date
    default_repo = DefaultedSupplierRepository(db)
    flag = await default_repo.create(
        **data.model_dump(),
        flagged_by=current_user.id,
    )
    audit = AuditService(db)
    await audit.record_create("defaulted_suppliers", flag.id, current_user.id)
    result = await db.execute(
        select(DefaultedSupplier).where(DefaultedSupplier.id == flag.id)
    )
    flag_with_rel = result.scalar_one()
    return DefaultedSupplierResponse.from_orm_obj(flag_with_rel)


@router.post("/defaulted/{flag_id}/resolve", response_model=MessageResponse)
async def resolve_defaulted_supplier(
    flag_id: UUID, current_user: FinanceAdmin, db: DB
) -> MessageResponse:
    repo = DefaultedSupplierRepository(db)
    flag = await repo.get_by_id(flag_id)
    if not flag or not flag.is_active:
        raise NotFoundError(f"Active default flag {flag_id} not found.")
    await repo.resolve(flag, current_user.id)
    audit = AuditService(db)
    await audit.record_update(
        "defaulted_suppliers", flag_id, current_user.id,
        field_name="is_active", old_value="True", new_value="False",
    )
    return MessageResponse(message="Supplier default flag resolved.")
