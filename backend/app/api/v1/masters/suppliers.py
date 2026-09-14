"""Supplier and Defaulted Supplier master endpoints."""

from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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
    SupplierExposureResponse,
    SupplierExposureRow,
    SupplierResponse,
    SupplierUpdate,
)
from app.services.audit_service import AuditService

router = APIRouter(prefix="/masters/suppliers", tags=["masters-suppliers"])

DB = Annotated[AsyncSession, Depends(get_db_session)]
User = Annotated[CurrentUser, Depends(get_current_user)]
FinanceAdmin = Annotated[CurrentUser, RequireFinanceAdmin]


def _ip(req: Request) -> str | None:
    forwarded = req.headers.get("x-forwarded-for")
    return forwarded.split(",")[0].strip() if forwarded else (req.client.host if req.client else None)


@router.get("", response_model=list[SupplierResponse])
async def list_suppliers(db: DB, _: User) -> list[SupplierResponse]:
    repo = SupplierRepository(db)
    suppliers = await repo.list_active()
    return [SupplierResponse.model_validate(s) for s in suppliers]


@router.get("/all", response_model=list[SupplierResponse])
async def list_all_suppliers(db: DB, _: FinanceAdmin) -> list[SupplierResponse]:
    """Admin endpoint (19 Aug 2026 masters page) — active AND inactive."""
    result = await db.execute(select(Supplier).order_by(Supplier.name))
    return [SupplierResponse.model_validate(s) for s in result.scalars().all()]


@router.post("", response_model=SupplierResponse, status_code=status.HTTP_201_CREATED)
async def create_supplier(data: SupplierCreate, current_user: FinanceAdmin, db: DB, request: Request) -> SupplierResponse:
    repo = SupplierRepository(db)
    result = await db.execute(select(Supplier).where(Supplier.supplier_code == data.supplier_code))
    if result.scalar_one_or_none():
        raise ConflictError(f"Supplier code '{data.supplier_code}' already exists.")
    name_check = await db.execute(
        select(Supplier).where(func.lower(Supplier.name) == func.lower(data.name))
    )
    if name_check.scalar_one_or_none():
        raise ConflictError(f"A supplier named '{data.name}' already exists.")
    supplier = await repo.create(**data.model_dump())
    await AuditService(db).record_create(
        "suppliers", supplier.id, current_user.id,
        ip_address=_ip(request),
        user_agent=request.headers.get("user-agent"),
        new_value=data.name,
    )
    return SupplierResponse.model_validate(supplier)


@router.patch("/{supplier_id}", response_model=SupplierResponse)
async def update_supplier(
    supplier_id: UUID, data: SupplierUpdate, current_user: FinanceAdmin, db: DB, request: Request
) -> SupplierResponse:
    repo = SupplierRepository(db)
    supplier = await repo.get_by_id(supplier_id)
    if not supplier:
        raise NotFoundError(f"Supplier {supplier_id} not found.")

    audit = AuditService(db)
    ip = _ip(request)
    ua = request.headers.get("user-agent")
    update_data = data.model_dump(exclude_unset=True)

    for field, new_val in update_data.items():
        await audit.record_update(
            "suppliers", supplier.id, current_user.id,
            field_name=field,
            old_value=str(getattr(supplier, field, "")),
            new_value=str(new_val),
            ip_address=ip,
            user_agent=ua,
        )

    supplier = await repo.update(supplier, **update_data)
    return SupplierResponse.model_validate(supplier)


@router.get("/{supplier_id}/default-status", response_model=SupplierDefaultStatusResponse)
async def get_supplier_default_status(supplier_id: UUID, db: DB, _: User) -> SupplierDefaultStatusResponse:
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


@router.get("/{supplier_id}/exposure", response_model=SupplierExposureResponse)
async def get_supplier_exposure(supplier_id: UUID, db: DB, _: User) -> SupplierExposureResponse:
    """The supplier's whole live exposure (UAT Aug 2026, item 2): every open
    request — not cancelled/rejected, goods not yet shipped — split into
    'graced ETD passed' and 'graced ETD not yet passed', with per-currency
    deposit totals. Rendered on the Supplier Default History panel for HoM
    approval and the Accounts payment view."""
    from datetime import date as date_cls

    from app.models.analytics import AnalyticsSnapshot
    from app.models.deposit_request import DepositRequest
    from app.models.enums import RequestStatus
    from app.models.payment import PaymentDetails

    _CLOSED = (
        RequestStatus.CANCELLED_BY_MERCHANDISER,
        RequestStatus.CANCELLED_BY_ACCOUNTS,
        RequestStatus.REJECTED_BY_HOM,
        RequestStatus.REJECTED_BY_ACCOUNTS,
    )
    stmt = (
        select(DepositRequest, AnalyticsSnapshot, PaymentDetails.payment_date)
        .outerjoin(
            AnalyticsSnapshot,
            AnalyticsSnapshot.deposit_request_id == DepositRequest.id,
        )
        .outerjoin(
            PaymentDetails,
            PaymentDetails.deposit_request_id == DepositRequest.id,
        )
        .where(
            DepositRequest.supplier_id == supplier_id,
            DepositRequest.is_deleted.is_(False),
            DepositRequest.current_status.notin_(_CLOSED),
            # A recorded ship date ends the exposure (goods delivered) —
            # the outer join keeps requests with no payment row at all.
            PaymentDetails.ship_date.is_(None),
        )
        .order_by(DepositRequest.created_at)
    )
    rows = (await db.execute(stmt)).all()

    today = date_cls.today()
    passed: list[SupplierExposureRow] = []
    pending: list[SupplierExposureRow] = []
    totals: dict[str, Decimal] = {}
    for req, snap, payment_date in rows:
        row = SupplierExposureRow(
            request_id=req.id,
            request_number=req.request_number,
            sunshine_invoice_number=req.sunshine_invoice_number,
            deposit_amount=req.deposit_amount,
            currency=req.currency.value if req.currency else None,
            current_status=req.current_status.value,
            grace_etd=snap.grace_etd if snap else None,
            etd_grace_overdue_days=snap.etd_grace_overdue_days if snap else None,
            # 2 Sep 2026: paid amounts always carry their payment date, and
            # every exposure row shows when the request was raised.
            payment_date=payment_date,
            request_date=req.created_at.date() if req.created_at else None,
        )
        if snap and snap.grace_etd and snap.grace_etd < today:
            passed.append(row)
        else:
            pending.append(row)
        key = row.currency or "—"
        totals[key] = totals.get(key, Decimal("0")) + Decimal(str(req.deposit_amount))

    return SupplierExposureResponse(
        supplier_id=supplier_id,
        graced_etd_passed=passed,
        graced_etd_pending=pending,
        totals_by_currency=totals,
    )


@router.get("/{supplier_id}/default-history", response_model=list[DefaultedSupplierResponse])
async def get_supplier_default_history(supplier_id: UUID, db: DB, _: User) -> list[DefaultedSupplierResponse]:
    """Full default history for one supplier — active and resolved flags,
    newest first. Shown on request detail pages so approvers can weigh the
    supplier's track record before deciding (Aug 2026 follow-up)."""
    repo = DefaultedSupplierRepository(db)
    flags = await repo.list_for_supplier(supplier_id)
    return [DefaultedSupplierResponse.from_orm_obj(f) for f in flags]


# ── Defaulted Suppliers ───────────────────────────────────────────────────────

@router.get("/defaulted", response_model=list[DefaultedSupplierResponse])
async def list_defaulted_suppliers(db: DB, _: User) -> list[DefaultedSupplierResponse]:
    repo = DefaultedSupplierRepository(db)
    flags = await repo.list_active()
    return [DefaultedSupplierResponse.from_orm_obj(f) for f in flags]


@router.post("/defaulted", response_model=DefaultedSupplierResponse, status_code=status.HTTP_201_CREATED)
async def flag_defaulted_supplier(
    data: DefaultedSupplierCreate, current_user: FinanceAdmin, db: DB, request: Request
) -> DefaultedSupplierResponse:
    repo = SupplierRepository(db)
    existing_flag = await repo.get_active_default_flag(data.supplier_id)
    if existing_flag:
        raise ConflictError("Supplier already has an active default flag.")
    default_repo = DefaultedSupplierRepository(db)
    flag = await default_repo.create(**data.model_dump(), flagged_by=current_user.id)
    await AuditService(db).record_create(
        "defaulted_suppliers", flag.id, current_user.id,
        ip_address=_ip(request),
        user_agent=request.headers.get("user-agent"),
        new_value=f"supplier_id={data.supplier_id} amount={data.outstanding_amount} {data.currency}",
    )
    # selectinload is required: from_orm_obj reads flag.supplier.name, and a
    # lazy load here would raise MissingGreenlet in async context.
    result = await db.execute(
        select(DefaultedSupplier)
        .where(DefaultedSupplier.id == flag.id)
        .options(selectinload(DefaultedSupplier.supplier))
    )
    return DefaultedSupplierResponse.from_orm_obj(result.scalar_one())


@router.post("/defaulted/{flag_id}/resolve", response_model=MessageResponse)
async def resolve_defaulted_supplier(
    flag_id: UUID, current_user: FinanceAdmin, db: DB, request: Request
) -> MessageResponse:
    repo = DefaultedSupplierRepository(db)
    flag = await repo.get_by_id(flag_id)
    if not flag or not flag.is_active:
        raise NotFoundError(f"Active default flag {flag_id} not found.")
    await repo.resolve(flag, current_user.id)
    await AuditService(db).record_update(
        "defaulted_suppliers", flag_id, current_user.id,
        field_name="is_active", old_value="True", new_value="False",
        ip_address=_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return MessageResponse(message="Supplier default flag resolved.")
