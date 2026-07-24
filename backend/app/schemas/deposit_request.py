"""Schemas for DepositRequest — create, update, response."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.models.enums import CurrencyCode, RequestStatus, SubmissionSource
from app.schemas.common import OrmBase
from app.schemas.analytics import AnalyticsSnapshotResponse
from app.schemas.masters import CustomerResponse, SupplierResponse, UserResponse, VerticalResponse


class DepositRequestCreate(BaseModel):
    supplier_id: UUID
    customer_id: UUID
    vertical_id: UUID | None = None
    supplier_invoice_number: str | None = None
    sunshine_invoice_number: str | None = None
    currency: CurrencyCode | None = None
    exchange_rate: Decimal | None = None
    deposit_amount: Decimal = Field(gt=0)
    deposit_percentage: Decimal | None = None
    total_supplier_invoice_amount: Decimal = Field(gt=0)
    estimated_shipment_date: date | None = None
    estimated_etd: date | None = None
    payment_terms: str | None = None
    remarks: str | None = None
    override_flagged_supplier: bool = False

    @field_validator("deposit_percentage")
    @classmethod
    def validate_percentage(cls, v: Decimal | None) -> Decimal | None:
        if v is not None and (v < 0 or v > 100):
            raise ValueError("Deposit percentage must be between 0 and 100")
        return v


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


class DepositRequestDetailResponse(DepositRequestResponse):
    """Full detail view including status history and analytics snapshot."""
    status_history: list[StatusHistoryResponse] = []
    creator: UserResponse | None = None
    submitter_email: str | None = None
    analytics_snapshot: AnalyticsSnapshotResponse | None = None
