"""Schemas for PaymentDetails."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import PaymentStatus
from app.schemas.common import OrmBase


class PaymentCreate(BaseModel):
    payment_date: date | None = None
    bank: str | None = None
    payment_reference_number: str | None = None
    payment_status: PaymentStatus | None = None
    ship_date: date | None = None
    actual_etd: date | None = None
    accounts_remarks: str | None = None


class PaymentUpdate(PaymentCreate):
    pass


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
