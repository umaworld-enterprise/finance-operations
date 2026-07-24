"""Unit tests for the preferences schema."""

import pytest
from pydantic import ValidationError

from app.schemas.auth import PreferencesUpdate


def test_valid_font_sizes():
    for value in ("default", "large", "xlarge"):
        assert PreferencesUpdate(font_size=value).font_size == value


def test_invalid_font_size_rejected():
    with pytest.raises(ValidationError):
        PreferencesUpdate(font_size="huge")


def test_font_size_required():
    with pytest.raises(ValidationError):
        PreferencesUpdate()
