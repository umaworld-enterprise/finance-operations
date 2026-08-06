"""Schemas for master data: Vertical, Customer, Supplier, DefaultedSupplier, User, SystemConfig."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.models.enums import CurrencyCode, UserRole
from app.schemas.common import OrmBase


# ── Payment Terms Master ──────────────────────────────────────────────────────

class PaymentTermCreate(BaseModel):
    label: str = Field(min_length=1, max_length=500)
    sort_order: int = 0

class PaymentTermUpdate(BaseModel):
    label: str | None = Field(None, min_length=1, max_length=500)
    is_active: bool | None = None
    sort_order: int | None = None

class PaymentTermResponse(OrmBase):
    id: UUID
    label: str
    is_active: bool
    sort_order: int


# ── Bank master (Aug 2026) ────────────────────────────────────────────────────

class BankCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    sort_order: int = 0

class BankUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    is_active: bool | None = None
    sort_order: int | None = None

class BankResponse(OrmBase):
    id: UUID
    name: str
    is_active: bool
    sort_order: int


# ── Vertical ─────────────────────────────────────────────────────────────────

class VerticalCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)

class VerticalUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    is_active: bool | None = None

class VerticalResponse(OrmBase):
    id: UUID
    name: str
    is_active: bool
    created_at: datetime


# ── Customer ─────────────────────────────────────────────────────────────────

class CustomerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)

class CustomerUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    is_active: bool | None = None

class CustomerResponse(OrmBase):
    id: UUID
    name: str
    is_active: bool
    created_at: datetime


# ── Supplier ─────────────────────────────────────────────────────────────────

class SupplierCreate(BaseModel):
    supplier_code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=200)
    country: str | None = None

class SupplierUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    country: str | None = None
    is_active: bool | None = None
    fixed_deposit_amount: Decimal | None = None

class SupplierResponse(OrmBase):
    id: UUID
    supplier_code: str
    name: str
    country: str | None
    is_active: bool
    fixed_deposit_amount: Decimal | None = None


# ── Defaulted Supplier ────────────────────────────────────────────────────────

class DefaultedSupplierCreate(BaseModel):
    supplier_id: UUID
    outstanding_amount: Decimal = Field(gt=0)
    currency: CurrencyCode = CurrencyCode.USD
    default_reason: str = Field(min_length=5)
    flagged_date: date

class DefaultedSupplierResponse(OrmBase):
    id: UUID
    supplier_id: UUID
    supplier_name: str = ""
    outstanding_amount: Decimal
    currency: CurrencyCode
    default_reason: str
    flagged_date: date
    is_active: bool
    resolved_date: date | None = None

    model_config = OrmBase.model_config.copy()

    @classmethod
    def from_orm_obj(cls, obj) -> "DefaultedSupplierResponse":  # type: ignore[no-untyped-def]
        return cls(
            id=obj.id,
            supplier_id=obj.supplier_id,
            supplier_name=obj.supplier.name if obj.supplier else "",
            outstanding_amount=obj.outstanding_amount,
            currency=obj.currency,
            default_reason=obj.default_reason,
            flagged_date=obj.flagged_date,
            is_active=obj.is_active,
            resolved_date=obj.resolved_date,
        )


# ── Supplier Default Status (for form validation) ─────────────────────────────

class SupplierDefaultStatusResponse(BaseModel):
    supplier_id: UUID
    is_defaulted: bool
    outstanding_amount: Decimal | None = None
    currency: CurrencyCode | None = None
    default_reason: str | None = None


# ── User ─────────────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=200)
    role: UserRole

class UserUpdate(BaseModel):
    full_name: str | None = Field(None, min_length=1, max_length=200)
    role: UserRole | None = None
    is_active: bool | None = None
    ai_access_enabled: bool | None = None

class UserResponse(OrmBase):
    id: UUID
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    ai_access_enabled: bool = False
    last_login_at: datetime | None = None
    created_at: datetime


# ── System Config ─────────────────────────────────────────────────────────────

class SystemConfigUpdate(BaseModel):
    config_value: str
    description: str | None = None

class SystemConfigResponse(OrmBase):
    id: UUID
    config_key: str
    config_value: str
    description: str | None
    updated_at: datetime
