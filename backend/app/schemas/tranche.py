"""Schemas for Advance Payment Tranches and Invoice Adjustments."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.models.enums import AdjustmentStatus, TrancheStatus
from app.schemas.common import OrmBase


def _assert_two_decimal_places(v: Decimal) -> Decimal:
    if v != v.quantize(Decimal("0.01")):
        raise ValueError("Amount must have at most 2 decimal places")
    return v


class TrancheCreate(BaseModel):
    amount: Decimal = Field(gt=0)
    tentative_payment_date: date

    @field_validator("amount")
    @classmethod
    def validate_precision(cls, v: Decimal) -> Decimal:
        return _assert_two_decimal_places(v)


class TrancheUpdate(BaseModel):
    """Merchandiser-editable fields on an UNPAID tranche."""

    amount: Decimal | None = Field(None, gt=0)
    tentative_payment_date: date | None = None

    @field_validator("amount")
    @classmethod
    def validate_precision(cls, v: Decimal | None) -> Decimal | None:
        return _assert_two_decimal_places(v) if v is not None else v


class TrancheResponse(OrmBase):
    id: UUID
    deposit_request_id: UUID
    tranche_number: int
    label: str
    amount: Decimal
    tentative_payment_date: date | None
    # amount / total supplier proforma invoice amount — always computed
    # server-side, never user-entered.
    percentage_of_invoice: Decimal | None = None
    status: TrancheStatus
    paid_at: datetime | None
    paid_by: UUID | None
    tt_copy_url: str | None = None
    tt_copy_file_id: str | None = None
    tt_copy_filename: str | None = None
    is_legacy: bool
    created_at: datetime
    updated_at: datetime
    # Adjustment context — filled where the endpoint loads adjustments.
    adjusted_out_total: Decimal | None = None
    available_paid_balance: Decimal | None = None
    adjusted_in_total: Decimal | None = None
    # Request context — filled by endpoints that list tranches across requests
    # (e.g. the Adjust Invoices pickers) so the invoice is identifiable.
    request_number: str | None = None
    request_currency: str | None = None
    supplier_invoice_number: str | None = None
    sunshine_invoice_number: str | None = None

    def with_percentage(self, total_invoice_amount: Decimal | None) -> "TrancheResponse":
        if total_invoice_amount and total_invoice_amount > 0:
            self.percentage_of_invoice = (
                Decimal(self.amount) / Decimal(total_invoice_amount) * 100
            ).quantize(Decimal("0.01"))
        return self


class AdjustmentCreate(BaseModel):
    source_tranche_id: UUID
    destination_tranche_id: UUID
    amount: Decimal = Field(gt=0)
    reason: str | None = None

    @field_validator("amount")
    @classmethod
    def validate_precision(cls, v: Decimal) -> Decimal:
        return _assert_two_decimal_places(v)


class AdjustmentDecision(BaseModel):
    """Approve/reject body for a pending adjustment — the reason is mandatory
    for both decisions (14 Jul 2026 change note, B3) and is recorded in the
    audit trail and the merchandiser's notification."""

    reason: str = Field(min_length=1)


class AdjustmentResponse(OrmBase):
    id: UUID
    source_tranche_id: UUID
    destination_tranche_id: UUID
    amount: Decimal
    reason: str | None
    status: AdjustmentStatus
    performed_by: UUID
    created_at: datetime
    # Traceability context — filled by the service from joined rows.
    performed_by_name: str | None = None
    source_request_id: UUID | None = None
    source_request_number: str | None = None
    source_tranche_label: str | None = None
    destination_request_id: UUID | None = None
    destination_request_number: str | None = None
    destination_tranche_label: str | None = None
    supplier_name: str | None = None


class SupplierTrancheOptions(BaseModel):
    """Source/destination candidates for the Adjust Invoices module."""

    paid_sources: list[TrancheResponse]
    unpaid_destinations: list[TrancheResponse]
