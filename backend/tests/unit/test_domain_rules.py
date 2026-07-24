"""Unit tests for supplier validation and lock rules."""

from decimal import Decimal

import pytest

from app.core.exceptions import RecordLockedError, SupplierDefaultedError
from app.domain.rules.lock_rules import assert_record_not_locked
from app.domain.rules.supplier_validation import DefaultedSupplierInfo, assert_supplier_not_defaulted
from app.models.enums import CurrencyCode, UserRole


def test_defaulted_supplier_blocks_submission():
    info = DefaultedSupplierInfo(
        supplier_name="Acme Corp",
        outstanding_amount=Decimal("50000.00"),
        currency=CurrencyCode.USD,
        default_reason="Non-delivery on past order",
    )
    with pytest.raises(SupplierDefaultedError) as exc_info:
        assert_supplier_not_defaulted(info)
    assert "Acme Corp" in exc_info.value.message


def test_non_defaulted_supplier_passes():
    assert_supplier_not_defaulted(None)  # should not raise


def test_locked_record_blocks_non_super_admin():
    with pytest.raises(RecordLockedError):
        assert_record_not_locked(is_locked=True, role=UserRole.ACCOUNTS_TEAM)


def test_locked_record_blocks_merchandiser():
    with pytest.raises(RecordLockedError):
        assert_record_not_locked(is_locked=True, role=UserRole.MERCHANDISER)


def test_super_admin_can_override_lock():
    assert_record_not_locked(is_locked=True, role=UserRole.SUPER_ADMIN)  # no raise


def test_unlocked_record_always_passes():
    for role in UserRole:
        assert_record_not_locked(is_locked=False, role=role)
