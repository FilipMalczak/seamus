"""End-to-end tests for the autocontinue daemon.

Tests that a session failure triggers the autocontinue daemon via steerable simulation,
branching a child session when retry is advised, or disabling the session on 'stop, its dead Jim'.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest

from seamus.config.models import (
    AgentConfig,
    DaemonAutocontinueConfig,
    DaemonsConfig,
    InferenceConfig,
    InferenceFormat,
    SteerableConfig,
    SteerableEmptyQueueStrategy,
)
from seamus.harness.runner import get_runner_registry
from seamus.harness.steerable import SteerableResponse, daemon_instance_id, get_steerable_registry


async def _drain(runner: Any, *, timeout: float = 30.0) -> None:
    """Wait for a runner's active task to finish."""
    task = runner._active_task
    if task is not None and not task.done():
        await asyncio.wait_for(asyncio.shield(task), timeout=timeout)


def _make_autocontinue_session(
    store: Any,
    name: str,
) -> dict[str, Any]:
    """Create a session with steerable agent provider and steerable autocontinue daemon."""
    config = AgentConfig(
        inference=InferenceConfig(
            format=InferenceFormat.STEERABLE,
            base_url="https://openrouter.ai/api/v1",
            steerable=SteerableConfig(
                empty_queue_strategy=SteerableEmptyQueueStrategy.ERROR,
                wait_timeout=1.0,
            ),
        ),
        model_name="steerable-model",
        mode="chat",
        daemons=DaemonsConfig(
            autocontinue=DaemonAutocontinueConfig(
                enabled=True,
                model="steerable-autocontinue",
                provider=InferenceConfig(
                    format=InferenceFormat.STEERABLE,
                    base_url="https://openrouter.ai/api/v1",
                    steerable=SteerableConfig(
                        empty_queue_strategy=SteerableEmptyQueueStrategy.WAIT,
                        wait_timeout=5.0,
                    ),
                ),
            )
        ),
    )
    agent = store.create_agent(config=config, name=name)
    session = next(iter(agent.sessions.values()))
    thread = session.get_open_thread()
    return {
        "agent": agent,
        "session": session,
        "thread": thread,
        "agent_id": str(agent.id),
        "session_id": str(session.id),
        "thread_id": str(thread.id) if thread else None,
    }


@pytest.mark.asyncio
async def test_autocontinue_steerable_retry_branches_child_session(
    client: httpx.AsyncClient,
    steerable_store: Any,
    resolve_session: Any,
) -> None:
    """When a session fails and autocontinue responds 'retry', a child session is branched."""
    ctx = _make_autocontinue_session(steerable_store, "autocontinue-retry-agent")
    session = resolve_session(ctx["session_id"])
    agent = ctx["agent"]

    # Script the autocontinue daemon response to 'retry'
    daemon_id = daemon_instance_id(session.id, daemon="autocontinue")
    reg = get_steerable_registry()
    inst = reg.get_or_create(daemon_id, role="daemon")
    inst.push(SteerableResponse(text="retry"))

    # Post message to trigger unhandled provider failure (empty agent queue -> error)
    await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "Please do something that fails."},
    )

    runner = get_runner_registry().get_runner(session)
    await _drain(runner)

    # Verify session failed
    assert session.status.value == "FAILED"

    # Verify a new child session was created under the agent
    assert len(agent.sessions) == 2
    child_session = [s for s in agent.sessions.values() if s.id != session.id][0]
    assert child_session.provenance is not None
    assert child_session.provenance.parent_session_id == session.id
    assert child_session.provenance.branch_position == "after"


@pytest.mark.asyncio
async def test_autocontinue_steerable_dead_jim_disables_session(
    client: httpx.AsyncClient,
    steerable_store: Any,
    resolve_session: Any,
) -> None:
    """When autocontinue responds 'stop, its dead Jim', the session is permanently disabled."""
    ctx = _make_autocontinue_session(steerable_store, "autocontinue-deadjim-agent")
    session = resolve_session(ctx["session_id"])

    # Script the autocontinue daemon response to 'stop, its dead Jim'
    daemon_id = daemon_instance_id(session.id, daemon="autocontinue")
    reg = get_steerable_registry()
    inst = reg.get_or_create(daemon_id, role="daemon")
    inst.push(SteerableResponse(text="stop, its dead Jim"))

    await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "Please do something that fails."},
    )

    runner = get_runner_registry().get_runner(session)
    await _drain(runner)

    # Verify session is failed and disabled
    assert session.status.value == "FAILED"
    assert session.disabled is True
    assert session.config.daemons.autocontinue.enabled is False

    # Check HTTP API response reflects disabled=True
    resp = await client.get(f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["disabled"] is True
    assert data["status"] == "FAILED"
