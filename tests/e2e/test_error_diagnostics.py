"""End-to-end baseline for error diagnostics.

``INV-039`` requires a failing turn to emit a ``RUN_ERROR`` event carrying
``error_type`` and ``traceback``, appended to the thread's event log before it
is broadcast, so that the failure survives a reload and reaches the client
through the ordinary event stream.

The failure is produced deterministically with the ``steerable`` provider's
``error`` empty-queue strategy: an empty queue raises
``SteerableQueueEmptyError`` inside the agent run, which is exactly the kind
of unhandled provider failure the invariant describes.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest

from seamus.config.models import (
    AgentConfig,
    InferenceConfig,
    InferenceFormat,
    SteerableConfig,
    SteerableEmptyQueueStrategy,
)
from seamus.harness.runner import get_runner_registry


async def _drain(runner: Any, *, timeout: float = 30.0) -> None:
    """Wait for a runner's active turn to finish."""
    task = runner._active_task
    if task is not None and not task.done():
        await asyncio.wait_for(asyncio.shield(task), timeout=timeout)


def _make_failing_session(store: Any, name: str) -> dict[str, Any]:
    """Create a session whose steerable model fails on an empty queue."""
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
    )
    agent = store.create_agent(config=config, name=name)
    session = store.create_session(agent_identifier=str(agent.id))
    thread = session.get_open_thread()
    return {
        "agent": agent,
        "session": session,
        "thread": thread,
        "agent_id": str(agent.id),
        "session_id": str(session.id),
        "thread_id": str(thread.id) if thread else None,
    }


def _run_errors(thread: Any) -> list[Any]:
    """Return the ``RUN_ERROR`` events recorded on a thread."""
    return [
        event
        for event in thread.events
        if (isinstance(event, dict) and event.get("type") == "RUN_ERROR")
        or getattr(event, "type", None) == "RUN_ERROR"
    ]


def _event_field(event: Any, field: str) -> Any:
    """Read a field from either a dict-shaped or object-shaped event."""
    if isinstance(event, dict):
        return event.get(field)
    return getattr(event, field, None)


@pytest.mark.asyncio
async def test_a_failing_turn_records_a_run_error_event(
    client: httpx.AsyncClient,
    steerable_store: Any,
    resolve_session: Any,
) -> None:
    """A failing turn records a ``RUN_ERROR`` event on the thread."""
    ctx = _make_failing_session(steerable_store, "run-error")

    await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "Trigger a provider failure."},
    )

    session = resolve_session(ctx["session_id"])
    runner = get_runner_registry().get_runner(session)
    await _drain(runner)

    thread = session.get_open_thread()
    assert thread is not None

    errors = _run_errors(thread)
    assert len(errors) == 1
    assert _event_field(errors[0], "message")


@pytest.mark.asyncio
async def test_a_failing_turn_replays_the_run_error_through_the_thread_stream(
    client: httpx.AsyncClient,
    steerable_store: Any,
    resolve_session: Any,
) -> None:
    """The ``RUN_ERROR`` survives into the replayed thread stream."""
    ctx = _make_failing_session(steerable_store, "run-error-stream")

    await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "Trigger a provider failure."},
    )

    session = resolve_session(ctx["session_id"])
    runner = get_runner_registry().get_runner(session)
    await _drain(runner)

    stream = await client.get(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}"
        f"/thread/{ctx['thread_id']}?follow=false"
    )

    assert stream.status_code == 200
    body = stream.text
    assert "RUN_ERROR" in body
    assert "empty response queue" in body


@pytest.mark.asyncio
async def test_a_failing_turn_marks_the_thread_as_failed(
    client: httpx.AsyncClient,
    steerable_store: Any,
    resolve_session: Any,
) -> None:
    """A failing turn leaves the thread in an error state."""
    ctx = _make_failing_session(steerable_store, "run-error-status")

    await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "Trigger a provider failure."},
    )

    session = resolve_session(ctx["session_id"])
    runner = get_runner_registry().get_runner(session)
    await _drain(runner)

    thread = session.get_open_thread()
    assert thread is not None
    assert thread.status.value == "ERROR"


@pytest.mark.asyncio
async def test_a_failing_turn_persists_the_error_type_and_traceback(
    client: httpx.AsyncClient,
    steerable_store: Any,
    resolve_session: Any,
) -> None:
    """INV-039: the persisted ``RUN_ERROR`` carries the error type and traceback.

    Currently unimplemented on the e2e path — the AG-UI layer swallows the
    provider exception and emits a message-only ``RunErrorEvent``. Tracked in
    ``knowledge/backlog.md``.
    """
    ctx = _make_failing_session(steerable_store, "run-error-diagnostics")

    await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "Trigger a provider failure."},
    )

    session = resolve_session(ctx["session_id"])
    runner = get_runner_registry().get_runner(session)
    await _drain(runner)

    thread = session.get_open_thread()
    assert thread is not None

    errors = _run_errors(thread)
    assert len(errors) == 1
    error = errors[0]
    assert _event_field(error, "error_type") == "SteerableQueueEmptyError"
    assert "SteerableQueueEmptyError" in (_event_field(error, "traceback") or "")


@pytest.mark.asyncio
async def test_the_streamed_run_error_exposes_the_error_type(
    client: httpx.AsyncClient,
    steerable_store: Any,
    resolve_session: Any,
) -> None:
    """INV-039: the streamed ``RUN_ERROR`` exposes the error type to the client.

    Currently unimplemented — see the technical-debt entry on error reporting
    in ``knowledge/backlog.md``.
    """
    ctx = _make_failing_session(steerable_store, "run-error-stream-diagnostics")

    await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "Trigger a provider failure."},
    )

    session = resolve_session(ctx["session_id"])
    runner = get_runner_registry().get_runner(session)
    await _drain(runner)

    stream = await client.get(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}"
        f"/thread/{ctx['thread_id']}?follow=false"
    )

    assert stream.status_code == 200
    assert "SteerableQueueEmptyError" in stream.text
