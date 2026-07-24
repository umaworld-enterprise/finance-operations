"""Schemas for analytics endpoints."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import RequestStatus
from app.schemas.common import OrmBase


class AnalyticsSnapshotResponse(OrmBase):
    deposit_request_id: UUID
    grace_etd: date | None
    etd_grace_overdue_days: int | None
    payment_to_ship_days: int | None
    payment_to_request_days: int | None
    actual_etd_overdue_days: int | None
    cost_of_fund_applicable: bool | None
    cost_of_fund_amount: Decimal | None
    default_status: str | None
    calculated_at: datetime


class AnalyticsSummary(BaseModel):
    total_requests: int
    pending_payment_count: int
    payment_processed_count: int
    total_deposit_exposure: Decimal
    overdue_shipments: int
    total_cost_of_fund: Decimal
    avg_payment_to_ship_days: float | None


class AnalyticsFilters(BaseModel):
    supplier_id: UUID | None = None
    customer_id: UUID | None = None
    vertical_id: UUID | None = None
    staff_id: UUID | None = None
    date_from: date | None = None
    date_to: date | None = None
