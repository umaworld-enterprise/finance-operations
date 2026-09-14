"""Golden-fixture test: Cost of Fund vs the client's own spreadsheet.

The rows below are real cached values lifted from the client's
"Sunshine Deposits Analysis V2-PWA" workbook (downloaded 2026-07-10).
The sheet computes AF = deposit × 12% × ((ship or TODAY) − Est ETD) / 365,
signed, with TODAY frozen at 2026-07-10 in the cached snapshot.

Our engine must reproduce the sheet's AE (Actual ETD Overdue Days) column
AND the AF (Cost of Fund) column exactly. The 10 Jul divergence (zero for
rows shipped within grace) was REMOVED by the client's final formulas of
2 Sep 2026: AF = IF(AND(paid, TODAY() > Grace ETD), deposit × 12%/365 × AE)
— so shipped-within-grace rows carry their small charge and early shipments
their negative notional gain, once TODAY has crossed the Grace ETD (true
for every cached row at the frozen sheet date).
"""

from datetime import date
from decimal import Decimal

import pytest

import app.analytics.engine as engine_module
from app.analytics.engine import AnalyticsInput, compute

SHEET_TODAY = date(2026, 7, 10)  # serial 46213 cached in the workbook

# (deposit, est_etd, payment_date, ship_date, sheet_AE_days, sheet_AF_cof)
GOLDEN_ROWS = [
    # shipped late (positive CoF)
    ("6955.425", date(2026, 1, 31), date(2025, 12, 16), date(2026, 3, 31), 59, "134.92"),
    ("4742.4", date(2025, 12, 31), date(2025, 12, 16), date(2026, 2, 23), 54, "84.19"),
    ("6164.0", date(2026, 1, 16), date(2026, 1, 5), date(2026, 2, 25), 40, "81.06"),
    ("49059.0", date(2026, 1, 16), date(2026, 1, 5), date(2026, 2, 8), 23, "370.97"),
    # shipped late but WITHIN the 10-day grace → the sheet's own values apply
    # since the 2 Sep 2026 final formulas (the 10 Jul zero-divergence is gone)
    ("8424.0", date(2026, 1, 15), date(2025, 12, 12), date(2026, 1, 25), 10, "27.70"),
    ("8424.0", date(2026, 1, 30), date(2025, 12, 12), date(2026, 2, 4), 5, "13.85"),
    # shipped early (negative CoF = notional gain)
    ("5832.0", date(2026, 1, 15), date(2025, 12, 12), date(2025, 12, 23), -23, "-44.10"),
    ("10272.80", date(2026, 1, 31), date(2025, 12, 16), date(2025, 12, 23), -39, "-131.72"),
    ("7384.14", date(2026, 1, 31), date(2025, 12, 16), date(2026, 1, 27), -4, "-9.71"),
    ("3744.20", date(2026, 1, 31), date(2026, 1, 7), date(2026, 1, 30), -1, "-1.23"),
    ("16552.5", date(2026, 1, 15), date(2025, 12, 19), date(2025, 12, 29), -17, "-92.51"),
    ("12972.0", date(2026, 4, 20), date(2026, 1, 7), date(2026, 4, 2), -18, "-76.77"),
    # shipped exactly on ETD
    ("7446.13", date(2025, 12, 31), date(2025, 12, 12), date(2025, 12, 31), 0, "0.00"),
    ("21652.0", date(2025, 11, 14), date(2025, 12, 19), date(2025, 11, 14), 0, "0.00"),
    # unshipped — accrues to the sheet's TODAY (2026-07-10)
    ("244000.0", date(2026, 2, 28), date(2026, 1, 7), None, 132, "10588.93"),
    ("25376.0", date(2026, 2, 28), date(2026, 1, 7), None, 132, "1101.25"),
    ("30294.0", date(2026, 1, 5), date(2026, 1, 7), None, 186, "1852.50"),
    ("10458.0", date(2026, 4, 4), date(2026, 1, 8), None, 97, "333.51"),
]


class _FrozenDate(date):
    @classmethod
    def today(cls):
        return cls(SHEET_TODAY.year, SHEET_TODAY.month, SHEET_TODAY.day)


@pytest.fixture()
def frozen_today(monkeypatch):
    monkeypatch.setattr(engine_module, "date", _FrozenDate)


@pytest.mark.parametrize("deposit,est_etd,payment,ship,sheet_ae,sheet_af", GOLDEN_ROWS)
def test_matches_client_sheet(frozen_today, deposit, est_etd, payment, ship, sheet_ae, sheet_af):
    result = compute(AnalyticsInput(
        deposit_request_id="golden",
        estimated_etd=est_etd,
        created_at=payment,  # not asserted here
        deposit_amount=Decimal(deposit),
        payment_date=payment,
        ship_date=ship,
        actual_etd=None,
        etd_grace_days=10,
        cost_of_fund_rate=0.12,
        cost_of_fund_grace_days=30,  # must be ignored by the engine
    ))
    assert result.actual_etd_overdue_days == sheet_ae
    assert result.cost_of_fund_applicable is True
    # sheet values were rounded to 2dp when extracting — allow 1 cent tolerance
    assert abs(result.cost_of_fund_amount - Decimal(sheet_af)) <= Decimal("0.01")
