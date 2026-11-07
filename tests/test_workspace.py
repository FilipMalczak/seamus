"""Integration tests for GitWorkspaceManager with local Git repositories."""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from seamus.config.models import AgentConfig, InferenceConfig, InferenceFormat
from seamus.domain.entities import Agent, Session
from seamus.persistence.config import PersistenceSettings
from seamus.persistence.workspace import GitWorkspaceManager


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


@pytest.fixture
def git_environment(tmp_path: Path) -> tuple[GitWorkspaceManager, Path, Path]:
    bare_remote = tmp_path / "remote.git"
    subprocess.run(
        ["git", "init", "--bare", "-b", "main", str(bare_remote)],
        check=True,
        capture_output=True,
    )

    workspace_dir = tmp_path / "workspaces"
    settings = PersistenceSettings(
        workspace_dir=workspace_dir,
        enabled=True,
    )

    mock_client = MagicMock()
    mock_client.get_or_create_repo.return_value = {"name": "test-repo"}
    mock_client.get_authenticated_clone_url.return_value = str(bare_remote)
    mock_client.list_branches.return_value = ["main"]

    manager = GitWorkspaceManager(settings=settings, client=mock_client)
    return manager, bare_remote, workspace_dir


def test_initialize_agent_repo(
    git_environment: tuple[GitWorkspaceManager, Path, Path], test_config: AgentConfig
) -> None:
    manager, bare_remote, workspace_dir = git_environment
    agent = Agent(name="test-agent", config=test_config)

    agent_dir = manager.initialize_agent_repo(agent)
    assert (agent_dir / ".git").exists()
    assert (agent_dir / ".gitignore").exists()
    assert (agent_dir / "agent" / "config" / "config.json").exists()
    assert (agent_dir / "agent" / "state" / ".gitkeep").exists()
    assert (agent_dir / "data" / ".gitkeep").exists()

    gitignore_content = (agent_dir / ".gitignore").read_text()
    assert "__pycache__/" in gitignore_content
    assert "node_modules/" in gitignore_content

    config_data = json.loads((agent_dir / "agent" / "config" / "config.json").read_text())
    assert config_data["id"] == str(agent.id)
    assert config_data["name"] == "test-agent"
    assert config_data["config"]["model_name"] == "openai/gpt-oss-120b"

    # Verify commit log
    log = subprocess.run(
        ["git", "log", "-1", "--pretty=%s"],
        cwd=agent_dir,
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()
    assert f"config: initialize agent [agent={agent.id}]" == log


def test_session_workspace_and_checkpoint_commits(
    git_environment: tuple[GitWorkspaceManager, Path, Path], test_config: AgentConfig
) -> None:
    manager, bare_remote, workspace_dir = git_environment
    agent = Agent(name="test-agent", config=test_config)
    manager.initialize_agent_repo(agent)

    session = Session(agent_id=agent.id, name="test-session", config=test_config)
    thread = session.create_thread(name="test-thread")

    session_dir = manager.create_session_workspace(session, agent)
    assert (session_dir / ".git").exists()
    assert (session_dir / "data").exists()
    assert (session_dir / "data" / "skills").exists()
    assert (session_dir / "data" / ".skills").exists()
    assert (session_dir / "agent" / "config" / "config.json").exists()

    # Verify session branch
    current_branch = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=session_dir,
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()
    assert current_branch == f"session/{session.id}"

    # Verify initial clean status
    committed = manager.commit_checkpoint_changes(agent.id, session.id, thread.id, "cp-0")
    assert committed is False

    # Create workspace files in data/
    test_file = session_dir / "data" / "output.txt"
    test_file.write_text("Hello agent world!", encoding="utf-8")

    # Commit checkpoint changes
    committed = manager.commit_checkpoint_changes(agent.id, session.id, thread.id, "cp-1")
    assert committed is True

    # Verify commit message
    log = subprocess.run(
        ["git", "log", "-1", "--pretty=%s"],
        cwd=session_dir,
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()
    expected_msg = f"checkpoint: [session={session.id} thread={thread.id} checkpoint=cp-1]"
    assert log == expected_msg

    # Second commit with no new changes should return False
    assert manager.commit_checkpoint_changes(agent.id, session.id, thread.id, "cp-2") is False


def test_commit_agent_and_session_config(
    git_environment: tuple[GitWorkspaceManager, Path, Path], test_config: AgentConfig
) -> None:
    manager, bare_remote, workspace_dir = git_environment
    agent = Agent(name="test-agent", config=test_config)
    manager.initialize_agent_repo(agent)

    # Update agent name and commit config
    agent.name = "renamed-agent"
    manager.commit_agent_config(agent)

    agent_dir = manager.get_agent_workspace_path(agent.id)
    log = subprocess.run(
        ["git", "log", "-1", "--pretty=%s"],
        cwd=agent_dir,
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()
    assert f"config: update agent config [agent={agent.id}]" == log

    # Update session config
    session = Session(agent_id=agent.id, name="test-session", config=test_config)
    manager.create_session_workspace(session, agent)

    session.name = "renamed-session"
    manager.commit_session_config(session)

    session_dir = manager.get_session_workspace_path(agent.id, session.id)
    session_log = subprocess.run(
        ["git", "log", "-1", "--pretty=%s"],
        cwd=session_dir,
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()
    assert f"config: update session config [session={session.id}]" == session_log


def test_save_and_load_thread_state_and_events(
    git_environment: tuple[GitWorkspaceManager, Path, Path], test_config: AgentConfig
) -> None:
    manager, bare_remote, workspace_dir = git_environment
    agent = Agent(name="test-agent", config=test_config)
    manager.initialize_agent_repo(agent)

    session = Session(agent_id=agent.id, name="test-session", config=test_config)
    thread = session.create_thread(name="test-thread")
    manager.create_session_workspace(session, agent)

    # Save thread events
    sample_events = [
        {"type": "TEXT_MESSAGE_START", "messageId": "m1", "role": "user"},
        {"type": "TEXT_MESSAGE_CONTENT", "messageId": "m1", "delta": "hello"},
        {"type": "TEXT_MESSAGE_END", "messageId": "m1"},
    ]
    saved_path = manager.save_thread_events(agent.id, session.id, thread.id, sample_events)
    assert saved_path.exists()

    loaded_events = manager.load_thread_events(agent.id, session.id, thread.id)
    assert len(loaded_events) == 3

    # Save checkpoints and messages
    cp_data = {"storage": {"t1": {}}, "writes": [], "blobs": []}
    cp_path = manager.save_thread_checkpoints(agent.id, session.id, thread.id, cp_data)
    assert cp_path.exists()
    assert manager.load_thread_checkpoints(agent.id, session.id, thread.id) == cp_data

    # Commit state changes
    committed = manager.commit_state_changes(agent.id, session.id, thread.id)
    assert committed is True

    session_dir = manager.get_session_workspace_path(agent.id, session.id)
    log = subprocess.run(
        ["git", "log", "-1", "--pretty=%s"],
        cwd=session_dir,
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()
    assert log == f"state: update thread events [session={session.id} thread={thread.id}]"


def test_sync_pr_workspace_operations(
    git_environment: tuple[GitWorkspaceManager, Path, Path],
    test_config: AgentConfig,
) -> None:
    manager, _, _ = git_environment
    agent = Agent(name="test-agent", config=test_config)
    session = Session(agent_id=agent.id, name="test-session", config=test_config)

    # Mock client PR methods
    mock_pr = {"id": 1, "number": 10, "head": {"ref": f"session/{session.id}"}, "mergeable": True}
    manager.client.list_pull_requests = MagicMock(return_value=[])  # type: ignore[method-assign]
    manager.client.create_pull_request = MagicMock(return_value=mock_pr)  # type: ignore[method-assign]
    manager.client.approve_pull_request = MagicMock(return_value={"state": "APPROVED"})  # type: ignore[method-assign]
    manager.client.merge_pull_request = MagicMock(return_value=True)  # type: ignore[method-assign]
    manager.client.get_pull_request = MagicMock(return_value=mock_pr)  # type: ignore[method-assign]

    # 1. Open Sync PR
    opened = manager.open_sync_pr(session, agent)
    assert opened is not None
    assert opened["number"] == 10
    manager.client.create_pull_request.assert_called_once()
    create_call = manager.client.create_pull_request.call_args
    assert create_call.kwargs["head"] == f"session/{session.id}"
    assert create_call.kwargs["base"] == "main"

    # 2. Get active Sync PR
    manager.client.list_pull_requests.return_value = [mock_pr]
    active = manager.get_active_sync_pr(session, agent)
    assert active is not None
    assert active["number"] == 10

    # 2.5. Get Sync PR Diff
    raw_mock_diff = (
        "diff --git a/agent/config/config.json b/agent/config/config.json\n"
        "--- a/agent/config/config.json\n"
        "+++ b/agent/config/config.json\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
        "diff --git a/agent/state/threads/123/events.json b/agent/state/threads/123/events.json\n"
        "--- a/agent/state/threads/123/events.json\n"
        "+++ b/agent/state/threads/123/events.json\n"
        "@@ -1 +1 @@\n"
        "-event_old\n"
        "+event_new\n"
        "diff --git a/data/script.py b/data/script.py\n"
        "--- a/data/script.py\n"
        "+++ b/data/script.py\n"
        "@@ -1 +1 @@\n"
        "+print('hello')\n"
    )
    manager.client.get_pull_request_diff = MagicMock(return_value=raw_mock_diff)  # type: ignore[method-assign]
    pr_data, diff_content = manager.get_sync_pr_diff(session, agent)
    assert pr_data is not None
    assert pr_data["number"] == 10
    assert "data/script.py" in diff_content
    assert "agent/config/config.json" not in diff_content
    assert "agent/state/threads/123/events.json" not in diff_content

    # 3. Merge Sync PR (mocked fallback when branch not in remote list_branches)
    merged = manager.merge_sync_pr(session, agent)
    assert merged is True
    manager.client.approve_pull_request.assert_called_once_with(
        repo_name=manager.get_agent_repo_name(session.agent_id),
        index=10,
        body="Accepted by user",
    )
    manager.client.merge_pull_request.assert_called_once_with(
        repo_name=manager.get_agent_repo_name(session.agent_id),
        index=10,
        do="merge",
        delete_branch=False,
    )


def test_sync_pr_data_scoped_merge_lifecycle(
    git_environment: tuple[GitWorkspaceManager, Path, Path],
    test_config: AgentConfig,
) -> None:
    manager, bare_remote, _ = git_environment
    agent = Agent(name="test-agent", config=test_config)
    session = Session(agent_id=agent.id, name="test-session", config=test_config)
    thread = session.create_thread()

    # 1. Initialize agent workspace and repo on main
    agent_dir = manager.initialize_agent_repo(agent)
    initial_agent_config = (agent_dir / "agent" / "config" / "config.json").read_text()

    # 2. Initialize session workspace on session branch
    session_dir = manager.create_session_workspace(session, agent)
    manager.client.list_branches = MagicMock(  # type: ignore[method-assign]
        return_value=["main", f"session/{session.id}"]
    )

    # 3. Commit agent deliverables in data/ and thread state in agent/state/
    (session_dir / "data" / "result.txt").write_text("agent deliverable content")
    manager.commit_checkpoint_changes(agent.id, session.id, thread.id, checkpoint_id="cp-1")
    manager.save_thread_events(agent.id, session.id, thread.id, [{"type": "MESSAGES_SNAPSHOT"}])
    manager.commit_state_changes(agent.id, session.id, thread.id)

    # 4. Open and merge Sync PR
    mock_pr = {
        "id": 1,
        "number": 42,
        "head": {"ref": f"session/{session.id}"},
        "mergeable": True,
        "merged": False,
    }
    manager.client.list_pull_requests = MagicMock(return_value=[mock_pr])  # type: ignore[method-assign]
    manager.client.get_pull_request = MagicMock(return_value=mock_pr)  # type: ignore[method-assign]
    manager.client.approve_pull_request = MagicMock(return_value={"state": "APPROVED"})  # type: ignore[method-assign]
    manager.client.merge_pull_request = MagicMock(return_value=True)  # type: ignore[method-assign]

    merged = manager.merge_sync_pr(session, agent)
    assert merged is True

    # 5. Verify that GiteaClient.merge_pull_request was called with manually-merged
    manager.client.merge_pull_request.assert_called_once()
    call_kwargs = manager.client.merge_pull_request.call_args.kwargs
    assert call_kwargs["do"] == "manually-merged"
    assert call_kwargs["index"] == 42
    assert call_kwargs["merge_commit_id"] is not None

    # 6. Verify repository state on main branch in agent_dir
    assert (agent_dir / "data" / "result.txt").exists()
    assert (agent_dir / "data" / "result.txt").read_text() == "agent deliverable content"
    # Agent config on main must NOT be overwritten by session config
    assert (agent_dir / "agent" / "config" / "config.json").read_text() == initial_agent_config
    # Thread state must NOT be merged to main
    assert not (agent_dir / "agent" / "state" / "threads").exists()


def test_sync_pr_multi_session_merge_no_conflict(
    git_environment: tuple[GitWorkspaceManager, Path, Path],
    test_config: AgentConfig,
) -> None:
    manager, bare_remote, _ = git_environment
    agent = Agent(name="test-agent", config=test_config)
    agent_dir = manager.initialize_agent_repo(agent)
    initial_agent_config = (agent_dir / "agent" / "config" / "config.json").read_text()

    # Session 1
    session1 = Session(agent_id=agent.id, name="session-1", config=test_config)
    thread1 = session1.create_thread()
    s1_dir = manager.create_session_workspace(session1, agent)

    # Session 2
    session2 = Session(agent_id=agent.id, name="session-2", config=test_config)
    thread2 = session2.create_thread()
    s2_dir = manager.create_session_workspace(session2, agent)

    manager.client.list_branches = MagicMock(  # type: ignore[method-assign]
        return_value=[
            "main",
            f"session/{session1.id}",
            f"session/{session2.id}",
        ]
    )

    # Session 1 produces deliverable 1
    (s1_dir / "data" / "deliverable_1.txt").write_text("s1 output")
    manager.commit_checkpoint_changes(agent.id, session1.id, thread1.id, checkpoint_id="cp-1")

    # Session 2 produces deliverable 2
    (s2_dir / "data" / "deliverable_2.txt").write_text("s2 output")
    manager.commit_checkpoint_changes(agent.id, session2.id, thread2.id, checkpoint_id="cp-2")

    # Mock PRs
    pr1 = {"id": 1, "number": 1, "head": {"ref": f"session/{session1.id}"}, "mergeable": True}
    pr2 = {"id": 2, "number": 2, "head": {"ref": f"session/{session2.id}"}, "mergeable": True}

    manager.client.approve_pull_request = MagicMock(return_value={"state": "APPROVED"})  # type: ignore[method-assign]
    manager.client.merge_pull_request = MagicMock(return_value=True)  # type: ignore[method-assign]

    # Merge Session 1
    manager.client.list_pull_requests = MagicMock(return_value=[pr1])  # type: ignore[method-assign]
    manager.client.get_pull_request = MagicMock(return_value=pr1)  # type: ignore[method-assign]
    assert manager.merge_sync_pr(session1, agent) is True

    # Merge Session 2
    manager.client.list_pull_requests = MagicMock(return_value=[pr2])  # type: ignore[method-assign]
    manager.client.get_pull_request = MagicMock(return_value=pr2)  # type: ignore[method-assign]
    assert manager.merge_sync_pr(session2, agent) is True

    # Main branch contains BOTH deliverables
    assert (agent_dir / "data" / "deliverable_1.txt").exists()
    assert (agent_dir / "data" / "deliverable_1.txt").read_text() == "s1 output"
    assert (agent_dir / "data" / "deliverable_2.txt").exists()
    assert (agent_dir / "data" / "deliverable_2.txt").read_text() == "s2 output"

    # Main branch configuration remains intact
    assert (agent_dir / "agent" / "config" / "config.json").read_text() == initial_agent_config
    assert not (agent_dir / "agent" / "state" / "threads").exists()


def test_system_repo_persistence(
    git_environment: tuple[GitWorkspaceManager, Path, Path],
) -> None:
    manager, bare_remote, workspace_dir = git_environment

    system_dir = manager.initialize_system_repo(
        default_settings={"skill_directories": ["/tmp/skills"]},
        default_config_template={"model_name": "initial-model"},
    )
    assert (system_dir / ".git").exists()
    assert (system_dir / "settings.json").exists()
    assert (system_dir / "config-template.json").exists()

    settings_read = manager.read_system_settings()
    assert settings_read is not None
    assert settings_read["skill_directories"] == ["/tmp/skills"]

    template_read = manager.read_system_config_template()
    assert template_read is not None
    assert template_read["model_name"] == "initial-model"

    # Commit updated settings
    manager.commit_system_settings({"skill_directories": ["/tmp/skills", "/opt/new-skills"]})
    settings_updated = manager.read_system_settings()
    assert settings_updated is not None
    assert settings_updated["skill_directories"] == ["/tmp/skills", "/opt/new-skills"]

    # Commit updated template
    manager.commit_system_config_template({"model_name": "updated-model"})
    template_updated = manager.read_system_config_template()
    assert template_updated is not None
    assert template_updated["model_name"] == "updated-model"


def test_system_repo_defaults_without_explicit_args(
    git_environment: tuple[GitWorkspaceManager, Path, Path],
) -> None:
    manager, bare_remote, workspace_dir = git_environment

    system_dir = manager.initialize_system_repo()
    assert (system_dir / "settings.json").exists()

    settings_read = manager.read_system_settings()
    assert settings_read is not None
    assert settings_read["skill_directories"] == ["~/.seamus/skills", "~/.skills"]


def test_sync_session_workspace_auto_pulls_external_changes(
    git_environment: tuple[GitWorkspaceManager, Path, Path],
    test_config: AgentConfig,
    tmp_path: Path,
) -> None:
    manager, bare_remote, workspace_dir = git_environment
    agent = Agent(name="sync-agent", config=test_config)
    manager.initialize_agent_repo(agent)

    session = Session(agent_id=agent.id, name="sync-session", config=test_config)
    thread = session.create_thread(name="sync-thread")

    session_dir = manager.create_session_workspace(session, agent)
    branch_name = f"session/{session.id}"

    # Commit initial state to establish the branch remotely
    test_file = session_dir / "data" / "initial.txt"
    test_file.write_text("initial content", encoding="utf-8")
    assert manager.commit_checkpoint_changes(agent.id, session.id, thread.id, "cp-init") is True

    # Simulate an external commit pushed directly to Gitea/remote
    external_clone = tmp_path / "external_clone"
    subprocess.run(["git", "clone", str(bare_remote), str(external_clone)], check=True)
    subprocess.run(["git", "-C", str(external_clone), "checkout", branch_name], check=True)
    ext_skill_dir = external_clone / "data" / ".skills" / "custom"
    ext_skill_dir.mkdir(parents=True)
    (ext_skill_dir / "SKILL.md").write_text("---\nname: custom\n---\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(external_clone), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(external_clone), "commit", "-m", "external manual skill addition"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(external_clone), "push", "origin", branch_name],
        check=True,
    )

    # Local workspace does not have the file yet
    assert not (session_dir / "data" / ".skills" / "custom" / "SKILL.md").exists()

    # Synchronize session workspace
    assert manager.sync_session_workspace(session) is True

    # Now the externally added skill exists locally on disk
    assert (session_dir / "data" / ".skills" / "custom" / "SKILL.md").exists()

    # Further local checkpoint commit rebases and pushes cleanly
    local_file = session_dir / "data" / "local.txt"
    local_file.write_text("local content", encoding="utf-8")
    assert manager.commit_checkpoint_changes(agent.id, session.id, thread.id, "cp-local") is True
