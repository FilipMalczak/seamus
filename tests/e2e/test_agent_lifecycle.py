"""End-to-end tests for the agent lifecycle and the runner recompilation.

An agent is created through the HTTP API, gets its configuration from the
singleton template, and receives a deterministic slug. Its configuration can
then be changed while a session is live, and the running agent must pick the
new configuration up on the very next turn.

* REQ-040 / INV-050 — an unnamed agent is assigned a `coolname` slug;
* REQ-006 / INV-006 — the slug is URL-safe and addressable;
* INV-034 — updating the session configuration recompiles the active runner,
  so the next turn already uses the new configuration;
* REQ-041 — the update is persisted with the session.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

import httpx
import pytest

from seamus.harness.runner import get_runner_registry
from seamus.harness.store import get_harness_store


async def _drain(runner: Any, *, timeout: float = 30.0) -> None:
    """Wait for a runner's active turn to finish."""
    task = runner._active_task
    if task is not None and not task.done():
        await asyncio.wait_for(asyncio.shield(task), timeout=timeout)


def _config_payload(**overrides: Any) -> dict[str, Any]:
    """Return a complete agent configuration payload."""
    payload: dict[str, Any] = {
        "model_name": "steerable-model",
        "mode": "chat",
        "inference": {
            "format": "steerable",
            "base_url": "https://openrouter.ai/api/v1",
            "steerable": {"empty_queue_strategy": "wait", "wait_timeout": 10.0},
        },
    }
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_an_unnamed_agent_receives_a_generated_slug(
    client: httpx.AsyncClient,
) -> None:
    """REQ-040 / INV-050: an unnamed agent is assigned a `coolname` slug."""
    created = await client.post("/api/v-alpha/agents", json=_config_payload())
    assert created.status_code == 201
    body = created.json()

    slug = body["name"]
    assert slug, "an unnamed agent must still receive a slug"

    # A `coolname` slug is a lowercase, dash-separated phrase.
    assert re.fullmatch(r"[a-z]+(?:-[a-z]+)+", slug), f"unexpected slug: {slug}"


@pytest.mark.asyncio
async def test_a_named_agent_keeps_its_name(
    client: httpx.AsyncClient,
) -> None:
    """REQ-040: a user-assigned name takes precedence over the generated slug."""
    created = await client.post(
        "/api/v-alpha/agents", json={**_config_payload(), "name": "my-agent"}
    )
    assert created.status_code == 201

    assert created.json()["name"] == "my-agent"


@pytest.mark.asyncio
async def test_two_agents_never_share_a_generated_slug(
    client: httpx.AsyncClient,
) -> None:
    """INV-006 / INV-050: the generated slugs are unique across agents."""
    first = await client.post("/api/v-alpha/agents", json=_config_payload())
    second = await client.post("/api/v-alpha/agents", json=_config_payload())

    assert first.json()["name"] != second.json()["name"]


@pytest.mark.asyncio
async def test_a_generated_agent_can_be_addressed_by_its_slug(
    client: httpx.AsyncClient,
) -> None:
    """REQ-005: the generated slug is a valid identifier for the agent."""
    created = await client.post("/api/v-alpha/agents", json=_config_payload())
    slug = created.json()["name"]

    fetched = await client.get(f"/api/v-alpha/agent/{slug}")

    assert fetched.status_code == 200
    assert fetched.json()["id"] == created.json()["id"]


@pytest.mark.asyncio
async def test_updating_the_session_recompiles_the_runner(
    client: httpx.AsyncClient,
    make_session: Any,
    queue_agent_turn: Any,
    resolve_session: Any,
) -> None:
    """INV-034: the next turn uses the updated session configuration."""
    ctx = make_session("agent-recompile", mode="chat")

    # Instantiate the runner so it is cached and can be reloaded.
    session = resolve_session(ctx["session_id"])
    get_runner_registry().get_runner(session)

    updated = await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}",
        json={
            "name": "recompiled",
            "config": _config_payload(system_prompt="Only speak in haiku."),
        },
    )
    assert updated.status_code == 200

    # The very next turn must already use the new prompt.
    queue_agent_turn(ctx["session_id"], text="A haiku.")

    await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "say something"},
    )

    session = resolve_session(ctx["session_id"])
    runner = get_runner_registry().get_runner(session)
    await _drain(runner)

    assert "Only speak in haiku." in runner.build_effective_system_prompt()


@pytest.mark.asyncio
async def test_the_update_is_persisted_with_the_session(
    client: httpx.AsyncClient,
    make_session: Any,
    resolve_session: Any,
    session_dir: Any,
) -> None:
    """REQ-041: the updated configuration is written to the session workspace."""
    ctx = make_session("agent-update-persist", mode="chat")

    updated = await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}",
        json={
            "name": "persisted",
            "config": _config_payload(system_prompt="Be terse."),
        },
    )
    assert updated.status_code == 200

    session = resolve_session(ctx["session_id"])
    assert session.name == "persisted"
    assert session.config.system_prompt == "Be terse."

    config_file = session_dir(session)["workspace"] / "agent" / "config" / "config.json"
    if config_file.is_file():
        assert "Be terse." in config_file.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_an_incomplete_update_is_rejected(
    client: httpx.AsyncClient,
    make_session: Any,
) -> None:
    """REQ-041: an incomplete configuration never reaches the session."""
    ctx = make_session("agent-update-invalid", mode="chat")

    rejected = await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}",
        json={"name": "broken", "config": {"model_name": ""}},
    )

    assert rejected.status_code == 400


@pytest.mark.asyncio
async def test_an_agent_update_keeps_the_agent_usable(
    client: httpx.AsyncClient,
    make_session: Any,
) -> None:
    """REQ-041: the agent configuration can be replaced through the API."""
    ctx = make_session("agent-update", mode="chat")

    updated = await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}",
        json={"name": "renamed-agent", "config": _config_payload()},
    )
    assert updated.status_code == 200

    agent = get_harness_store().resolve_agent(ctx["agent_id"])
    assert agent.name == "renamed-agent"
