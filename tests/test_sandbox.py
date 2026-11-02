"""Unit tests for OpenSandbox integration, runtime API key management, and system prompt."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from langchain_opensandbox import OpenSandboxBackend

from seamus.config.models import AgentConfig, InferenceConfig
from seamus.domain.entities import Agent
from seamus.harness.runner import SessionAgentRunner
from seamus.harness.sandbox import (
    SandboxSettings,
    SeamusOpenSandboxBackend,
    build_sandbox_system_prompt,
    get_or_create_sandbox_api_key,
)


def _make_execution(
    *,
    stdout: str = "",
    stderr: str = "",
    exit_code: int | None = 0,
) -> SimpleNamespace:
    logs = SimpleNamespace(
        stdout=[SimpleNamespace(text=stdout)] if stdout else [],
        stderr=[SimpleNamespace(text=stderr)] if stderr else [],
    )
    return SimpleNamespace(logs=logs, exit_code=exit_code)


def test_get_or_create_sandbox_api_key_autogenerates_and_reuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OPENSANDBOX_SERVER_API_KEY", raising=False)
    key_file = tmp_path / "opensandbox" / "api_key"
    settings = SandboxSettings(api_key_file=key_file)

    assert not key_file.exists()
    key1 = get_or_create_sandbox_api_key(settings)
    assert len(key1) >= 32
    assert key_file.exists()
    assert key_file.read_text(encoding="utf-8").strip() == key1

    # Subsequent calls reuse the persisted runtime key
    key2 = get_or_create_sandbox_api_key(settings)
    assert key2 == key1


def test_get_or_create_sandbox_api_key_prefers_env_var(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENSANDBOX_SERVER_API_KEY", "runtime-internal-secret-token")
    key_file = tmp_path / "opensandbox" / "api_key"
    settings = SandboxSettings(api_key_file=key_file)

    assert get_or_create_sandbox_api_key(settings) == "runtime-internal-secret-token"
    assert not key_file.exists()


def test_build_sandbox_system_prompt() -> None:
    prompt = build_sandbox_system_prompt("/workspace")
    assert "/workspace" in prompt
    assert "Git-tracked operational directory" in prompt
    assert "transient" in prompt.lower()

    custom_prompt = build_sandbox_system_prompt("/custom/op/dir")
    assert "/custom/op/dir" in custom_prompt


def test_seamus_opensandbox_backend_volume_pvc_and_host(tmp_path: Path) -> None:
    agent_id = uuid4()
    session_id = uuid4()
    data_dir = tmp_path / str(agent_id) / str(session_id) / "data"

    # 1. Docker Compose mode with named volume + sub_path
    pvc_settings = SandboxSettings(
        workdir="/workspace",
        workspace_volume="seamus-workspaces",
        api_key_file=tmp_path / "key",
    )
    backend_pvc = SeamusOpenSandboxBackend(
        agent_id=agent_id,
        session_id=session_id,
        data_dir=data_dir,
        settings=pvc_settings,
    )
    assert isinstance(backend_pvc, OpenSandboxBackend)
    vol_pvc = backend_pvc.build_workspace_volume()
    assert vol_pvc.mount_path == "/workspace"
    assert vol_pvc.read_only is False
    assert vol_pvc.pvc is not None
    assert vol_pvc.pvc.claim_name == "seamus-workspaces"
    assert vol_pvc.sub_path == f"{agent_id}/{session_id}/data"
    assert vol_pvc.host is None

    # 2. Local host mode with Host bind mount
    host_settings = SandboxSettings(
        workdir="/workspace",
        workspace_volume=None,
        api_key_file=tmp_path / "key",
    )
    backend_host = SeamusOpenSandboxBackend(
        agent_id=agent_id,
        session_id=session_id,
        data_dir=data_dir,
        settings=host_settings,
    )
    vol_host = backend_host.build_workspace_volume()
    assert vol_host.mount_path == "/workspace"
    assert vol_host.read_only is False
    assert vol_host.host is not None
    assert vol_host.host.path == str(data_dir.resolve())
    assert vol_host.pvc is None


def test_seamus_opensandbox_backend_lazy_provisioning_and_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OPENSANDBOX_SERVER_API_KEY", raising=False)
    agent_id = uuid4()
    session_id = uuid4()
    data_dir = tmp_path / "data"
    settings = SandboxSettings(
        domain="opensandbox:8080",
        protocol="http",
        image="python:3.12-slim",
        timeout=180,
        sandbox_timeout=1800,
        workdir="/workspace",
        workspace_volume="seamus-workspaces",
        api_key_file=tmp_path / "api_key",
    )

    backend = SeamusOpenSandboxBackend(
        agent_id=agent_id,
        session_id=session_id,
        data_dir=data_dir,
        settings=settings,
    )
    assert backend._active_sandbox is None

    mock_sb = MagicMock()
    mock_sb.id = "sb-lazy-1"
    mock_sb.commands.run.return_value = _make_execution(stdout="sandbox-ok", exit_code=0)

    with patch("seamus.harness.sandbox.SandboxSync.create", return_value=mock_sb) as mock_create:
        res = backend.execute("echo sandbox-ok")
        assert res.output == "sandbox-ok"
        assert res.exit_code == 0
        assert backend.id == "sb-lazy-1"
        assert mock_create.call_count == 1

        call_args, call_kwargs = mock_create.call_args
        assert call_args[0] == "python:3.12-slim"
        assert call_kwargs["metadata"] == {
            "seamus.agent_id": str(agent_id),
            "seamus.session_id": str(session_id),
        }
        assert len(call_kwargs["volumes"]) == 1
        assert call_kwargs["volumes"][0].mount_path == "/workspace"
        assert call_kwargs["volumes"][0].sub_path == f"{agent_id}/{session_id}/data"

    backend.close()
    mock_sb.close.assert_called_once()

    backend.destroy()
    mock_sb.destroy.assert_called_once()
    assert backend._active_sandbox is None


def test_session_agent_runner_builds_deep_agent_with_opensandbox_and_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SEAMUS_PERSISTENCE_ENABLED", "false")
    monkeypatch.setenv("SEAMUS_WORKSPACE_DIR", str(tmp_path / "ws"))

    from seamus.persistence.config import get_persistence_settings

    get_persistence_settings.cache_clear()

    config = AgentConfig(
        inference=InferenceConfig(api_key="test-key", base_url="https://openrouter.ai/api/v1"),
        model_name="openai/gpt-oss-120b",
    )
    agent = Agent(config=config, name="sandboxed-agent")
    session = agent.create_session(name="sandboxed-session")

    captured_kwargs: dict[str, Any] = {}

    def fake_create_deep_agent(**kwargs: Any) -> MagicMock:
        captured_kwargs.update(kwargs)
        return MagicMock()

    with patch("seamus.harness.runner.create_deep_agent", side_effect=fake_create_deep_agent):
        runner = SessionAgentRunner(session=session, agent_entity=agent)

    assert isinstance(runner._sandbox_backend, SeamusOpenSandboxBackend)
    assert captured_kwargs["backend"] is runner._sandbox_backend
    assert isinstance(captured_kwargs["system_prompt"], str)
    assert "/workspace" in captured_kwargs["system_prompt"]
    assert "transient" in captured_kwargs["system_prompt"].lower()
    assert "skills" in captured_kwargs
    assert "/workspace/.skills" in captured_kwargs["skills"]


def test_session_agent_runner_includes_resolved_system_skills(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SEAMUS_PERSISTENCE_ENABLED", "false")
    monkeypatch.setenv("SEAMUS_WORKSPACE_DIR", str(tmp_path / "ws"))
    from seamus.config.settings import SystemSettings, get_system_settings_store
    from seamus.persistence.config import get_persistence_settings

    get_persistence_settings.cache_clear()

    host_home = tmp_path / "host_home"
    existing_sys_skill = host_home / ".seamus" / "skills"
    existing_sys_skill.mkdir(parents=True)
    monkeypatch.setenv("SEAMUS_HOST_HOME", str(host_home))

    store = get_system_settings_store()
    store.set_settings(
        SystemSettings(skill_directories=["~/.seamus/skills", "~/.nonexistent/skills"])
    )

    config = AgentConfig(
        inference=InferenceConfig(api_key="test-key", base_url="https://openrouter.ai/api/v1"),
        model_name="openai/gpt-oss-120b",
    )
    agent = Agent(config=config, name="skills-agent")
    session = agent.create_session(name="skills-session")

    captured_kwargs: dict[str, Any] = {}

    def fake_create_deep_agent(**kwargs: Any) -> MagicMock:
        captured_kwargs.update(kwargs)
        return MagicMock()

    with patch("seamus.harness.runner.create_deep_agent", side_effect=fake_create_deep_agent):
        _runner = SessionAgentRunner(session=session, agent_entity=agent)

    skills = captured_kwargs.get("skills", [])
    # Existing resolved system skill directory included first
    assert str(existing_sys_skill.resolve()) in skills
    # Nonexistent directory omitted
    assert not any("nonexistent" in s for s in skills)
    # Session workspace skills last
    assert skills[-1] == "/workspace/.skills"


def test_sandbox_build_skill_volumes_read_only(tmp_path: Path) -> None:
    skill_dir_1 = tmp_path / "skill1"
    skill_dir_1.mkdir()
    skill_dir_2 = tmp_path / "skill2"
    skill_dir_2.mkdir()
    non_existent = tmp_path / "skill_missing"

    backend = SeamusOpenSandboxBackend(
        agent_id=uuid4(),
        session_id=uuid4(),
        data_dir=tmp_path / "data",
        skill_directories=[str(skill_dir_1), str(skill_dir_2), str(non_existent)],
    )

    volumes = backend.build_skill_volumes()
    assert len(volumes) == 2

    # Verify strictly read-only and correct mount path
    for vol in volumes:
        assert vol.read_only is True
        assert vol.host is not None

    paths = [vol.mount_path for vol in volumes]
    assert str(skill_dir_1.resolve()) in paths
    assert str(skill_dir_2.resolve()) in paths
    assert str(non_existent.resolve()) not in paths


def test_sandbox_build_skill_volumes_tilde_expansion_and_missing_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_home = tmp_path / "home_user"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))

    # Existing dir under fake home
    existing_skill = fake_home / ".seamus" / "skills"
    existing_skill.mkdir(parents=True)

    # Missing dir under fake home
    missing_skill = fake_home / ".skills"
    assert not missing_skill.exists()

    backend = SeamusOpenSandboxBackend(
        agent_id=uuid4(),
        session_id=uuid4(),
        data_dir=tmp_path / "data",
        skill_directories=["~/.seamus/skills", "~/.skills"],
    )

    volumes = backend.build_skill_volumes()
    # Missing ~/.skills is cleanly skipped without error; existing ~/.seamus/skills is mounted
    assert len(volumes) == 1
    assert volumes[0].mount_path == str(existing_skill.resolve())
    assert volumes[0].read_only is True
