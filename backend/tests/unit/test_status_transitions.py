"""Unit tests for the status transition state machine."""

import pytest

from app.core.exceptions import InvalidStatusTransitionError
from app.domain.rules.status_transitions import assert_transition_allowed
from app.models.enums import RequestStatus, UserRole


def test_merchandiser_can_hold_own_pending_request():
    assert_transition_allowed(
        RequestStatus.PENDING_PAYMENT,
        RequestStatus.HOLD_BY_MERCHANDISER,
        UserRole.MERCHANDISER,
    )


def test_merchandiser_can_cancel_pending_request():
    assert_transition_allowed(
        RequestStatus.PENDING_PAYMENT,
        RequestStatus.CANCELLED_BY_MERCHANDISER,
        UserRole.MERCHANDISER,
    )


def test_accounts_can_hold_pending_request():
    assert_transition_allowed(
        RequestStatus.PENDING_PAYMENT,
        RequestStatus.HOLD_BY_ACCOUNTS,
        UserRole.ACCOUNTS_TEAM,
    )


def test_accounts_can_process_payment():
    assert_transition_allowed(
        RequestStatus.PENDING_PAYMENT,
        RequestStatus.PAYMENT_PROCESSED,
        UserRole.ACCOUNTS_TEAM,
    )


def test_merchandiser_cannot_process_payment():
    with pytest.raises(InvalidStatusTransitionError):
        assert_transition_allowed(
            RequestStatus.PENDING_PAYMENT,
            RequestStatus.PAYMENT_PROCESSED,
            UserRole.MERCHANDISER,
        )


def test_accounts_can_reopen_cancelled_by_accounts():
    assert_transition_allowed(
        RequestStatus.CANCELLED_BY_ACCOUNTS,
        RequestStatus.REOPENED,
        UserRole.ACCOUNTS_TEAM,
    )


def test_merchandiser_cannot_reopen():
    with pytest.raises(InvalidStatusTransitionError):
        assert_transition_allowed(
            RequestStatus.CANCELLED_BY_ACCOUNTS,
            RequestStatus.REOPENED,
            UserRole.MERCHANDISER,
        )


def test_super_admin_can_do_any_allowed_transition():
    assert_transition_allowed(
        RequestStatus.PENDING_PAYMENT,
        RequestStatus.PAYMENT_PROCESSED,
        UserRole.SUPER_ADMIN,
    )


def test_invalid_transition_raises():
    with pytest.raises(InvalidStatusTransitionError):
        assert_transition_allowed(
            RequestStatus.PAYMENT_PROCESSED,
            RequestStatus.PENDING_PAYMENT,
            UserRole.SUPER_ADMIN,
        )
