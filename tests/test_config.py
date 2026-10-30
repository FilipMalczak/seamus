"""Unit tests for configuration models and template store."""

import pytest

from seamus.config.models import AgentConfig, InferenceConfig, InferenceFormat
from seamus.config.template import ConfigTemplateStore


def test_inference_config_defaults() -> None:
    cfg = InferenceConfig()
    assert cfg.format == InferenceFormat.OPENAI
    assert cfg.base_url == "https://openrouter.ai/api/v1"
    assert cfg.api_key is None
    assert cfg.is_complete() is False


def test_agent_config_completeness() -> None:
    incomplete = AgentConfig()
    assert incomplete.is_complete() is False
    with pytest.raises(ValueError, match="incomplete"):
        incomplete.validate_complete()

    complete = AgentConfig(
        inference=InferenceConfig(
            format=InferenceFormat.OPENAI,
            base_url="https://openrouter.ai/api/v1",
            api_key="sk-test-key",
        ),
        model_name="openai/gpt-oss-120b",
    )
    assert complete.is_complete() is True
    # Should not raise
    complete.validate_complete()


def test_agent_config_copy_with_overrides() -> None:
    base = AgentConfig(
        inference=InferenceConfig(api_key="base-key"),
        model_name="openai/gpt-oss-120b",
    )
    overrides = AgentConfig(
        inference=InferenceConfig(api_key="overridden-key"),
        model_name="custom/model",
    )
    derived = base.copy_with_overrides(overrides)

    assert derived.inference.api_key == "overridden-key"
    assert derived.model_name == "custom/model"
    # Ensure original base was not mutated
    assert base.inference.api_key == "base-key"
    assert base.model_name == "openai/gpt-oss-120b"


def test_config_template_store_crud() -> None:
    store = ConfigTemplateStore(
        initial_template=AgentConfig(
            inference=InferenceConfig(api_key="initial-key"),
            model_name="test-model",
        )
    )
    current = store.get_template()
    assert current.inference.api_key == "initial-key"
    assert current.model_name == "test-model"

    # Update template with full object and clearing api_key
    new_template = AgentConfig(
        inference=InferenceConfig(
            format=InferenceFormat.OPENAI,
            base_url="https://api.openai.com/v1",
            api_key=None,
        ),
        model_name="gpt-4o",
    )
    updated = store.set_template(new_template)
    assert updated.inference.api_key is None
    assert updated.inference.base_url == "https://api.openai.com/v1"
    assert updated.model_name == "gpt-4o"
    assert updated.is_complete() is False
