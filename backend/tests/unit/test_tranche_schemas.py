"""Schema-level validation for tranches and tranche-bearing request creates."""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.models.tranche import tranche_label
from app.schemas.deposit_request import DepositRequestCreate
from app.schemas.tranche import TrancheCreate

BASE = {
    "supplier_id": str(uuid.uuid4()),
    "customer_id": str(uuid.uuid4()),
    "total_supplier_invoice_amount": Decimal("10000.00"),
}


def _tranche(amount: str, day: int = 1) -> dict:
    return {"amount": Decimal(amount), "tentative_payment_date": date(2026, 8, day)}


def test_tranche_labels_are_roman():
    assert tranche_label(1) == "Deposit - Tranche I"
    assert tranche_label(2) == "Deposit - Tranche II"
    assert tranche_label(3) == "Deposit - Tranche III"
    assert tranche_label(4) == "Deposit - Tranche IV"
    assert tranche_label(9) == "Deposit - Tranche IX"


def test_tranche_requires_positive_amount():
    with pytest.raises(ValidationError):
        TrancheCreate(amount=Decimal("0"), tentative_payment_date=date(2026, 8, 1))
    with pytest.raises(ValidationError):
        TrancheCreate(amount=Decimal("-5"), tentative_payment_date=date(2026, 8, 1))


def test_tranche_requires_two_decimal_precision():
    with pytest.raises(ValidationError):
        TrancheCreate(amount=Decimal("10.001"), tentative_payment_date=date(2026, 8, 1))
    ok = TrancheCreate(amount=Decimal("10.10"), tentative_payment_date=date(2026, 8, 1))
    assert ok.amount == Decimal("10.10")


def test_tranche_requires_tentative_date():
    with pytest.raises(ValidationError):
        TrancheCreate(amount=Decimal("10.00"))  # type: ignore[call-arg]


def test_create_derives_deposit_amount_from_tranches():
    payload = DepositRequestCreate(
        **BASE, tranches=[_tranche("3000.00"), _tranche("2000.00", day=15)]
    )
    assert payload.deposit_amount == Decimal("5000.00")


def test_create_rejects_tranches_exceeding_invoice_total():
    with pytest.raises(ValidationError, match="cannot exceed"):
        DepositRequestCreate(
            **BASE, tranches=[_tranche("8000.00"), _tranche("3000.00", day=15)]
        )


def test_create_requires_deposit_amount_or_tranches():
    with pytest.raises(ValidationError, match="deposit_amount or tranches"):
        DepositRequestCreate(**BASE)


def test_create_without_tranches_keeps_legacy_shape():
    payload = DepositRequestCreate(**BASE, deposit_amount=Decimal("1500.00"))
    assert payload.deposit_amount == Decimal("1500.00")
    assert payload.tranches is None
