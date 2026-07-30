"""Public form endpoints — no authentication required.

Anyone with the form URL can submit a deposit request.
Submitter email is stored on the record for traceability.
"""

from datetime import date
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response

from app.analytics.snapshot_job import seed_snapshot_for_request
from pydantic import BaseModel, EmailStr, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db_session
from app.core.rate_limit import limiter
import json

from app.models.enums import CurrencyCode
from app.models.integrations import DefaultedSupplier
from app.models.masters import Customer, PaymentTermsMaster, Supplier, SystemConfig, Vertical
from app.schemas.deposit_request import DepositRequestCreate
from app.schemas.tranche import TrancheCreate
from app.services.deposit_request_service import DepositRequestService

router = APIRouter(prefix="/public", tags=["public-form"])
settings = get_settings()

DB = Annotated[AsyncSession, Depends(get_db_session)]


# ── Master data (read-only, no auth) ─────────────────────────────────────────

class MasterItem(BaseModel):
    id: UUID
    name: str


class PublicSupplierItem(BaseModel):
    id: UUID
    name: str
    fixed_deposit_amount: float | None = None
    is_flagged: bool = False


class PublicMasters(BaseModel):
    verticals: list[MasterItem]
    customers: list[MasterItem]
    suppliers: list[PublicSupplierItem]
    currencies: list[str]
    payment_terms: list[str]


@router.get("/form-config")
@limiter.limit(settings.rate_limit_public_default)
async def get_public_form_config(request: Request, db: DB, response: Response) -> dict:
    """Return the current field configuration for the public form."""
    response.headers["Cache-Control"] = "public, max-age=300"
    result = await db.execute(
        select(SystemConfig.config_value).where(SystemConfig.config_key == "public_form_fields")
    )
    raw = result.scalar_one_or_none()
    try:
        return json.loads(raw) if raw else {}
    except (ValueError, Exception):
        return {}


@router.get("/masters", response_model=PublicMasters)
@limiter.limit(settings.rate_limit_public_default)
async def get_masters(request: Request, db: DB, response: Response) -> PublicMasters:
    """Return active verticals, customers, and suppliers for the public form dropdowns."""
    response.headers["Cache-Control"] = "public, max-age=300"
    verticals_res = await db.execute(
        select(Vertical.id, Vertical.name)
        .where(Vertical.is_active == True)  # noqa: E712
        .order_by(Vertical.name)
    )
    customers_res = await db.execute(
        select(Customer.id, Customer.name)
        .where(Customer.is_active == True)  # noqa: E712
        .order_by(Customer.name)
    )
    suppliers_res = await db.execute(
        select(Supplier.id, Supplier.name, Supplier.fixed_deposit_amount)
        .where(Supplier.is_active == True)  # noqa: E712
        .order_by(Supplier.name)
    )
    terms_res = await db.execute(
        select(PaymentTermsMaster.label)
        .where(PaymentTermsMaster.is_active == True)  # noqa: E712
        .order_by(PaymentTermsMaster.sort_order, PaymentTermsMaster.label)
    )
    flagged_res = await db.execute(
        select(DefaultedSupplier.supplier_id)
        .where(DefaultedSupplier.is_active == True)  # noqa: E712
    )
    flagged_ids = {row.supplier_id for row in flagged_res.all()}
    return PublicMasters(
        verticals=[MasterItem(id=r.id, name=r.name) for r in verticals_res.all()],
        customers=[MasterItem(id=r.id, name=r.name) for r in customers_res.all()],
        suppliers=[
            PublicSupplierItem(
                id=r.id,
                name=r.name,
                fixed_deposit_amount=float(r.fixed_deposit_amount) if r.fixed_deposit_amount is not None else None,
                is_flagged=r.id in flagged_ids,
            )
            for r in suppliers_res.all()
        ],
        currencies=[c.value for c in CurrencyCode],
        payment_terms=[r.label for r in terms_res.all()],
    )


# ── Submission ────────────────────────────────────────────────────────────────

class PublicSubmissionRequest(BaseModel):
    """All fields are optional at the Pydantic level — config-driven required checks happen in the endpoint."""
    submitter_email: EmailStr
    # Core (always required in DB)
    supplier_id: UUID
    customer_id: UUID
    # Either explicit tranches (the current form) or a plain deposit_amount
    # (legacy callers) — DepositRequestCreate enforces one of the two.
    deposit_amount: Decimal | None = Field(None, gt=0)
    tranches: list[TrancheCreate] | None = None
    total_supplier_invoice_amount: Decimal = Field(gt=0)
    # Configurable — may be hidden/optional
    vertical_id: UUID | None = None
    currency: CurrencyCode | None = None
    sunshine_invoice_number: str | None = None
    supplier_invoice_number: str | None = None
    deposit_percentage: Decimal | None = None
    estimated_etd: date | None = None
    payment_terms: str | None = None
    remarks: str | None = None
    override_flagged_supplier: bool = False


class PublicSubmissionResponse(BaseModel):
    request_number: str
    message: str


@router.post("/submit", response_model=PublicSubmissionResponse)
@limiter.limit(settings.rate_limit_public_submit)
async def submit_public_form(
    request: Request, body: PublicSubmissionRequest, db: DB, background_tasks: BackgroundTasks
) -> PublicSubmissionResponse:
    """Accept a deposit request from the public form (no login required)."""
    from app.core.exceptions import BusinessRuleError
    from app.repositories.user_repo import UserRepository

    # Every form submission must map to a registered account.
    user_repo = UserRepository(db)
    submitter = await user_repo.get_by_email(str(body.submitter_email))
    if submitter is None:
        raise BusinessRuleError(
            "No account found for this email address. Please contact your administrator."
        )

    # Load form config to validate required fields
    cfg_result = await db.execute(
        select(SystemConfig.config_value).where(SystemConfig.config_key == "public_form_fields")
    )
    raw_cfg = cfg_result.scalar_one_or_none()
    try:
        cfg: dict = json.loads(raw_cfg) if raw_cfg else {}
    except (ValueError, Exception):
        cfg = {}

    def field_required(key: str) -> bool:
        return cfg.get(key, {}).get("required", False)

    # Validate configurable required fields. deposit_percentage is NOT checked
    # any more — the field was retired in favour of Advance Payment Tranches
    # (the percentage is system-calculated), so a stale "required" entry in the
    # stored form config must not block submissions.
    errors: list[str] = []
    if field_required("vertical_id") and body.vertical_id is None:
        errors.append("Vertical / Category is required")
    if field_required("currency") and body.currency is None:
        errors.append("Currency is required")
    if errors:
        raise BusinessRuleError("; ".join(errors))

    svc = DepositRequestService(db)

    # DepositRequestCreate is constructed manually (not via FastAPI request
    # validation), so its field validators raise a raw pydantic ValidationError
    # here — catch it and surface the messages as a normal 4xx business error
    # instead of an unhandled 500.
    try:
        data = DepositRequestCreate(
            supplier_id=body.supplier_id,
            customer_id=body.customer_id,
            vertical_id=body.vertical_id,
            currency=body.currency,
            sunshine_invoice_number=body.sunshine_invoice_number,
            supplier_invoice_number=body.supplier_invoice_number,
            total_supplier_invoice_amount=body.total_supplier_invoice_amount,
            deposit_percentage=body.deposit_percentage,
            deposit_amount=body.deposit_amount,
            estimated_etd=body.estimated_etd,
            payment_terms=body.payment_terms,
            remarks=body.remarks,
            override_flagged_supplier=body.override_flagged_supplier,
            tranches=body.tranches,
        )
    except ValidationError as exc:
        messages = "; ".join(
            str(err.get("ctx", {}).get("error") or err.get("msg", "Invalid value"))
            for err in exc.errors()
        )
        raise BusinessRuleError(messages) from exc

    request = await svc.create_public(
        data=data,
        submitter_email=str(body.submitter_email),
        created_by=submitter.id,
    )

    background_tasks.add_task(seed_snapshot_for_request, request.id)

    return PublicSubmissionResponse(
        request_number=request.request_number,
        message=f"Your Supplier Advance Payment Request {request.request_number} has been submitted successfully. The accounts team will review it shortly.",
    )
