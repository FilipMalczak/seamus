"""End-to-end tests for the session workspace and the skill precedence engine.

The session workspace is the boundary between the harness state and the
deliverables. These tests assert on that boundary as the production code
builds it:

* INV-017 — the workspace separates the deliverables (`data/`) from the
  harness state (`agent/config/`, `agent/state/`);
* INV-018 / INV-032 — a turn's output is written into the workspace and the
  session configuration is persisted next to it;
* INV-035 — a session skill shadows a bundled skill of the same name;
* INV-047 / INV-031 — the bundled platform skills are mounted into the
  sandbox, and the system skill directories are mounted read-only;
* REQ-049 / INV-060 — a skill declared as retained survives a phase
  transition, while an exploratory one does not;
* REQ-017 — the workspace mount policy follows the operational mode.
"""

from __future__ import annotations

import asyncio
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest

from seamus.harness.runner import get_runner_registry
from seamus.harness.steerable import SteerableToolCall
from seamus.persistence.config import PersistenceSettings
from seamus.persistence.workspace import (
    GitWorkspaceManager,
    get_workspace_manager,
    reset_workspace_manager,
)


async def _drain(runner: Any, *, timeout: float = 30.0) -> None:
    """Wait for a runner's active turn to finish."""
    task = runner._active_task
    if task is not None and not task.done():
        await asyncio.wait_for(asyncio.shield(task), timeout=timeout)


def _write_skill(directory: Any, name: str, description: str) -> None:
    """Write a minimal skill into a skill directory."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n# {name}\n",
        encoding="utf-8",
    )


@pytest.fixture
def local_git_workspace(tmp_path: Path, steerable_store: Any) -> Iterator[None]:
    """Enable Git-backed workspace persistence over a local bare repository."""
    previous_mgr = get_workspace_manager()
    if previous_mgr.settings.enabled:
        yield
        return

    bare_remote = tmp_path / "remote.git"
    subprocess.run(
        ["git", "init", "--bare", "-b", "main", str(bare_remote)],
        check=True,
        capture_output=True,
    )
    mock_client = MagicMock()
    mock_client.get_or_create_repo.return_value = {"name": "test-repo"}
    mock_client.get_authenticated_clone_url.return_value = str(bare_remote)
    mock_client.list_branches.return_value = ["main"]
    mock_client.list_pull_requests.return_value = []
    mock_client.create_pull_request.return_value = {"number": 1}

    settings = PersistenceSettings(
        workspace_dir=previous_mgr.workspace_root,
        enabled=True,
    )
    reset_workspace_manager(GitWorkspaceManager(settings=settings, client=mock_client))
    try:
        yield
    finally:
        reset_workspace_manager(previous_mgr)


@pytest.mark.asyncio
async def test_session_workspace_separates_deliverables_from_harness_state(
    client: httpx.AsyncClient,
    local_git_workspace: None,
    make_session: Any,
    session_dir: Any,
) -> None:
    """INV-017: `data/` and `agent/config/` live side by side in the workspace."""
    ctx = make_session("workspace-layout", mode="chat")

    workspace = session_dir(ctx["session"])["workspace"]

    assert (workspace / "data").is_dir(), "the deliverables directory must exist"
    assert (workspace / "agent" / "config").is_dir(), "the harness config directory must exist"
    assert (workspace / "agent" / "state").is_dir(), "the harness state directory must exist"


@pytest.mark.asyncio
async def test_session_configuration_is_persisted_next_to_the_deliverables(
    client: httpx.AsyncClient,
    local_git_workspace: None,
    make_session: Any,
    session_dir: Any,
) -> None:
    """INV-018 / INV-032: the session config is written into `agent/config/`."""
    ctx = make_session("workspace-config", mode="chat")

    workspace = session_dir(ctx["session"])["workspace"]
    config_file = workspace / "agent" / "config" / "config.json"

    assert config_file.is_file(), "the session configuration must be persisted"
    assert ctx["session_id"] in config_file.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_a_turn_writes_its_deliverable_into_the_data_directory(
    client: httpx.AsyncClient,
    make_session: Any,
    queue_agent_turn: Any,
    resolve_session: Any,
    session_dir: Any,
) -> None:
    """INV-018: a tool that writes a file lands in the tracked data directory."""
    ctx = make_session("workspace-write", mode="chat")

    queue_agent_turn(
        ctx["session_id"],
        tool_calls=[
            SteerableToolCall(
                name="write_file",
                args={"file_path": "/workspace/notes/finding.md", "content": "a finding"},
            )
        ],
    )
    queue_agent_turn(ctx["session_id"], text="Wrote the note.")

    await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "write the note"},
    )

    session = resolve_session(ctx["session_id"])
    runner = get_runner_registry().get_runner(session)
    await _drain(runner)

    data_dir = session_dir(ctx["session"])["data"]
    assert (data_dir / "notes" / "finding.md").is_file()


@pytest.mark.asyncio
async def test_a_session_skill_shadows_the_bundled_skill(
    client: httpx.AsyncClient,
    make_session: Any,
    session_dir: Any,
) -> None:
    """INV-035: a workspace skill wins over the bundled skill of the same name."""
    ctx = make_session("workspace-skill-shadow", mode="chat")

    data_dir = session_dir(ctx["session"])["data"]
    _write_skill(
        data_dir / "skills" / "artifacts",
        "artifacts",
        "The session's own artifacts skill.",
    )

    body = (
        await client.get(
            f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/inspect"
        )
    ).json()

    skills = {skill["name"]: skill for skill in body["skills"]}
    assert "artifacts" in skills
    assert skills["artifacts"]["origin_layer"] != "Bundled", (
        "the session skill must shadow the bundled skill"
    )


@pytest.mark.asyncio
async def test_the_bundled_skills_are_discovered(
    client: httpx.AsyncClient,
    make_session: Any,
) -> None:
    """INV-047 / REQ-043: the bundled platform skills are always available."""
    ctx = make_session("workspace-bundled-skills", mode="chat")

    body = (
        await client.get(
            f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/inspect"
        )
    ).json()

    origins = {skill["origin_layer"] for skill in body["skills"]}
    assert "Bundled" in origins


@pytest.mark.asyncio
async def test_the_sandbox_receives_the_session_skill_mounts(
    client: httpx.AsyncClient,
    make_session: Any,
    stub_sandbox: list[Any],
    queue_agent_turn: Any,
    resolve_session: Any,
) -> None:
    """INV-031 / INV-047: the skill sources are mounted into the sandbox."""
    ctx = make_session("workspace-skill-mounts", mode="chat")
    queue_agent_turn(ctx["session_id"], text="ok")

    await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "hello"},
    )
    session = resolve_session(ctx["session_id"])
    runner = get_runner_registry().get_runner(session)
    await _drain(runner)

    assert stub_sandbox, "the session must provision a sandbox"
    sources = stub_sandbox[-1].get_skill_sources()
    mounted = {virtual for virtual, _label in sources}

    assert "/workspace/skills" in mounted
    assert "/workspace/.skills" in mounted


@pytest.mark.asyncio
async def test_the_workspace_is_read_only_during_the_make_phase(
    client: httpx.AsyncClient,
    make_session: Any,
    stub_sandbox: list[Any],
    queue_agent_turn: Any,
    resolve_session: Any,
) -> None:
    """REQ-017 / INV-041: the make phase mounts the workspace read-only."""
    ctx = make_session("workspace-readonly", mode="plan", phase="make")
    queue_agent_turn(ctx["session_id"], text="ok")

    await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "hello"},
    )
    session = resolve_session(ctx["session_id"])
    runner = get_runner_registry().get_runner(session)
    await _drain(runner)

    assert stub_sandbox, "the session must provision a sandbox"
    assert stub_sandbox[-1].workspace_readonly is True


@pytest.mark.asyncio
async def test_the_workspace_is_writable_in_chat_mode(
    client: httpx.AsyncClient,
    make_session: Any,
    stub_sandbox: list[Any],
    queue_agent_turn: Any,
    resolve_session: Any,
) -> None:
    """REQ-017: the chat mode mounts the workspace read-write."""
    ctx = make_session("workspace-writable", mode="chat")
    queue_agent_turn(ctx["session_id"], text="ok")

    await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "hello"},
    )
    session = resolve_session(ctx["session_id"])
    runner = get_runner_registry().get_runner(session)
    await _drain(runner)

    assert stub_sandbox, "the session must provision a sandbox"
    assert stub_sandbox[-1].workspace_readonly is False


@pytest.mark.asyncio
async def test_a_retained_skill_survives_a_phase_transition(
    client: httpx.AsyncClient,
    make_session: Any,
    queue_agent_turn: Any,
    resolve_session: Any,
) -> None:
    """REQ-049 / INV-060: a retained skill stays active across the transition.

    The `artifacts` skill is loaded and declared as retained, so it must
    still be active on the thread that the transition opens.
    """
    ctx = make_session("workspace-retained-skill", mode="plan", phase="discuss")

    queue_agent_turn(
        ctx["session_id"],
        tool_calls=[SteerableToolCall(name="load_skill", args={"name": "artifacts"})],
    )
    queue_agent_turn(
        ctx["session_id"],
        tool_calls=[
            SteerableToolCall(
                name="plan",
                args={"retained_skills": ["artifacts"]},
            )
        ],
    )
    queue_agent_turn(ctx["session_id"], text="Moving on.")

    await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "load the skill and move to make"},
    )

    session = resolve_session(ctx["session_id"])
    runner = get_runner_registry().get_runner(session)
    await _drain(runner)

    open_thread = session.get_open_thread()
    assert open_thread is not None
    assert open_thread.mode == "plan"
    assert open_thread.phase == "make"
    assert "artifacts" in open_thread.active_skills, (
        "a retained skill must survive the phase transition"
    )
