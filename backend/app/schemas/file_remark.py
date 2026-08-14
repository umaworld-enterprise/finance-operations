"""Schemas for the File Remarks module (CIO batch 2, Aug 2026; reworked 4 Aug:
two categories only, amounts included, dynamic split targets, remark optional)."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import OrmBase

FileRemarkCategoryLiteral = Literal["invoice_split", "invoice_amount_change"]


class SplitTarget(BaseModel):
    """One 'file splits to' row: new file number + the amount going to it."""

    file_number: str = Field(min_length=1, max_length=200)
    amount: Decimal = Field(gt=0)


class FileRemarkCreate(BaseModel):
    deposit_request_id: UUID
    category: FileRemarkCategoryLiteral
    # Invoice amount change: new file + amount. Neither the OLD file number
    # nor the OLD amount are accepted from the client (10 Aug rework) — both
    # are server-derived from the selected file (its invoice number and its
    # deposit_amount), so every remark carries its parent file reference.
    new_file_number: str | None = Field(None, max_length=200)
    new_amount: Decimal | None = Field(None, gt=0)
    # Split Invoices: dynamic target rows.
    split_targets: list[SplitTarget] | None = None
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
            missing = [
                label
                for value, label in (
                    (self.new_file_number, "New file number"),
                    (self.new_amount, "New file amount"),
                )
                if value in (None, "") or (isinstance(value, str) and not value.strip())
            ]
            if missing:
                raise ValueError(
                    f"{', '.join(missing)} required for an invoice amount change."
                )
        return self


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
    supplier_name: str | None = None
    created_by_name: str | None = None
    resolved_by_name: str | None = None
