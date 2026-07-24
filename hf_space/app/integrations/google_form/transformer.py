"""Transform raw Google Form payload into DepositRequestCreate schema."""

from datetime import date
from decimal import Decimal

from app.core.exceptions import ValidationError
from app.models.enums import CurrencyCode, SubmissionSource
from app.schemas.deposit_request import DepositRequestCreate

# Maps Google Form question titles → internal field names.
# Update question titles here if the Google Form changes.
_FIELD_MAP: dict[str, str] = {
    "Sunshine Invoice Number": "sunshine_invoice_number",
    "Vertical / Category": "_vertical_name",          # resolved to UUID by handler
    "Customer": "_customer_name",                      # resolved to UUID by handler
    "Supplier": "_supplier_name",                      # resolved to UUID by handler
    "Supplier Invoice Number": "supplier_invoice_number",
    "Total Supplier Proforma Invoice Amount": "total_supplier_invoice_amount",
    "Deposit Advance Percentage": "deposit_percentage",
    "Currency of Advance Deposit": "currency",
    "Estimated Shipment Date": "estimated_shipment_date",
    "Remarks": "remarks",
}


def extract_raw_fields(payload: dict) -> dict[str, str]:
    """
    Extract question→answer pairs from the Google Form webhook payload.
    Returns a flat dict keyed by internal field name.
    """
    items = payload.get("items", [])
    raw: dict[str, str] = {}
    for item in items:
        question = item.get("question", "").strip()
        answer = item.get("answer", "")
        if question in _FIELD_MAP:
            raw[_FIELD_MAP[question]] = answer if isinstance(answer, str) else str(answer)
    return raw


def parse_date(value: str) -> date:
    """Parse date strings in common formats."""
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"):
        try:
            from datetime import datetime
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    raise ValidationError(f"Cannot parse date: {value!r}")


def to_deposit_request_create(
    raw: dict[str, str],
    supplier_id,
    customer_id,
    vertical_id,
) -> DepositRequestCreate:
    """
    Convert raw extracted fields + resolved UUIDs into a DepositRequestCreate.
    Raises ValidationError if required fields are missing or malformed.
    """
    try:
        currency_str = raw.get("currency", "USD").strip().upper()
        try:
            currency = CurrencyCode(currency_str)
        except ValueError:
            currency = CurrencyCode.OTHER

        total_amount_str = raw.get("total_supplier_invoice_amount", "0").replace(",", "").strip()
        pct_str = raw.get("deposit_percentage", "0").replace("%", "").strip()

        total_amount = Decimal(total_amount_str)
        pct = Decimal(pct_str)
        deposit_amount = (total_amount * pct / Decimal("100")).quantize(Decimal("0.01"))

        return DepositRequestCreate(
            supplier_id=supplier_id,
            customer_id=customer_id,
            vertical_id=vertical_id,
            sunshine_invoice_number=raw.get("sunshine_invoice_number"),
            supplier_invoice_number=raw.get("supplier_invoice_number"),
            currency=currency,
            deposit_amount=deposit_amount,
            deposit_percentage=pct,
            total_supplier_invoice_amount=total_amount,
            estimated_shipment_date=parse_date(raw.get("estimated_shipment_date", "")),
            remarks=raw.get("remarks"),
        )
    except (KeyError, Exception) as exc:
        raise ValidationError(f"Google Form payload transformation failed: {exc}") from exc
