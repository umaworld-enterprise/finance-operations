"""Business rule: block requests for defaulted suppliers."""

from dataclasses import dataclass
from decimal import Decimal

from app.core.exceptions import SupplierDefaultedError
from app.models.enums import CurrencyCode


@dataclass(frozen=True)
class DefaultedSupplierInfo:
    supplier_name: str
    outstanding_amount: Decimal
    currency: CurrencyCode
    default_reason: str


def assert_supplier_not_defaulted(info: DefaultedSupplierInfo | None) -> None:
    """
    Raise SupplierDefaultedError if the supplier has an active default flag.
    Pass None if the supplier is not defaulted (no-op).
    """
    if info is not None:
        raise SupplierDefaultedError(
            message=(
                f"Supplier '{info.supplier_name}' is on the defaulted supplier list. "
                "Request cannot be submitted until the Finance Team resolves the flag."
            ),
            detail=(
                f"Outstanding amount: {info.currency.value} {info.outstanding_amount:,.2f}. "
                f"Reason: {info.default_reason}"
            ),
        )
