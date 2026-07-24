"""
Analytics computation engine.

All metrics are calculated here and written to analytics_snapshots.
Config values (grace days, rate) are read from system_config table at runtime.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any


@dataclass
class AnalyticsInput:
    deposit_request_id: Any  # UUID
    estimated_etd: date | None
    created_at: date
    deposit_amount: Decimal
    # From payment_details — may be None if not yet paid
    payment_date: date | None
    ship_date: date | None
    actual_etd: date | None
    # Config
    etd_grace_days: int
    cost_of_fund_rate: float  # annualised rate e.g. 0.18
    cost_of_fund_grace_days: int


@dataclass
class AnalyticsResult:
    grace_etd: date | None
    etd_grace_overdue_days: int | None
    payment_to_ship_days: int | None
    payment_to_request_days: int | None
    actual_etd_overdue_days: int | None
    cost_of_fund_applicable: bool
    cost_of_fund_amount: Decimal
    default_status: str  # on_time | delayed | critical


def compute(inp: AnalyticsInput) -> AnalyticsResult:
    """Pure function — no I/O. Given raw inputs, return computed metrics."""
    today = date.today()

    # Grace ETD
    grace_etd: date | None = None
    if inp.estimated_etd:
        grace_etd = inp.estimated_etd + timedelta(days=inp.etd_grace_days)

    # ETD grace overdue days
    etd_grace_overdue_days: int | None = None
    if grace_etd:
        reference_date = inp.ship_date or today
        overdue = (reference_date - grace_etd).days
        etd_grace_overdue_days = overdue if overdue > 0 else 0

    # Payment to ship days
    payment_to_ship_days: int | None = None
    if inp.payment_date and inp.ship_date:
        payment_to_ship_days = (inp.ship_date - inp.payment_date).days

    # Payment to request days
    payment_to_request_days: int | None = None
    if inp.payment_date:
        request_date = inp.created_at
        payment_to_request_days = (inp.payment_date - request_date).days

    # Actual ETD overdue days — aligned to the client's sheet (verified 2026-07-10):
    # (ship_date or today) − Est ETD, SIGNED. Negative = shipped early; keeps
    # accruing day by day while unshipped and freezes at ship_date once recorded.
    # (The accounts-entered actual_etd field no longer feeds this metric.)
    actual_etd_overdue_days: int | None = None
    if inp.estimated_etd:
        actual_etd_overdue_days = ((inp.ship_date or today) - inp.estimated_etd).days

    # Cost of fund — client rule confirmed 2026-07-10 (supersedes the raw sheet
    # formula for within-grace rows): deposit × rate × days / 365 where days =
    # (ship_date or today) − Est ETD, but the charge only starts once the
    # etd_grace_days window is EXCEEDED — and then counts retroactively from
    # Est ETD itself (day 1, not day 11). Shipping 0..grace days late costs
    # nothing; shipping EARLY keeps the sheet's negative "notional gain";
    # unshipped rows stay at 0 until grace is exceeded, then accrue daily.
    # Applies only once the advance has been paid (pre-payment accrual pending
    # client confirmation). cost_of_fund_grace_days is intentionally unused —
    # etd_grace_days is the gate.
    cost_of_fund_applicable = False
    cost_of_fund_amount = Decimal("0.00")
    if inp.payment_date and inp.estimated_etd and actual_etd_overdue_days is not None:
        cost_of_fund_applicable = True
        past_grace = actual_etd_overdue_days > inp.etd_grace_days
        shipped_early = inp.ship_date is not None and actual_etd_overdue_days < 0
        if past_grace or shipped_early:
            cost_of_fund_amount = (
                inp.deposit_amount
                * Decimal(str(inp.cost_of_fund_rate))
                * Decimal(actual_etd_overdue_days)
                / Decimal("365")
            ).quantize(Decimal("0.01"))

    # Delay classification
    if etd_grace_overdue_days is None:
        default_status = "pending"
    elif etd_grace_overdue_days == 0:
        default_status = "on_time"
    elif etd_grace_overdue_days <= 30:
        default_status = "delayed"
    else:
        default_status = "critical"

    return AnalyticsResult(
        grace_etd=grace_etd,
        etd_grace_overdue_days=etd_grace_overdue_days,
        payment_to_ship_days=payment_to_ship_days,
        payment_to_request_days=payment_to_request_days,
        actual_etd_overdue_days=actual_etd_overdue_days,
        cost_of_fund_applicable=cost_of_fund_applicable,
        cost_of_fund_amount=cost_of_fund_amount,
        default_status=default_status,
    )
