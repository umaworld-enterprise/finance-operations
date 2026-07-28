"""Schemas for DepositRequest — create, update, response."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.enums import AuditAction, CurrencyCode, RequestStatus, SubmissionSource
from app.schemas.common import OrmBase
from app.schemas.analytics import AnalyticsSnapshotResponse
from app.schemas.masters import CustomerResponse, SupplierResponse, UserResponse, VerticalResponse
from app.schemas.tranche import TrancheCreate, TrancheResponse


class DepositRequestCreate(BaseModel):
    supplier_id: UUID
    customer_id: UUID
    vertical_id: UUID | None = None
    supplier_invoice_number: str | None = None
    sunshine_invoice_number: str | None = None
    currency: CurrencyCode | None = None
    exchange_rate: Decimal | None = None
    # Optional when tranches are supplied — then it is derived as their sum.
    # Kept for API compatibility with tranche-less submitters (public form).
    deposit_amount: Decimal | None = Field(None, gt=0)
    deposit_percentage: Decimal | None = None
    total_supplier_invoice_amount: Decimal = Field(gt=0)
    estimated_shipment_date: date | None = None
    estimated_etd: date | None = None
    payment_terms: str | None = None
    remarks: str | None = None
    override_flagged_supplier: bool = False
    # Advance Payment Tranches (Tranche I, II, …). When omitted, a single
    # tranche covering deposit_amount is created for compatibility.
    tranches: list[TrancheCreate] | None = None

    @field_validator("deposit_percentage")
    @classmethod
    def validate_percentage(cls, v: Decimal | None) -> Decimal | None:
        if v is not None and (v < 0 or v > 100):
            raise ValueError("Deposit percentage must be between 0 and 100")
        return v

    @model_validator(mode="after")
    def validate_tranches(self) -> "DepositRequestCreate":
        if self.tranches:
            total = sum((t.amount for t in self.tranches), Decimal("0"))
            if total > self.total_supplier_invoice_amount:
                raise ValueError(
                    "Total of tranche amounts cannot exceed the total supplier "
                    "proforma invoice amount."
                )
            # Deposit amount is always the sum of the tranches.
            self.deposit_amount = total
        elif self.deposit_amount is None:
            raise ValueError("Either deposit_amount or tranches must be provided.")
        return self


class DepositRequestUpdate(BaseModel):
    customer_id: UUID | None = None
    vertical_id: UUID | None = None
    supplier_invoice_number: str | None = None
    sunshine_invoice_number: str | None = None
    currency: CurrencyCode | None = None
    exchange_rate: Decimal | None = None
    deposit_amount: Decimal | None = Field(None, gt=0)
    deposit_percentage: Decimal | None = Field(None, gt=0, le=100)
    total_supplier_invoice_amount: Decimal | None = Field(None, gt=0)
    estimated_shipment_date: date | None = None
    estimated_etd: date | None = None
    payment_terms: str | None = None
    remarks: str | None = None


class StatusChangeRequest(BaseModel):
    remarks: str | None = None


class StatusHistoryResponse(OrmBase):
    id: UUID
    old_status: RequestStatus | None
    new_status: RequestStatus
    remarks: str | None
    changed_by: UUID | None = None
    changed_at: datetime


class ActivityItemResponse(BaseModel):
    id: UUID
    request_id: UUID
    request_number: str
    supplier_name: str
    old_status: RequestStatus | None
    new_status: RequestStatus
    remarks: str | None
    changed_at: datetime


class DepositRequestResponse(OrmBase):
    id: UUID
    request_number: str
    supplier: SupplierResponse
    customer: CustomerResponse
    vertical: VerticalResponse | None = None
    supplier_invoice_number: str | None
    sunshine_invoice_number: str | None
    currency: CurrencyCode | None = None
    exchange_rate: Decimal | None
    deposit_amount: Decimal
    deposit_percentage: Decimal | None = None
    total_supplier_invoice_amount: Decimal
    estimated_shipment_date: date | None = None
    estimated_etd: date | None
    payment_terms: str | None = None
    remarks: str | None
    submission_source: SubmissionSource
    current_status: RequestStatus
    is_locked: bool
    created_by: UUID | None
    creator: UserResponse | None = None
    created_at: datetime
    updated_at: datetime
    tranches: list[TrancheResponse] = []

    @model_validator(mode="after")
    def compute_tranche_percentages(self) -> "DepositRequestResponse":
        # Percentage of invoice is always system-calculated: amount / total
        # supplier proforma invoice amount. Never user-entered, never stored.
        for t in self.tranches:
            t.with_percentage(self.total_supplier_invoice_amount)
        return self


class DepositRequestDetailResponse(DepositRequestResponse):
    """Full detail view including status history and analytics snapshot."""
    status_history: list[StatusHistoryResponse] = []
    creator: UserResponse | None = None
    submitter_email: str | None = None
    analytics_snapshot: AnalyticsSnapshotResponse | None = None


class RequestAuditEntryResponse(BaseModel):
    """A single audit trail row shown on the request detail view — covers the
    request itself, its tranches, and adjustments touching it."""

    id: UUID
    entity_name: str
    entity_id: UUID
    field_name: str | None
    old_value: str | None
    new_value: str | None
    action: AuditAction
    changed_by_name: str | None
    changed_by_email: str | None
    changed_at: datetime
