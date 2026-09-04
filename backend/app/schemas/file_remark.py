"""Schemas for the File Remarks module (CIO batch 2, Aug 2026; reworked 4 Aug:
two categories only, amounts included, dynamic split targets, remark optional)."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import OrmBase

FileRemarkCategoryLiteral = Literal[
    "invoice_split", "invoice_amount_change", "invoice_value_change"
]


class SplitTarget(BaseModel):
    """One 'file splits to' row: new file number + the amount going to it."""

    file_number: str = Field(min_length=1, max_length=200)
    amount: Decimal = Field(gt=0)


class FileRemarkCreate(BaseModel):
    deposit_request_id: UUID
    category: FileRemarkCategoryLiteral
    # The selected FILE within the request (19 Aug 2026 chain support): the
    # root file, or a live file born from an approved split / invoice change
    # on this request. Omitted → the request's root file (legacy behaviour).
    # The server validates it against the request's LIVE file set and derives
    # the old amount from that file.
    file_number: str | None = Field(None, max_length=200)
    # Invoice Change: new file number only. Neither the OLD file/amount (10
    # Aug rework) nor the NEW amount (19 Aug: a whole-invoice change keeps
    # the amount — pre-filled and locked in the UI) are accepted from the
    # client; all three are server-derived from the selected file.
    new_file_number: str | None = Field(None, max_length=200)
    # Split Invoices: dynamic target rows.
    split_targets: list[SplitTarget] | None = None
    # Invoice Value Change (4 Sep 2026): the amount the merchandiser proposes.
    # The final revised amount is applied by Accounts after approval.
    proposed_amount: Decimal | None = Field(None, gt=0)
    # Optional — the structured fields carry the instruction.
    remark: str | None = None

    @model_validator(mode="after")
    def validate_category_fields(self) -> "FileRemarkCreate":
        if self.category == "invoice_split":
            if not self.split_targets:
                raise ValueError(
                    "At least one 'file splits to' row (new file number + amount) is required."
                )
        if self.category == "invoice_amount_change":
            if not (self.new_file_number or "").strip():
                raise ValueError("New file number required for an invoice change.")
        if self.category == "invoice_value_change" and self.proposed_amount is None:
            raise ValueError("A proposed new amount is required for an invoice value change.")
        return self


class FileRemarkAmountUpdate(BaseModel):
    """Accounts apply the final revised amount on an APPROVED Invoice Value
    Change (4 Sep 2026) — a separate step after approval; the merchandiser's
    proposed amount pre-fills the UI but Accounts decide the figure."""

    revised_amount: Decimal = Field(gt=0)


class FileRemarkDecide(BaseModel):
    """Accounts approve or reject a remark (UAT Aug 2026, item 14). The note
    is optional on approval and mandatory on rejection (service-enforced);
    it travels back in the merchandiser's notification when given."""

    response_note: str | None = None


class FileRemarkResponse(OrmBase):
    id: UUID
    deposit_request_id: UUID
    category: str
    old_file_number: str | None
    old_amount: Decimal | None
    new_file_number: str | None
    new_amount: Decimal | None
    proposed_amount: Decimal | None = None
    split_targets: list[dict] | None
    remark: str | None
    status: str
    created_by: UUID
    created_at: datetime
    resolved_by: UUID | None
    resolved_at: datetime | None
    response_note: str | None
    # Context — filled by the service from joined rows.
    request_number: str | None = None
    # The parent file's CURRENT sunshine invoice number — preferred for the
    # "From {parent}" display (10 Aug: rows created before the derived
    # parent, or whose invoice number was edited later, still show it).
    sunshine_invoice_number: str | None = None
    supplier_name: str | None = None
    # The request's currency — display alongside every amount (19 Aug 2026).
    currency: str | None = None
    created_by_name: str | None = None
    resolved_by_name: str | None = None
