"""End-to-end baseline for the naming daemons.

The naming daemons are non-agentic: they run a one-shot prompt against a
separate model instance and write a slug back onto the thread (and, for a
single-thread session, onto the session). They fire from inside the runner
loop on a geometric "stepback" schedule — after exchange 1, 3, 7, 15, ….

This file drives the daemon through the real runner loop with the scripted
``steerable`` provider, so the daemon consumes its own queue
(``session:{id}:daemon:naming``) independently of the agent's queue.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest

from seamus.harness.runner import get_runner_registry
from seamus.harness.steerable import SteerableResponse, daemon_instance_id, get_steerable_registry


async def _drain(runner: Any, *, timeout: float = 30.0) -> None:
    """Wait for a runner's active turn to finish."""
    task = runner._active_task
    if task is not None and not task.done():
        await asyncio.wait_for(asyncio.shield(task), timeout=timeout)


async def _wait_for(predicate: Any, *, timeout: float = 10.0) -> bool:
    """Poll ``predicate`` until it is truthy or the timeout elapses."""
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.05)
    return bool(predicate())


@pytest.mark.asyncio
async def test_naming_daemon_names_the_thread_after_the_first_exchange(
    client: httpx.AsyncClient,
    make_session: Any,
    queue_agent_turn: Any,
    resolve_session: Any,
) -> None:
    """After the first exchange the naming daemon writes a slug onto the thread."""
    ctx = make_session("daemon-naming", mode="chat", naming_daemon=True)

    # The daemon has its own queue; the agent's queue is separate.
    daemon = get_steerable_registry().get_or_create(daemon_instance_id(ctx["session_id"]), "daemon")
    daemon.push(SteerableResponse(text="fix-token-redirect-bug"))

    queue_agent_turn(ctx["session_id"], text="Working on the token redirect bug.")

    await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "Fix the token redirect bug."},
    )

    session = resolve_session(ctx["session_id"])
    runner = get_runner_registry().get_runner(session)
    await _drain(runner)

    thread = session.get_open_thread()
    assert thread is not None
    assert await _wait_for(lambda: bool(thread.daemon_name))
    assert thread.daemon_name == "fix-token-redirect-bug"


@pytest.mark.asyncio
async def test_naming_daemon_mirrors_the_slug_onto_a_single_thread_session(
    client: httpx.AsyncClient,
    make_session: Any,
    queue_agent_turn: Any,
    resolve_session: Any,
) -> None:
    """A session with one thread mirrors the thread's daemon slug onto the session."""
    ctx = make_session("daemon-session-naming", mode="chat", naming_daemon=True)

    daemon = get_steerable_registry().get_or_create(daemon_instance_id(ctx["session_id"]), "daemon")
    daemon.push(SteerableResponse(text="vault-secrets-integration"))

    queue_agent_turn(ctx["session_id"], text="Wiring the vault in.")

    await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "Wire the vault in."},
    )

    session = resolve_session(ctx["session_id"])
    runner = get_runner_registry().get_runner(session)
    await _drain(runner)

    assert await _wait_for(lambda: bool(session.daemon_name))
    assert session.daemon_name == "vault-secrets-integration"


@pytest.mark.asyncio
async def test_naming_daemon_parses_a_loose_model_output(
    client: httpx.AsyncClient,
    make_session: Any,
    queue_agent_turn: Any,
    resolve_session: Any,
) -> None:
    """A chatty daemon output is still parsed into a clean slug."""
    ctx = make_session("daemon-loose", mode="chat", naming_daemon=True)

    daemon = get_steerable_registry().get_or_create(daemon_instance_id(ctx["session_id"]), "daemon")
    daemon.push(SteerableResponse(text="Output: `docker-networking-fix`\n\nHope this helps!"))

    queue_agent_turn(ctx["session_id"], text="Fixing the network.")

    await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "Fix the network."},
    )

    session = resolve_session(ctx["session_id"])
    runner = get_runner_registry().get_runner(session)
    await _drain(runner)

    thread = session.get_open_thread()
    assert thread is not None
    assert await _wait_for(lambda: bool(thread.daemon_name))
    assert thread.daemon_name == "docker-networking-fix"


@pytest.mark.asyncio
async def test_naming_daemon_is_inert_when_disabled(
    client: httpx.AsyncClient,
    make_session: Any,
    queue_agent_turn: Any,
    resolve_session: Any,
) -> None:
    """With the naming daemon disabled no slug is written."""
    ctx = make_session("daemon-disabled", mode="chat", naming_daemon=False)

    queue_agent_turn(ctx["session_id"], text="No naming here.")

    await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "Hello."},
    )

    session = resolve_session(ctx["session_id"])
    runner = get_runner_registry().get_runner(session)
    await _drain(runner)

    thread = session.get_open_thread()
    assert thread is not None
    assert thread.daemon_name is None
    assert session.daemon_name is None
