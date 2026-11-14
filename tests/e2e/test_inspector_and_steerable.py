"""End-to-end tests for the agent inspector and the steerable control surface.

The inspector report is produced from the *live* runner of a real session, so
these tests assert on the same data the Web UI consumes: tool inventory with
JSON schemas and backends, decomposed prompts, redacted credentials and the
conversation history.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest

from seamus.harness.runner import get_runner_registry
from seamus.harness.steerable import agent_instance_id, daemon_instance_id


def _ensure_runner(ctx: dict[str, Any]) -> Any:
    """Instantiate the session runner so its steerable instance is registered."""
    session = ctx["session"]
    return get_runner_registry().get_runner(session)


async def _drain(runner: Any, *, timeout: float = 30.0) -> None:
    """Wait for a runner's active turn to finish."""
    task = runner._active_task
    if task is not None and not task.done():
        await asyncio.wait_for(asyncio.shield(task), timeout=timeout)


@pytest.mark.asyncio
async def test_inspect_report_exposes_tools_without_secrets(
    client: httpx.AsyncClient,
    make_session: Any,
    queue_agent_turn: Any,
    resolve_session: Any,
) -> None:
    """INV-021: the inspector exposes tools and never leaks raw credentials."""
    ctx = make_session("inspect-tools", mode="chat")
    queue_agent_turn(ctx["session_id"], text="Hello.")

    await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "hi"},
    )
    session = resolve_session(ctx["session_id"])
    runner = get_runner_registry().get_runner(session)
    await _drain(runner)

    report = await client.get(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/inspect"
    )
    assert report.status_code == 200
    body = report.json()

    # Credentials are reported as a boolean flag only.
    assert body["inference"]["api_key_configured"] is False
    assert "api_key" not in body["inference"]

    # Tools carry a JSON schema and a backend.
    tools = {tool["name"]: tool for tool in body["tools"]}
    assert tools, "the inspector must report at least one tool"
    for tool in body["tools"]:
        assert tool["description"]
        assert isinstance(tool["parameters"], dict)
        assert tool["backend"]

    # The prompt is decomposed into layers.
    assert body["prompts"]["composite"]
    assert body["prompts"]["scaffold"]
    assert "custom" in body["prompts"]


@pytest.mark.asyncio
async def test_inspect_report_reflects_conversation_history(
    client: httpx.AsyncClient,
    make_session: Any,
    queue_agent_turn: Any,
    resolve_session: Any,
) -> None:
    """The inspector history mirrors the recorded conversation turns."""
    ctx = make_session("inspect-history", mode="chat")
    queue_agent_turn(ctx["session_id"], reasoning="thinking", text="The answer.")

    await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "the question"},
    )
    session = resolve_session(ctx["session_id"])
    runner = get_runner_registry().get_runner(session)
    await _drain(runner)

    report = await client.get(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/inspect"
    )
    assert report.status_code == 200
    history = report.json()["history"]

    assert history["message_count"] > 0
    roles = {message["role"] for message in history["messages"]}
    assert "user" in roles
    assert "assistant" in roles


@pytest.mark.asyncio
async def test_inspect_report_lists_steerable_models(
    client: httpx.AsyncClient,
    make_session: Any,
    queue_agent_turn: Any,
    resolve_session: Any,
) -> None:
    """INV-062: the inspector lists the session's steerable model instances."""
    ctx = make_session("inspect-steerable", mode="chat")
    queue_agent_turn(ctx["session_id"], text="Hello.")

    await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "hi"},
    )
    session = resolve_session(ctx["session_id"])
    runner = get_runner_registry().get_runner(session)
    await _drain(runner)

    report = await client.get(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/inspect"
    )
    assert report.status_code == 200
    steerable = report.json()["steerable_models"]
    assert steerable
    instance_ids = {entry["instance_id"] for entry in steerable}
    assert agent_instance_id(ctx["session_id"]) in instance_ids


@pytest.mark.asyncio
async def test_steerable_queue_can_be_replaced_and_cleared(
    client: httpx.AsyncClient,
    make_session: Any,
) -> None:
    """INV-062 / INV-007: the queue is replaced (never deleted) via PUT."""
    ctx = make_session("steerable-queue", mode="chat")
    instance_id = agent_instance_id(ctx["session_id"])
    _ensure_runner(ctx)

    appended = await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}"
        f"/steerable/{instance_id}/responses",
        json={"responses": [{"text": "one"}, {"text": "two"}]},
    )
    assert appended.status_code == 200
    assert appended.json()["pending_count"] == 2

    replaced = await client.put(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}"
        f"/steerable/{instance_id}/responses",
        json={"responses": [{"text": "only"}]},
    )
    assert replaced.status_code == 200
    assert replaced.json()["pending_count"] == 1

    cleared = await client.put(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}"
        f"/steerable/{instance_id}/responses",
        json={"responses": []},
    )
    assert cleared.status_code == 200
    assert cleared.json()["pending_count"] == 0


@pytest.mark.asyncio
async def test_steerable_strategy_can_be_switched(
    client: httpx.AsyncClient,
    make_session: Any,
) -> None:
    """INV-062: the empty-queue strategy is switchable at runtime."""
    ctx = make_session("steerable-strategy", mode="chat")
    instance_id = agent_instance_id(ctx["session_id"])
    _ensure_runner(ctx)

    patched = await client.patch(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}"
        f"/steerable/{instance_id}/strategy",
        json={"strategy": "repeat", "default_response": "fallback", "wait_timeout": 5.0},
    )
    assert patched.status_code == 200
    body = patched.json()
    assert body["strategy"] == "repeat"
    assert body["default_response"] == "fallback"
    assert body["wait_timeout"] == 5.0


@pytest.mark.asyncio
async def test_steerable_instances_are_listed_per_session(
    client: httpx.AsyncClient,
    make_session: Any,
) -> None:
    """INV-062: agent and daemon queues are separate instances of one session."""
    ctx = make_session("steerable-list", mode="chat", naming_daemon=True)
    agent_id = agent_instance_id(ctx["session_id"])
    daemon_id = daemon_instance_id(ctx["session_id"])
    _ensure_runner(ctx)

    for instance_id in (agent_id, daemon_id):
        await client.post(
            f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}"
            f"/steerable/{instance_id}/responses",
            json={"responses": [{"text": "queued"}]},
        )

    listed = await client.get(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/steerable"
    )
    assert listed.status_code == 200
    instances = {entry["instance_id"]: entry for entry in listed.json()}
    assert agent_id in instances
    assert daemon_id in instances
    assert instances[agent_id]["role"] == "agent"
    assert instances[daemon_id]["role"] == "daemon"
    assert instances[agent_id]["pending_count"] == 1
    assert instances[daemon_id]["pending_count"] == 1


@pytest.mark.asyncio
async def test_steerable_response_for_unknown_instance_is_404(
    client: httpx.AsyncClient,
    make_session: Any,
) -> None:
    """An unknown steerable instance is reported as 404, not 500."""
    ctx = make_session("steerable-unknown", mode="chat")
    _ensure_runner(ctx)
    res = await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}"
        f"/steerable/session:{ctx['session_id']}:nope/responses",
        json={"responses": [{"text": "x"}]},
    )
    assert res.status_code == 404
