"""ETD validation (21 Sep 2026, executive request): on a NEW request the
Estimated Time of Departure must be tomorrow or later. Updates are exempt —
legacy requests carry past ETDs and editing them must not be blocked."""

from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.deposit_request import DepositRequestCreate, DepositRequestUpdate


def _payload(**overrides):
    base = dict(
        supplier_id=uuid4(),
        customer_id=uuid4(),
        total_supplier_invoice_amount=Decimal("10000.00"),
        deposit_amount=Decimal("1000.00"),
    )
    base.update(overrides)
    return base


def test_create_rejects_past_and_today_etd():
    for bad in (date.today(), date.today() - timedelta(days=1)):
        with pytest.raises(ValidationError, match="tomorrow or later"):
            DepositRequestCreate(**_payload(estimated_etd=bad))


def test_create_accepts_tomorrow_and_missing_etd():
    ok = DepositRequestCreate(**_payload(estimated_etd=date.today() + timedelta(days=1)))
    assert ok.estimated_etd == date.today() + timedelta(days=1)
    assert DepositRequestCreate(**_payload()).estimated_etd is None


def test_update_still_accepts_any_etd():
    upd = DepositRequestUpdate(estimated_etd=date.today() - timedelta(days=30))
    assert upd.estimated_etd == date.today() - timedelta(days=30)
