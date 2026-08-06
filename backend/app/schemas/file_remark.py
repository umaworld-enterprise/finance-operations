"""Schemas for the File Remarks module (CIO batch 2, Aug 2026)."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import OrmBase

FileRemarkCategoryLiteral = Literal["invoice_number_change", "invoice_split", "other"]


class FileRemarkCreate(BaseModel):
    deposit_request_id: UUID
    category: FileRemarkCategoryLiteral
    old_file_number: str | None = Field(None, max_length=200)
    new_file_number: str | None = Field(None, max_length=200)
    remark: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_category_fields(self) -> "FileRemarkCreate":
        """Category-specific required fields (per client examples):
        - invoice_number_change: old file number + new file number
        - invoice_split: the file number(s) it splits to
        - other: remark only
        """
        if self.category == "invoice_number_change":
            if not (self.old_file_number and self.old_file_number.strip()):
                raise ValueError("Old file number is required for an invoice number change.")
            if not (self.new_file_number and self.new_file_number.strip()):
                raise ValueError("New file number is required for an invoice number change.")
        if self.category == "invoice_split":
            if not (self.new_file_number and self.new_file_number.strip()):
                raise ValueError(
                    "The file number(s) the invoice splits to is required for an invoice split."
                )
        return self


class FileRemarkResolve(BaseModel):
    """Accounts resolve a remark — the response note is optional and travels
    back to the merchandiser's notification when given."""

    response_note: str | None = None


class FileRemarkResponse(OrmBase):
    id: UUID
    deposit_request_id: UUID
    category: str
    old_file_number: str | None
    new_file_number: str | None
    remark: str
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
