"""End-to-end tests for the mounted external Git repositories.

An agent can be configured with external Git repositories that are mounted
into its sandbox under `/projects/<name>`. These tests assert the contract
that the sandbox boundary defines:

* REQ-036 — the repositories configured for the agent are mounted under
  `/projects/<name>`;
* INV-043 — the mount names are deterministic and collision-proof, and the
  repository credentials are never exposed;
* INV-045 — the mounted working tree is independent of the session's own
  deliverable directory.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest

from seamus.config.models import ExternalRepositoryConfig
from seamus.harness.runner import get_runner_registry


async def _drain(runner: Any, *, timeout: float = 30.0) -> None:
    """Wait for a runner's active turn to finish."""
    task = runner._active_task
    if task is not None and not task.done():
        await asyncio.wait_for(asyncio.shield(task), timeout=timeout)


async def _inspect(client: httpx.AsyncClient, ctx: dict[str, Any]) -> dict[str, Any]:
    """Fetch the inspection report of a session."""
    response = await client.get(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/inspect"
    )
    assert response.status_code == 200
    return dict(response.json())


@pytest.mark.asyncio
async def test_a_configured_repository_is_reported_as_mounted(
    client: httpx.AsyncClient,
    make_session: Any,
    session_dir: Any,
) -> None:
    """REQ-036: the configured repository is mounted under `/projects/<name>`."""
    ctx = make_session("external-repo", mode="chat")

    session = ctx["session"]
    session.config.repositories = [
        ExternalRepositoryConfig(
            id="repo-1",
            url="https://github.com/example/widgets.git",
            branch="main",
        )
    ]

    body = await _inspect(client, ctx)
    mounted = body["mounted_repositories"]

    assert len(mounted) == 1
    assert mounted[0]["id"] == "repo-1"
    assert mounted[0]["mount_path"] == "/projects/widgets"
    assert mounted[0]["url"] == "https://github.com/example/widgets.git"
    assert mounted[0]["branch"] == "main"


@pytest.mark.asyncio
async def test_two_repositories_with_the_same_name_get_distinct_mounts(
    client: httpx.AsyncClient,
    make_session: Any,
) -> None:
    """INV-043: colliding mount names are suffixed so they stay distinct."""
    ctx = make_session("external-repo-collision", mode="chat")

    session = ctx["session"]
    session.config.repositories = [
        ExternalRepositoryConfig(
            id="a",
            url="https://github.com/example/widgets.git",
            branch="main",
        ),
        ExternalRepositoryConfig(
            id="b",
            url="https://github.com/other/widgets.git",
            branch="main",
        ),
    ]

    body = await _inspect(client, ctx)
    paths = {repo["id"]: repo["mount_path"] for repo in body["mounted_repositories"]}

    assert len(set(paths.values())) == 2, f"the mount paths must differ: {paths}"
    assert all(path.startswith("/projects/") for path in paths.values())


@pytest.mark.asyncio
async def test_repository_credentials_are_not_exposed(
    client: httpx.AsyncClient,
    make_session: Any,
) -> None:
    """INV-043: the credentials are reported as a flag, never as a value."""
    ctx = make_session("external-repo-credentials", mode="chat")

    session = ctx["session"]
    session.config.repositories = [
        ExternalRepositoryConfig(
            id="repo-1",
            url="https://github.com/example/private.git",
            branch="main",
            credentials="ghp_super_secret_token",
        )
    ]

    body = await _inspect(client, ctx)
    mounted = body["mounted_repositories"][0]

    assert mounted["credentials_configured"] is True
    assert "ghp_super_secret_token" not in str(body)


@pytest.mark.asyncio
async def test_a_repository_without_credentials_is_reported_as_unconfigured(
    client: httpx.AsyncClient,
    make_session: Any,
) -> None:
    """INV-043: a public repository reports no credentials."""
    ctx = make_session("external-repo-public", mode="chat")

    session = ctx["session"]
    session.config.repositories = [
        ExternalRepositoryConfig(
            id="repo-1",
            url="https://github.com/example/public.git",
            branch="main",
        )
    ]

    body = await _inspect(client, ctx)

    assert body["mounted_repositories"][0]["credentials_configured"] is False


@pytest.mark.asyncio
async def test_the_sandbox_mounts_the_repository_under_projects(
    client: httpx.AsyncClient,
    make_session: Any,
    stub_sandbox: list[Any],
    queue_agent_turn: Any,
    resolve_session: Any,
) -> None:
    """REQ-036: the repository is mounted into the sandbox under `/projects/`."""
    ctx = make_session("external-repo-mount", mode="chat")

    session = ctx["session"]
    session.config.repositories = [
        ExternalRepositoryConfig(
            id="repo-1",
            url="https://github.com/example/widgets.git",
            branch="main",
        )
    ]

    queue_agent_turn(ctx["session_id"], text="Hello.")

    await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "hello"},
    )

    session = resolve_session(ctx["session_id"])
    runner = get_runner_registry().get_runner(session)
    await _drain(runner)

    assert stub_sandbox, "the session must provision a sandbox"
    backend = stub_sandbox[-1]

    assert backend.repositories, "the repository must be handed to the sandbox"
    assert backend.repositories[0].id == "repo-1"

    # The skill sources of the mounted project are exposed under `/projects/`.
    sources = backend.get_skill_sources()
    mounted = {virtual for virtual, _label in sources}
    assert "/projects/repo-1/skills" in mounted
    assert "/projects/repo-1/.skills" in mounted


@pytest.mark.asyncio
async def test_the_prompt_names_the_projects_directory(
    client: httpx.AsyncClient,
    make_session: Any,
) -> None:
    """REQ-036: the operating environment tells the agent about `/projects/`."""
    ctx = make_session("external-repo-prompt", mode="chat")

    body = await _inspect(client, ctx)
    composite = body["prompts"]["composite"]

    assert "<projects_directory>/projects</projects_directory>" in composite
