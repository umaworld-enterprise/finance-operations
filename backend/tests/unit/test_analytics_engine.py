"""Unit tests for the analytics computation engine."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.analytics.engine import AnalyticsInput, compute


def _base_input(**overrides) -> AnalyticsInput:
    defaults = dict(
        deposit_request_id="test-id",
        estimated_etd=date(2025, 6, 1),
        created_at=date(2025, 4, 1),
        deposit_amount=Decimal("10000.00"),
        payment_date=date(2025, 4, 15),
        ship_date=date(2025, 6, 20),
        actual_etd=None,
        etd_grace_days=10,
        cost_of_fund_rate=0.18,
        cost_of_fund_grace_days=30,
    )
    defaults.update(overrides)
    return AnalyticsInput(**defaults)


def _cof(deposit: str, rate: str, days: int) -> Decimal:
    return (Decimal(deposit) * Decimal(rate) * Decimal(days) / Decimal("365")).quantize(
        Decimal("0.01")
    )


def test_grace_etd_is_etd_plus_grace_days():
    result = compute(_base_input())
    assert result.grace_etd == date(2025, 6, 11)  # June 1 + 10 days


# ── Defaulter logic (client rule 11 Aug 2026): overdue accrues ONLY when the
# advance is PAID + the graced ETD is surpassed + shipment NOT made.


def test_overdue_accrues_when_paid_unshipped_past_grace():
    # Paid, unshipped, grace ended 30 days ago → 30 days overdue.
    etd = date.today() - timedelta(days=40)  # grace_etd = etd + 10
    result = compute(_base_input(estimated_etd=etd, ship_date=None))
    assert result.etd_grace_overdue_days == 30


def test_overdue_zero_when_shipment_made():
    # Shipped (even after grace) → no longer a defaulter; lateness history
    # stays in actual_etd_overdue_days / cost of fund.
    result = compute(_base_input(ship_date=date(2025, 6, 20)))
    assert result.etd_grace_overdue_days == 0
    assert result.actual_etd_overdue_days == 19  # history preserved


def test_overdue_zero_when_advance_not_paid():
    # Unpaid past grace → no money out → not overdue, not a defaulter.
    etd = date.today() - timedelta(days=40)
    result = compute(_base_input(estimated_etd=etd, payment_date=None, ship_date=None))
    assert result.etd_grace_overdue_days == 0
    assert result.default_status == "on_time"


def test_etd_grace_overdue_days_zero_when_on_time():
    # ship_date before grace_etd
    result = compute(_base_input(ship_date=date(2025, 6, 5)))
    assert result.etd_grace_overdue_days == 0


def test_payment_to_ship_days():
    # payment=Apr 15, ship=Jun 20 → 66 days
    result = compute(_base_input())
    assert result.payment_to_ship_days == 66


def test_payment_to_request_days():
    # payment=Apr 15, created=Apr 1 → 14 days
    result = compute(_base_input())
    assert result.payment_to_request_days == 14


def test_actual_etd_overdue_when_shipped_late():
    # ship=Jun 20, estimated_etd=Jun 1 → +19 days (accounts-entered actual_etd ignored)
    result = compute(_base_input(actual_etd=date(2025, 6, 20)))
    assert result.actual_etd_overdue_days == 19


def test_actual_etd_overdue_negative_when_shipped_early():
    # ship=May 25, estimated_etd=Jun 1 → −7 days (signed, per client sheet)
    result = compute(_base_input(ship_date=date(2025, 5, 25)))
    assert result.actual_etd_overdue_days == -7


def test_actual_etd_overdue_accrues_while_unshipped():
    etd = date.today() - timedelta(days=40)
    result = compute(_base_input(estimated_etd=etd, ship_date=None))
    assert result.actual_etd_overdue_days == 40


# ── Cost of fund — gated on grace, then retroactive from Est ETD, signed
# (client rule confirmed 2026-07-10: 0 within grace; past grace counts from
# Est ETD itself; early shipment keeps the negative notional gain)


def test_cost_of_fund_shipped_after_grace():
    # estimated_etd = Jun 1, grace ends Jun 11, shipped Jun 20 → past grace,
    # charged retroactively from Est ETD: 19 days (not 9)
    result = compute(_base_input(ship_date=date(2025, 6, 20)))
    assert result.cost_of_fund_applicable is True
    assert result.cost_of_fund_amount == _cof("10000.00", "0.18", 19)


def test_cost_of_fund_client_worked_example():
    # ETD 07-Jun-2026, actual shipment 07-Jul-2026 → 30 delay days from Est ETD.
    result = compute(_base_input(
        deposit_amount=Decimal("2000.00"),
        estimated_etd=date(2026, 6, 7),
        payment_date=date(2026, 5, 1),
        ship_date=date(2026, 7, 7),
    ))
    assert result.grace_etd == date(2026, 6, 17)
    assert result.cost_of_fund_applicable is True
    assert result.cost_of_fund_amount == _cof("2000.00", "0.18", 30)


def test_cost_of_fund_zero_within_grace():
    # Shipped 4 days after ETD — inside the 10-day grace → no charge.
    result = compute(_base_input(ship_date=date(2025, 6, 5)))
    assert result.cost_of_fund_applicable is True
    assert result.cost_of_fund_amount == Decimal("0.00")


def test_cost_of_fund_zero_on_grace_boundary():
    # Shipped exactly on the last grace day (ETD + 10 = Jun 11) → still 0.
    result = compute(_base_input(ship_date=date(2025, 6, 11)))
    assert result.cost_of_fund_amount == Decimal("0.00")


def test_cost_of_fund_charged_one_day_past_grace():
    # Shipped Jun 12 (11 days after ETD) → grace exceeded, charged
    # retroactively from Est ETD: 11 days, not 1.
    result = compute(_base_input(ship_date=date(2025, 6, 12)))
    assert result.cost_of_fund_amount == _cof("10000.00", "0.18", 11)


def test_cost_of_fund_unshipped_zero_within_grace():
    # Unshipped, ETD 5 days ago — grace not yet exceeded → 0 (not negative,
    # not accruing yet).
    etd = date.today() - timedelta(days=5)
    result = compute(_base_input(estimated_etd=etd, ship_date=None))
    assert result.cost_of_fund_applicable is True
    assert result.cost_of_fund_amount == Decimal("0.00")


def test_cost_of_fund_negative_when_shipped_early():
    # Shipped 7 days before ETD → notional GAIN (negative), matching the sheet.
    result = compute(_base_input(ship_date=date(2025, 5, 25)))
    assert result.cost_of_fund_applicable is True
    assert result.cost_of_fund_amount == _cof("10000.00", "0.18", -7)
    assert result.cost_of_fund_amount < 0


def test_cost_of_fund_zero_when_shipped_on_etd():
    result = compute(_base_input(ship_date=date(2025, 6, 1)))
    assert result.cost_of_fund_applicable is True
    assert result.cost_of_fund_amount == Decimal("0.00")


def test_cost_of_fund_unshipped_accrues_to_today():
    # No ship date, Est ETD 40 days in the past → 40 accrued days.
    etd = date.today() - timedelta(days=40)
    result = compute(_base_input(estimated_etd=etd, ship_date=None))
    assert result.cost_of_fund_applicable is True
    assert result.cost_of_fund_amount == _cof("10000.00", "0.18", 40)


def test_no_cost_of_fund_without_payment():
    # Advance not paid yet → no capital locked → no cost of fund, even past grace.
    etd = date.today() - timedelta(days=40)
    result = compute(_base_input(estimated_etd=etd, payment_date=None, ship_date=None))
    assert result.cost_of_fund_applicable is False
    assert result.cost_of_fund_amount == Decimal("0.00")


def test_no_cost_of_fund_without_estimated_etd():
    result = compute(_base_input(estimated_etd=None))
    assert result.cost_of_fund_applicable is False
    assert result.cost_of_fund_amount == Decimal("0.00")


# ── Delay classification ──────────────────────────────────────────────────────


def test_default_status_critical_when_very_overdue():
    # Paid, unshipped, grace ended 50 days ago (> 30) → critical.
    etd = date.today() - timedelta(days=60)
    result = compute(_base_input(estimated_etd=etd, ship_date=None))
    assert result.default_status == "critical"


def test_default_status_delayed_when_moderately_overdue():
    # Paid, unshipped, grace ended 20 days ago (≤ 30) → delayed.
    etd = date.today() - timedelta(days=30)
    result = compute(_base_input(estimated_etd=etd, ship_date=None))
    assert result.default_status == "delayed"


def test_default_status_on_time():
    result = compute(_base_input(ship_date=date(2025, 6, 5)))
    assert result.default_status == "on_time"


def test_default_status_pending_without_etd():
    result = compute(_base_input(estimated_etd=None))
    assert result.default_status == "pending"
