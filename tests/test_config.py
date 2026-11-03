"""Unit tests for configuration models and template store."""

from pathlib import Path

import pytest

from seamus.config.models import (
    AgentConfig,
    InferenceConfig,
    InferenceFormat,
    TodoImplementation,
)
from seamus.config.settings import (
    SystemSettings,
    SystemSettingsStore,
    resolve_skill_path,
)
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
        system_prompt="Base prompt",
        todo_implementation=TodoImplementation.NONE,
    )
    overrides = AgentConfig(
        inference=InferenceConfig(api_key="overridden-key"),
        model_name="custom/model",
        system_prompt="Overridden prompt",
        todo_implementation=TodoImplementation.DEEPAGENTS,
    )
    derived = base.copy_with_overrides(overrides)

    assert derived.inference.api_key == "overridden-key"
    assert derived.model_name == "custom/model"
    assert derived.system_prompt == "Overridden prompt"
    assert derived.todo_implementation == TodoImplementation.DEEPAGENTS
    # Ensure original base was not mutated
    assert base.inference.api_key == "base-key"
    assert base.model_name == "openai/gpt-oss-120b"
    assert base.system_prompt == "Base prompt"
    assert base.todo_implementation == TodoImplementation.NONE


def test_agent_config_todo_implementation_validation() -> None:
    from pydantic import ValidationError

    cfg = AgentConfig()
    assert cfg.todo_implementation == TodoImplementation.NONE

    cfg_deep = AgentConfig(todo_implementation=TodoImplementation.DEEPAGENTS)
    assert cfg_deep.todo_implementation == TodoImplementation.DEEPAGENTS

    cfg_from_str = AgentConfig.model_validate({"todo_implementation": "deepagents"})
    assert cfg_from_str.todo_implementation == TodoImplementation.DEEPAGENTS

    cfg_none_str = AgentConfig.model_validate({"todo_implementation": "none"})
    assert cfg_none_str.todo_implementation == TodoImplementation.NONE

    with pytest.raises(ValidationError):
        AgentConfig.model_validate({"todo_implementation": "unsupported_value"})


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


def test_system_settings_defaults_and_crud() -> None:
    settings = SystemSettings()
    assert settings.skill_directories == ["~/.seamus/skills", "~/.skills"]

    store = SystemSettingsStore(initial_settings=settings)
    assert store.get_settings().skill_directories == ["~/.seamus/skills", "~/.skills"]

    updated = store.set_settings(
        SystemSettings(skill_directories=["/opt/skills", "~/custom-skills"])
    )
    assert updated.skill_directories == ["/opt/skills", "~/custom-skills"]
    assert store.get_settings().skill_directories == ["/opt/skills", "~/custom-skills"]


def test_resolve_skill_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_home = tmp_path / "user_home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.delenv("SEAMUS_HOST_HOME", raising=False)

    existing_dir = fake_home / ".skills"
    existing_dir.mkdir()
    file_path = fake_home / "some_file.txt"
    file_path.write_text("hello")

    # Valid existing dir with ~
    resolved = resolve_skill_path("~/.skills")
    assert resolved == existing_dir.resolve()

    # Missing dir returns None
    assert resolve_skill_path("~/.nonexistent") is None

    # File rather than directory returns None
    assert resolve_skill_path("~/some_file.txt") is None

    # Empty or whitespace returns None
    assert resolve_skill_path("") is None
    assert resolve_skill_path("   ") is None

    # SEAMUS_HOST_HOME override for container environments
    container_host_home = tmp_path / "host_home"
    container_skills = container_host_home / ".seamus" / "skills"
    container_skills.mkdir(parents=True)
    monkeypatch.setenv("SEAMUS_HOST_HOME", str(container_host_home))

    assert resolve_skill_path("~/.seamus/skills") == container_skills.resolve()
    assert resolve_skill_path("~") == container_host_home.resolve()
