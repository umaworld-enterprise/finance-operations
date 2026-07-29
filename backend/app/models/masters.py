"""ORM models for master data: Vertical, Customer, Supplier, User, SystemConfig."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import UserRole, pg_enum


class Vertical(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "verticals"

    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    deposit_requests: Mapped[list["DepositRequest"]] = relationship(back_populates="vertical")


class Customer(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "customers"

    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    deposit_requests: Mapped[list["DepositRequest"]] = relationship(back_populates="customer")


class Supplier(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "suppliers"

    supplier_code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    fixed_deposit_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)

    deposit_requests: Mapped[list["DepositRequest"]] = relationship(back_populates="supplier")
    default_flags: Mapped[list["DefaultedSupplier"]] = relationship(back_populates="supplier")


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[UserRole] = mapped_column(pg_enum(UserRole, "user_role"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ai_access_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    secondary_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    department: Mapped[str | None] = mapped_column(String(100), nullable=True)
    onboarding_completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    font_size: Mapped[str] = mapped_column(String(16), nullable=False, default="default")

    # Relationships
    created_requests: Mapped[list["DepositRequest"]] = relationship(
        back_populates="creator", foreign_keys="DepositRequest.created_by"
    )
    deleted_requests: Mapped[list["DepositRequest"]] = relationship(
        back_populates="deleter", foreign_keys="DepositRequest.deleted_by"
    )
    flags_raised: Mapped[list["DefaultedSupplier"]] = relationship(
        back_populates="flagged_by_user", foreign_keys="DefaultedSupplier.flagged_by"
    )
    flags_resolved: Mapped[list["DefaultedSupplier"]] = relationship(
        back_populates="resolved_by_user", foreign_keys="DefaultedSupplier.resolved_by"
    )
    merchandiser_actions: Mapped[list["MerchandiserAction"]] = relationship(
        back_populates="performer"
    )
    accounts_actions: Mapped[list["AccountsAction"]] = relationship(back_populates="performer")
    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="changed_by_user")
    payment_updates: Mapped[list["PaymentDetails"]] = relationship(back_populates="updated_by_user")
    status_changes: Mapped[list["StatusHistory"]] = relationship(back_populates="changed_by_user")
    config_updates: Mapped[list["SystemConfig"]] = relationship(back_populates="updated_by_user")


class SystemConfig(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "system_config"

    config_key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    config_value: Mapped[str] = mapped_column(nullable=False)
    description: Mapped[str | None] = mapped_column(nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    updated_by_user: Mapped[User | None] = relationship(back_populates="config_updates")


class PaymentTermsMaster(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "payment_terms_master"

    label: Mapped[str] = mapped_column(String(500), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(nullable=False, default=0)


class FormLink(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "form_links"

    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    creator: Mapped[User | None] = relationship(foreign_keys=[created_by])


# Deferred imports to avoid circular deps — resolved at module load time
from app.models.deposit_request import DepositRequest  # noqa: E402, F401
from app.models.workflow import AccountsAction, MerchandiserAction, StatusHistory  # noqa: E402, F401
from app.models.audit import AuditLog  # noqa: E402, F401
from app.models.integrations import DefaultedSupplier  # noqa: E402, F401
from app.models.payment import PaymentDetails  # noqa: E402, F401
