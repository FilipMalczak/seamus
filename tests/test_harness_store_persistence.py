"""Unit tests for HarnessStore persistence synchronization and Gitea hydration."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from seamus.config.models import AgentConfig, InferenceConfig, InferenceFormat
from seamus.domain.entities import SessionStatus
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
    mock_client.list_orgs.return_value = [
        {"name": f"agent-{agent_id.hex}"},
        {"name": f"archived-agent-{uuid4().hex}"},
        {"name": "mirrors"},
    ]
    mock_client.list_org_repos.return_value = [
        {"name": "agent"},
        {"name": f"session-{session_id}"},
        {"name": "project-myrepo-12345678-abcdef12"},
    ]

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
        "status": "KILLED",
        "provenance": {
            "parent_session_id": str(uuid4()),
            "parent_message_id": "msg-origin-1",
            "parent_session_name": "origin-session",
        },
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

    def mock_get_file(repo: str, branch: str, path: str, owner: str | None = None) -> str | None:
        config_paths = ("agent/config/config.json", "config/config.json")
        if repo == "agent" and branch == "main" and path in config_paths:
            return json.dumps(main_config)
        if repo == f"session-{session_id}" and branch == "main":
            if path in ("agent/config/config.json", "config/config.json"):
                return json.dumps(session_config)
            if path == f"agent/state/threads/{thread_id}/events.json":
                return json.dumps(thread_events)
        return None

    mock_client.get_file_content.side_effect = mock_get_file

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
        assert session.status == SessionStatus.KILLED
        assert session.provenance is not None
        assert session.provenance.parent_message_id == "msg-origin-1"
        assert session.provenance.parent_session_name == "origin-session"
        assert thread_id in session.threads
        thread = session.threads[thread_id]
        assert thread.name == "hydrated-thread"
        assert thread.is_open is True
        assert len(thread.events) == 3


def test_harness_store_hydrate_ignores_prefixed_and_invalid_orgs() -> None:
    store = HarnessStore()
    mock_client = MagicMock()
    mock_client.is_healthy.return_value = True
    mock_client.list_orgs.return_value = [
        {"name": "archived-agent-12345678-1234-1234-1234-123456789abc"},
        {"name": "deleted-agent-12345678-1234-1234-1234-123456789abc"},
        {"name": "mirrors"},
        {"name": "agent-not-a-uuid"},
        {"name": "some-other-org"},
    ]
    mock_ws = MagicMock()
    mock_ws.settings.enabled = True
    mock_ws.client = mock_client

    with patch("seamus.harness.store.get_workspace_manager", return_value=mock_ws):
        store.hydrate_from_gitea()

    assert len(store._agents) == 0
    mock_client.list_org_repos.assert_not_called()


def test_harness_store_hydrate_ignores_archived_repos(test_config: AgentConfig) -> None:
    store = HarnessStore()
    agent_id = uuid4()
    active_session_id = uuid4()
    archived_session_id = uuid4()

    mock_client = MagicMock()
    mock_client.is_healthy.return_value = True
    mock_client.list_orgs.return_value = [{"name": f"agent-{agent_id.hex}"}]
    mock_client.list_org_repos.return_value = [
        {"name": "agent"},
        {"name": f"session-{active_session_id}", "archived": False},
        {"name": f"session-{archived_session_id}", "archived": True},
    ]

    main_config = {
        "id": str(agent_id),
        "name": "agent-1",
        "created_at": "2026-10-31T10:00:00Z",
        "config": test_config.model_dump(),
    }
    session_config = {
        "id": str(active_session_id),
        "agent_id": str(agent_id),
        "name": "active-session",
        "created_at": "2026-10-31T10:05:00Z",
        "status": "AWAITING_USER",
        "config": test_config.model_dump(),
        "threads": [],
    }

    def mock_get_file(repo: str, branch: str, path: str, owner: str | None = None) -> str | None:
        if repo == "agent":
            return json.dumps(main_config)
        if repo == f"session-{active_session_id}":
            return json.dumps(session_config)
        return None

    mock_client.get_file_content.side_effect = mock_get_file

    mock_ws = MagicMock()
    mock_ws.settings.enabled = True
    mock_ws.client = mock_client

    with patch("seamus.harness.store.get_workspace_manager", return_value=mock_ws):
        store.hydrate_from_gitea()

    assert agent_id in store._agents
    agent = store._agents[agent_id]
    assert active_session_id in agent.sessions
    assert archived_session_id not in agent.sessions


def test_harness_store_archive_session(test_config: AgentConfig, tmp_path: Path) -> None:
    store = HarnessStore()
    mock_ws = MagicMock()
    mock_ws.settings.enabled = True
    mock_ws.workspace_root = tmp_path
    mock_client = MagicMock()
    mock_client.is_healthy.return_value = True
    mock_ws.client = mock_client

    with patch("seamus.harness.store.get_workspace_manager", return_value=mock_ws):
        agent = store.create_agent(config=test_config, name="agent-arch")
        session = store.create_session(str(agent.id), config=test_config, name="session-arch")

        session_hash = session.id.hex[:8]
        org_name = f"agent-{agent.id.hex}"
        mock_ws.get_agent_org_name.return_value = org_name
        mock_ws.get_session_repo_name.return_value = f"session-{session.id}"

        # Mock mount forks in the org
        fork_name = f"project-myrepo-12345678-{session_hash}"
        other_fork = "project-other-87654321-ffffffff"
        mock_client.list_org_repos.return_value = [
            {"name": "agent"},
            {"name": f"session-{session.id}"},
            {"name": fork_name},
            {"name": other_fork},
        ]

        # Fake local session workspace directory
        sess_ws = tmp_path / str(agent.id) / str(session.id)
        sess_ws.mkdir(parents=True, exist_ok=True)
        (sess_ws / "dummy.txt").write_text("hello")
        mock_ws.get_session_workspace_path.return_value = sess_ws

        store.archive_session(str(agent.id), str(session.id))

        # Checkpoints committed
        assert mock_ws.commit_checkpoint_changes.called
        assert mock_ws.commit_session_config.called
        assert mock_ws.close_sync_pr.called

        # Repos archived in Gitea
        mock_client.archive_repo.assert_any_call(f"session-{session.id}", owner=org_name)
        mock_client.archive_repo.assert_any_call(fork_name, owner=org_name)
        # Other session's fork should not be archived
        for call in mock_client.archive_repo.call_args_list:
            assert call.args[0] != other_fork

        # Local directory cleaned up
        assert not sess_ws.exists()

        # Session removed from in-memory agent
        assert session.id not in agent.sessions


def test_harness_store_delete_session(test_config: AgentConfig, tmp_path: Path) -> None:
    store = HarnessStore()
    mock_ws = MagicMock()
    mock_ws.settings.enabled = True
    mock_ws.workspace_root = tmp_path
    mock_client = MagicMock()
    mock_client.is_healthy.return_value = True
    mock_ws.client = mock_client

    with patch("seamus.harness.store.get_workspace_manager", return_value=mock_ws):
        agent = store.create_agent(config=test_config, name="agent-del")
        session = store.create_session(str(agent.id), config=test_config, name="session-del")

        session_hash = session.id.hex[:8]
        org_name = f"agent-{agent.id.hex}"
        mock_ws.get_agent_org_name.return_value = org_name
        mock_ws.get_session_repo_name.return_value = f"session-{session.id}"

        fork_name = f"project-myrepo-12345678-{session_hash}"
        mock_client.list_org_repos.return_value = [
            {"name": f"session-{session.id}"},
            {"name": fork_name},
        ]

        sess_ws = tmp_path / str(agent.id) / str(session.id)
        sess_ws.mkdir(parents=True, exist_ok=True)
        mock_ws.get_session_workspace_path.return_value = sess_ws

        store.delete_session(str(agent.id), str(session.id))

        mock_client.delete_repo.assert_any_call(fork_name, owner=org_name)
        mock_client.delete_repo.assert_any_call(f"session-{session.id}", owner=org_name)
        assert not sess_ws.exists()
        assert session.id not in agent.sessions


def test_harness_store_archive_agent(test_config: AgentConfig, tmp_path: Path) -> None:
    store = HarnessStore()
    mock_ws = MagicMock()
    mock_ws.settings.enabled = True
    mock_ws.workspace_root = tmp_path
    mock_client = MagicMock()
    mock_client.is_healthy.return_value = True
    mock_ws.client = mock_client

    with patch("seamus.harness.store.get_workspace_manager", return_value=mock_ws):
        agent = store.create_agent(config=test_config, name="agent-arch-all")
        org_name = f"agent-{agent.id.hex}"
        mock_ws.get_agent_org_name.return_value = org_name

        agent_ws = tmp_path / str(agent.id)
        agent_ws.mkdir(parents=True, exist_ok=True)

        store.archive_agent(str(agent.id))

        mock_client.rename_org.assert_called_once_with(org_name, f"archived-{org_name}")
        assert not agent_ws.exists()
        assert agent.id not in store._agents


def test_harness_store_delete_agent(test_config: AgentConfig, tmp_path: Path) -> None:
    store = HarnessStore()
    mock_ws = MagicMock()
    mock_ws.settings.enabled = True
    mock_ws.workspace_root = tmp_path
    mock_client = MagicMock()
    mock_client.is_healthy.return_value = True
    mock_ws.client = mock_client

    with patch("seamus.harness.store.get_workspace_manager", return_value=mock_ws):
        agent = store.create_agent(config=test_config, name="agent-del-all")
        org_name = f"agent-{agent.id.hex}"
        mock_ws.get_agent_org_name.return_value = org_name

        mock_client.list_org_repos.return_value = [
            {"name": "agent"},
            {"name": "session-1"},
            {"name": "project-repo-1234"},
        ]

        agent_ws = tmp_path / str(agent.id)
        agent_ws.mkdir(parents=True, exist_ok=True)

        store.delete_agent(str(agent.id))

        # Repos deleted first
        mock_client.delete_repo.assert_any_call("agent", owner=org_name)
        mock_client.delete_repo.assert_any_call("session-1", owner=org_name)
        mock_client.delete_repo.assert_any_call("project-repo-1234", owner=org_name)

        # Then org deleted
        mock_client.delete_org.assert_called_once_with(org_name)

        assert not agent_ws.exists()
        assert agent.id not in store._agents
