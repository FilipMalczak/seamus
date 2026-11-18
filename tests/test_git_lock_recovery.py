"""Tests for Git lock recovery, concurrency serialization, and self-healing workspaces."""

import os
import subprocess
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from seamus.config.models import AgentConfig, InferenceConfig, InferenceFormat
from seamus.domain.entities import Agent, Session
from seamus.persistence.config import PersistenceSettings
from seamus.persistence.git_lock import (
    clean_stale_locks,
    extract_lock_paths_from_stderr,
    get_repo_lock,
    sweep_workspace_stale_locks,
)
from seamus.persistence.workspace import GitWorkspaceManager
from seamus.server.app import create_app


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


def test_extract_lock_paths_from_stderr() -> None:
    """Verify regex extraction of lock file paths from Git error messages."""
    stderr_single = (
        "fatal: Unable to create '/app/workspaces/a/b/.git/index.lock': File exists.\n"
        "Another git process seems to be running in this repository..."
    )
    paths = extract_lock_paths_from_stderr(stderr_single)
    assert len(paths) == 1
    assert str(paths[0]) == "/app/workspaces/a/b/.git/index.lock"

    stderr_case_insensitive = 'fatal: unable to create "/tmp/repo/.git/HEAD.lock": file exists.'
    paths2 = extract_lock_paths_from_stderr(stderr_case_insensitive)
    assert len(paths2) == 1
    assert str(paths2[0]) == "/tmp/repo/.git/HEAD.lock"

    assert extract_lock_paths_from_stderr("") == []
    assert extract_lock_paths_from_stderr("Everything up-to-date") == []


def test_clean_stale_locks(tmp_path: Path) -> None:
    """Verify cleaning of stale lock files inside a Git repository."""
    repo_dir = tmp_path / "test_repo"
    git_dir = repo_dir / ".git"
    git_dir.mkdir(parents=True)

    index_lock = git_dir / "index.lock"
    head_lock = git_dir / "HEAD.lock"
    refs_lock = git_dir / "refs" / "heads" / "main.lock"
    refs_lock.parent.mkdir(parents=True)

    index_lock.write_text("lock1")
    head_lock.write_text("lock2")
    refs_lock.write_text("lock3")

    # Regular file should remain untouched
    config_file = git_dir / "config"
    config_file.write_text("repo config")

    removed = clean_stale_locks(repo_dir, force=True)
    assert len(removed) == 3
    assert not index_lock.exists()
    assert not head_lock.exists()
    assert not refs_lock.exists()
    assert config_file.exists()


def test_clean_stale_locks_max_age(tmp_path: Path) -> None:
    """Verify max_age_seconds filtering in clean_stale_locks."""
    repo_dir = tmp_path / "test_repo_age"
    git_dir = repo_dir / ".git"
    git_dir.mkdir(parents=True)

    old_lock = git_dir / "old.lock"
    new_lock = git_dir / "new.lock"
    old_lock.touch()
    new_lock.touch()

    # Artificially age old_lock by 100 seconds
    past_time = time.time() - 100.0
    os.utime(old_lock, (past_time, past_time))

    removed = clean_stale_locks(repo_dir, force=True, max_age_seconds=50.0)
    assert old_lock in removed
    assert not old_lock.exists()
    assert new_lock.exists()


def test_sweep_workspace_stale_locks(tmp_path: Path) -> None:
    """Verify recursive workspace sweeping across multiple repositories."""
    ws_root = tmp_path / "workspaces"

    repo1 = ws_root / "agent-1" / "_agent"
    (repo1 / ".git").mkdir(parents=True)
    lock1 = repo1 / ".git" / "index.lock"
    lock1.touch()

    repo2 = ws_root / "agent-1" / "session-1"
    (repo2 / ".git").mkdir(parents=True)
    lock2 = repo2 / ".git" / "index.lock"
    lock2.touch()

    repo3 = ws_root / "_system"
    (repo3 / ".git").mkdir(parents=True)
    lock3 = repo3 / ".git" / "HEAD.lock"
    lock3.touch()

    count = sweep_workspace_stale_locks(ws_root)
    assert count == 3
    assert not lock1.exists()
    assert not lock2.exists()
    assert not lock3.exists()


def test_get_repo_lock_reentrancy_and_uniqueness(tmp_path: Path) -> None:
    """Verify get_repo_lock returns identical re-entrant locks for equivalent paths."""
    repo_dir = tmp_path / "repo_lock_test"
    repo_dir.mkdir()

    lock1 = get_repo_lock(repo_dir)
    lock2 = get_repo_lock(repo_dir / ".." / "repo_lock_test")
    assert lock1 is lock2

    # Re-entrant acquisition
    with lock1:
        with lock2:
            pass


def test_workspace_manager_self_healing_from_index_lock(
    git_environment: tuple[GitWorkspaceManager, Path, Path],
    test_config: AgentConfig,
) -> None:
    """Verify GitWorkspaceManager automatically recovers from stale index.lock."""
    manager, _bare_remote, _workspace_dir = git_environment

    agent = Agent(name="healing-agent", config=test_config)
    manager.initialize_agent_repo(agent)
    session = Session(agent_id=agent.id, name="healing-session", config=test_config)
    session_dir = manager.create_session_workspace(session, agent)

    # Simulate abrupt host kill: plant a stale index.lock in the session repository
    stale_lock = session_dir / ".git" / "index.lock"
    stale_lock.write_text("")
    assert stale_lock.exists()

    # Modifying session configuration calls _run_git(["add", "-A", "agent/config/"])
    # With the fix, this should automatically remove stale_lock, retry, and succeed!
    session.custom_name = "New Custom Name"
    manager.commit_session_config(session)

    assert not stale_lock.exists()

    # Plant index.lock again and call create_session_workspace (which runs on session reconnect)
    stale_lock.write_text("")
    assert stale_lock.exists()

    reopened_dir = manager.create_session_workspace(session, agent)
    assert reopened_dir == session_dir
    assert not stale_lock.exists()


def test_workspace_manager_run_git_stale_lock_recovery(
    git_environment: tuple[GitWorkspaceManager, Path, Path],
    test_config: AgentConfig,
) -> None:
    """Verify _run_git directly heals and retries when encountering index.lock."""
    manager, _bare_remote, _workspace_dir = git_environment

    agent = Agent(name="git-run-agent", config=test_config)
    agent_dir = manager.initialize_agent_repo(agent)

    # Touch a new file
    test_file = agent_dir / "data" / "sample.txt"
    test_file.write_text("content")

    # Inject stale lock
    lock_file = agent_dir / ".git" / "index.lock"
    lock_file.write_text("")
    assert lock_file.exists()

    # Running git add should recover
    res = manager._run_git(agent_dir, ["add", "data/sample.txt"])
    assert res.returncode == 0
    assert not lock_file.exists()


def test_concurrent_git_operations_serialization(
    git_environment: tuple[GitWorkspaceManager, Path, Path],
    test_config: AgentConfig,
) -> None:
    """Verify per-repository locks serialize concurrent threads without index.lock collisions."""
    manager, _bare_remote, _workspace_dir = git_environment

    agent = Agent(name="concurrent-agent", config=test_config)
    agent_dir = manager.initialize_agent_repo(agent)

    errors: list[Exception] = []

    def worker(worker_id: int) -> None:
        try:
            for i in range(5):
                f = agent_dir / "data" / f"worker_{worker_id}_{i}.txt"
                f.write_text(f"worker {worker_id} iter {i}")
                manager._run_git(agent_dir, ["add", str(f.relative_to(agent_dir))])
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Concurrent git operations encountered errors: {errors}"


def test_sse_session_stream_heals_stale_index_lock(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Reproduction test for the user's issue:

    Abrupt host kill leaves behind .git/index.lock.
    Opening the SSE stream previously failed with status 400.
    With the fix, it should heal the repository and connect with status 200.
    """
    from seamus.harness import HarnessStore, reset_harness_store
    from seamus.harness.runner import reset_runner_registry
    from seamus.persistence import reset_workspace_manager

    # Configure isolated workspace root
    ws_root = tmp_path / "workspaces"
    settings = PersistenceSettings(enabled=False, workspace_dir=ws_root)

    ws_mgr = GitWorkspaceManager(settings=settings)
    reset_workspace_manager(ws_mgr)
    reset_runner_registry()

    store = HarnessStore()
    reset_harness_store(store)

    agent_config = AgentConfig(
        model_name="openai/gpt-oss-120b",
        inference=InferenceConfig(
            api_key="sk-test",
            base_url="https://api.openai.com/v1",
        ),
    )
    agent = store.create_agent(name="delicate-griffin", config=agent_config)
    session = store.create_session(str(agent.id), name="external-repo-support")
    session.create_thread(name="main-thread")

    # Prepare session workspace
    session_dir = ws_mgr.get_session_workspace_path(agent.id, session.id)
    git_dir = session_dir / ".git"
    git_dir.mkdir(parents=True, exist_ok=True)

    # Initialize a dummy git repo so .git exists
    subprocess.run(["git", "init", "-b", "main"], cwd=session_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=session_dir, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.local"], cwd=session_dir, check=True)

    # Plant the stale index.lock file left behind by the host kill!
    stale_lock = git_dir / "index.lock"
    stale_lock.write_text("")
    assert stale_lock.exists()

    app = create_app()
    client = TestClient(app)

    # Request the SSE stream endpoint
    url = f"/api/v-alpha/agent/{agent.id}/session/{session.id}/stream?follow=false"
    response = client.get(url)

    # Must connect with 200 OK (NOT 400 Bad Request)
    assert response.status_code == 200, (
        f"Expected 200 OK, got {response.status_code}: {response.text}"
    )
    assert response.headers["content-type"].startswith("text/event-stream")
    # Verify stale lock was cleaned
    assert not stale_lock.exists()
