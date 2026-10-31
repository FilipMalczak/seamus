"""Unit tests for HarnessStore persistence synchronization and Gitea hydration."""

import json
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from seamus.config.models import AgentConfig, InferenceConfig, InferenceFormat
from seamus.harness.store import HarnessStore


@pytest.fixture
def test_config() -> AgentConfig:
    return AgentConfig(
        inference=InferenceConfig(
            format=InferenceFormat.OPENAI,
            base_url="https://openrouter.ai/api/v1",
            api_key="sk-test-key",
        ),
        model_name="openai/gpt-oss-120b",
    )


def test_harness_store_persistence_hooks(test_config: AgentConfig) -> None:
    store = HarnessStore()
    mock_ws = MagicMock()

    with patch("seamus.harness.store.get_workspace_manager", return_value=mock_ws):
        agent = store.create_agent(config=test_config, name="agent-1")
        assert mock_ws.initialize_agent_repo.called
        assert mock_ws.create_session_workspace.called

        store.update_agent(str(agent.id), test_config, "agent-1-renamed")
        assert mock_ws.commit_agent_config.called

        session = store.create_session(str(agent.id), config=test_config, name="session-2")
        assert mock_ws.create_session_workspace.call_count >= 2

        store.update_session(str(agent.id), str(session.id), test_config, "session-2-renamed")
        assert mock_ws.commit_session_config.called

        thread = store.create_thread(str(agent.id), str(session.id), "thread-2")
        assert mock_ws.commit_session_config.call_count >= 2

        store.update_thread(str(agent.id), str(session.id), str(thread.id), "thread-2-renamed")
        assert mock_ws.commit_session_config.call_count >= 3


def test_harness_store_hydrate_from_gitea(test_config: AgentConfig) -> None:
    store = HarnessStore()
    agent_id = uuid4()
    session_id = uuid4()
    thread_id = uuid4()

    mock_client = MagicMock()
    mock_client.is_healthy.return_value = True
    mock_client.list_user_repos.return_value = [{"name": f"agent-{agent_id}"}]

    main_config = {
        "id": str(agent_id),
        "name": "hydrated-agent",
        "created_at": "2026-10-31T10:00:00Z",
        "config": test_config.model_dump(),
    }
    session_config = {
        "id": str(session_id),
        "agent_id": str(agent_id),
        "name": "hydrated-session",
        "created_at": "2026-10-31T10:05:00Z",
        "config": test_config.model_dump(),
        "threads": [
            {
                "id": str(thread_id),
                "name": "hydrated-thread",
                "created_at": "2026-10-31T10:06:00Z",
                "is_open": True,
                "status": "AWAITING_USER",
            }
        ],
    }
    thread_events = [
        {"type": "TEXT_MESSAGE_START", "messageId": "msg-1", "role": "user"},
        {"type": "TEXT_MESSAGE_CONTENT", "messageId": "msg-1", "delta": "Hello agent"},
        {"type": "TEXT_MESSAGE_END", "messageId": "msg-1"},
    ]

    def mock_get_file(repo: str, branch: str, path: str) -> str | None:
        if branch == "main" and path in ("agent/config/config.json", "config/config.json"):
            return json.dumps(main_config)
        if branch == f"session/{session_id}":
            if path in ("agent/config/config.json", "config/config.json"):
                return json.dumps(session_config)
            if path == f"agent/state/threads/{thread_id}/events.json":
                return json.dumps(thread_events)
        return None

    mock_client.get_file_content.side_effect = mock_get_file
    mock_client.list_branches.return_value = ["main", f"session/{session_id}"]

    mock_ws = MagicMock()
    mock_ws.settings.enabled = True
    mock_ws.client = mock_client

    with patch("seamus.harness.store.get_workspace_manager", return_value=mock_ws):
        store.hydrate_from_gitea()

        assert agent_id in store._agents
        agent = store._agents[agent_id]
        assert agent.name == "hydrated-agent"
        assert session_id in agent.sessions
        session = agent.sessions[session_id]
        assert session.name == "hydrated-session"
        assert thread_id in session.threads
        thread = session.threads[thread_id]
        assert thread.name == "hydrated-thread"
        assert thread.is_open is True
        assert len(thread.events) == 3
