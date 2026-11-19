"""Unit tests for SystemSettings models, batch size defaults, and validation."""

import pytest
from pydantic import ValidationError

from seamus.config.settings import SystemSettings, SystemSettingsStore


def test_system_settings_defaults() -> None:
    settings = SystemSettings()
    assert settings.api_batch_size == 50
    assert settings.ui_batch_size == 200
    assert settings.memory_batch_size == 300


def test_system_settings_validation_constraints() -> None:
    # Valid custom settings
    valid = SystemSettings(api_batch_size=20, ui_batch_size=100, memory_batch_size=150)
    assert valid.api_batch_size == 20
    assert valid.ui_batch_size == 100
    assert valid.memory_batch_size == 150

    # Equal is allowed
    equal = SystemSettings(api_batch_size=50, ui_batch_size=50, memory_batch_size=50)
    assert equal.api_batch_size == 50

    # api_batch_size > ui_batch_size fails
    with pytest.raises(ValidationError) as exc:
        SystemSettings(api_batch_size=250, ui_batch_size=200, memory_batch_size=300)
    assert "api_batch_size (250) cannot exceed ui_batch_size (200)" in str(exc.value)

    # ui_batch_size > memory_batch_size fails
    with pytest.raises(ValidationError) as exc:
        SystemSettings(api_batch_size=50, ui_batch_size=400, memory_batch_size=300)
    assert "ui_batch_size (400) cannot exceed memory_batch_size (300)" in str(exc.value)


def test_system_settings_store_update() -> None:
    store = SystemSettingsStore(initial_settings=SystemSettings())
    updated = store.set_settings(
        SystemSettings(api_batch_size=40, ui_batch_size=150, memory_batch_size=250)
    )
    assert updated.api_batch_size == 40
    assert store.get_settings().ui_batch_size == 150
