"""Schemas for analytics endpoints."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import CurrencyCode, RequestStatus
from app.schemas.common import OrmBase


class AnalyticsSnapshotResponse(OrmBase):
    deposit_request_id: UUID
    request_number: str | None = None
    current_status: RequestStatus | None = None
    # Currency of the underlying request — cost_of_fund_amount is denominated in it.
    currency: CurrencyCode | None = None
    grace_etd: date | None
    etd_grace_overdue_days: int | None
    payment_to_ship_days: int | None
    payment_to_request_days: int | None
    actual_etd_overdue_days: int | None
    cost_of_fund_applicable: bool | None
    cost_of_fund_amount: Decimal | None
    default_status: str | None
    calculated_at: datetime

    @classmethod
    def from_orm_obj(cls, snap) -> "AnalyticsSnapshotResponse":  # type: ignore[no-untyped-def]
        dr = getattr(snap, "deposit_request", None)
        return cls(
            deposit_request_id=snap.deposit_request_id,
            request_number=dr.request_number if dr else None,
            current_status=dr.current_status if dr else None,
            currency=dr.currency if dr else None,
            grace_etd=snap.grace_etd,
            etd_grace_overdue_days=snap.etd_grace_overdue_days,
            payment_to_ship_days=snap.payment_to_ship_days,
            payment_to_request_days=snap.payment_to_request_days,
            actual_etd_overdue_days=snap.actual_etd_overdue_days,
            cost_of_fund_applicable=snap.cost_of_fund_applicable,
            cost_of_fund_amount=snap.cost_of_fund_amount,
            default_status=snap.default_status,
            calculated_at=snap.calculated_at,
        )


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


class MonthlyTrendPoint(BaseModel):
    month: int
    month_name: str
    total_overdue_days: int
    total_cost_of_fund: float
    ytd_overdue_days: int
    ytd_cost_of_fund: float
    request_count: int


class FlaggedSupplierNpa(BaseModel):
    supplier_id: UUID
    supplier_name: str
    flagged_date: date | None = None
    default_reason: str | None = None
    is_auto_flagged: bool
    is_formally_flagged: bool
    overdue_request_count: int
    max_overdue_days: int


class MerchandiserNpa(BaseModel):
    merchandiser_id: UUID
    name: str
    email: str
    total_requests: int
    overdue_count: int
    avg_overdue_days: float | None


class NpaResponse(BaseModel):
    flagged_suppliers: list[FlaggedSupplierNpa]
    merchandiser_performance: list[MerchandiserNpa]
