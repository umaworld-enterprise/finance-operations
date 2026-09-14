"""Schemas for PaymentDetails."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import PaymentStatus
from app.schemas.common import OrmBase


class PaymentUpdate(BaseModel):
    """Partial PATCH body — deliberately permissive so existing rows (incl.
    partial ones created by set_ship_date / attach_tt_copy) can be updated
    field by field. Completeness is enforced at process time."""

    payment_date: date | None = None
    bank: str | None = None
    payment_reference_number: str | None = None
    payment_status: PaymentStatus | None = None
    ship_date: date | None = None
    actual_etd: date | None = None
    accounts_remarks: str | None = None


class PaymentCreate(PaymentUpdate):
    """POST body — Payment Date, Bank and Payment Status are mandatory
    (14 Jul 2026 change note, C7). The Payment Reference Number was made
    optional again by the Aug 2026 change batch (item 3.2)."""

    payment_date: date
    bank: str = Field(min_length=1)
    payment_status: PaymentStatus


class ShipDateUpdate(BaseModel):
    ship_date: date


class PaymentResponse(OrmBase):
    id: UUID
    deposit_request_id: UUID
    payment_date: date | None
    bank: str | None
    payment_reference_number: str | None
    payment_status: str | None
    ship_date: date | None
    actual_etd: date | None
    accounts_remarks: str | None
    tt_copy_url: str | None = None
    tt_copy_file_id: str | None = None
    tt_copy_filename: str | None = None
    updated_by: UUID | None
    updated_at: datetime
