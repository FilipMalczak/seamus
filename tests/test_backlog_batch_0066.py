"""Tests for batch 0066 backlog items: tool disabling, terminal complete/timeout, and async Git."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import empty_checkpoint

from seamus.config.models import AgentConfig, InferenceConfig
from seamus.config.settings import SystemSettings, SystemSettingsStore, reset_system_settings_store
from seamus.config.template import reset_config_template_store
from seamus.harness.runner import reset_runner_registry
from seamus.harness.store import HarnessStore, reset_harness_store
from seamus.persistence.checkpointer import GitCheckpointSaver
from seamus.server.app import create_app


@pytest.fixture
def api_client(monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory) -> TestClient:
    from seamus.persistence.config import get_persistence_settings

    monkeypatch.setenv("SEAMUS_PERSISTENCE_ENABLED", "false")
    get_persistence_settings.cache_clear()
    reset_config_template_store(None)
    reset_harness_store(HarnessStore())
    reset_runner_registry()
    reset_system_settings_store(
        SystemSettingsStore(initial_settings=SystemSettings(terminal_session_timeout_seconds=120))
    )
    app = create_app()
    return TestClient(app)


def _complete_config() -> dict[str, object]:
    return AgentConfig(inference=InferenceConfig(api_key="test-key")).model_dump(mode="json")


def test_inspector_tool_toggle_and_runner_filtering(api_client: TestClient) -> None:
    agent_resp = api_client.post(
        "/api/v-alpha/agent",
        json={"name": "toggle-agent", "config": _complete_config()},
    )
    assert agent_resp.status_code == 201
    agent_id = agent_resp.json()["id"]

    sess_resp = api_client.post(
        f"/api/v-alpha/agent/{agent_id}/session",
        json={"name": "toggle-sess"},
    )
    assert sess_resp.status_code == 201
    session_id = sess_resp.json()["id"]

    # Disable web_search tool via inspector endpoint
    patch_resp = api_client.patch(
        f"/api/v-alpha/agent/{agent_id}/session/{session_id}/inspector/tools",
        json={"tool_name": "web_search", "enabled": False},
    )
    assert patch_resp.status_code == 200
    tools_by_name = {t["name"]: t for t in patch_resp.json()["tools"]}
    if "web_search" in tools_by_name:
        assert tools_by_name["web_search"]["enabled"] is False

    # Re-enable web_search
    patch_resp2 = api_client.patch(
        f"/api/v-alpha/agent/{agent_id}/session/{session_id}/inspector/tools",
        json={"tool_name": "web_search", "enabled": True},
    )
    assert patch_resp2.status_code == 200
    tools_by_name2 = {t["name"]: t for t in patch_resp2.json()["tools"]}
    if "web_search" in tools_by_name2:
        assert tools_by_name2["web_search"]["enabled"] is True


def test_terminal_info_includes_timeout_and_complete_endpoint(api_client: TestClient) -> None:
    agent_resp = api_client.post(
        "/api/v-alpha/agent",
        json={"name": "term-agent", "config": _complete_config()},
    )
    agent_id = agent_resp.json()["id"]
    sess_resp = api_client.post(
        f"/api/v-alpha/agent/{agent_id}/session",
        json={"name": "term-sess"},
    )
    session_id = sess_resp.json()["id"]

    fake_backend = MagicMock()
    fake_backend.settings.workdir = "/workspace"
    fake_exec = SimpleNamespace(
        logs=SimpleNamespace(stdout=[SimpleNamespace(text="README.md\nsrc/\n")])
    )
    fake_backend.run_with_recovery.return_value = fake_exec

    with patch(
        "seamus.harness.runner.SessionAgentRunner.get_sandbox_backend",
        return_value=fake_backend,
    ):
        info_resp = api_client.get(
            f"/api/v-alpha/agent/{agent_id}/session/{session_id}/terminal/info"
        )
        assert info_resp.status_code == 200
        assert info_resp.json()["terminal_session_timeout_seconds"] == 120

        comp_resp = api_client.post(
            f"/api/v-alpha/agent/{agent_id}/session/{session_id}/terminal/complete",
            json={"prefix": "ls ", "working_directory": "/workspace"},
        )
        assert comp_resp.status_code == 200
        data = comp_resp.json()
        assert data["candidates"] == ["README.md", "src/"]


@pytest.mark.asyncio
async def test_git_checkpoint_aput_offloads_to_thread() -> None:
    mock_ws = MagicMock()
    mock_ws.load_all_thread_checkpoints.return_value = []
    saver = GitCheckpointSaver(
        agent_id=uuid4(),
        session_id=uuid4(),
        workspace_manager=mock_ws,
    )
    config: RunnableConfig = {"configurable": {"thread_id": uuid4().hex, "checkpoint_ns": ""}}
    checkpoint = empty_checkpoint()

    with patch("seamus.persistence.checkpointer.asyncio.to_thread", wraps=asyncio.to_thread) as spy:
        await saver.aput(config, checkpoint, {}, {})
        assert spy.called
