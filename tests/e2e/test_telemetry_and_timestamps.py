"""End-to-end tests for telemetry spans and event timestamps.

Two concerns are covered:

* **Telemetry** — a scripted turn must produce the hierarchical
  ``agent → session → thread`` Logfire span tree, and the HTTP layer must
  emit request spans for API calls while excluding health probes.
* **Timestamps** — AG-UI events must carry an authoritative emission
  timestamp so the UI can render bubble times from the backend rather than
  from client-side render time.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import logfire
import pytest
from logfire.testing import TestExporter
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

from seamus.harness.runner import get_runner_registry
from seamus.telemetry import _scrub_callback


async def _drain(runner: Any, *, timeout: float = 60.0) -> None:
    """Wait for a runner's active turn to finish."""
    task = runner._active_task
    if task is not None and not task.done():
        await asyncio.wait_for(asyncio.shield(task), timeout=timeout)


@pytest.fixture
def span_exporter() -> TestExporter:
    """Configure Logfire to export spans into an in-memory buffer."""
    exporter = TestExporter()
    logfire.configure(
        send_to_logfire=False,
        console=False,
        scrubbing=logfire.ScrubbingOptions(callback=_scrub_callback),
        additional_span_processors=[SimpleSpanProcessor(exporter)],
        inspect_arguments=False,
    )
    return exporter


@pytest.mark.asyncio
async def test_scripted_turn_emits_agent_session_thread_spans(
    client: httpx.AsyncClient,
    make_session: Any,
    queue_agent_turn: Any,
    resolve_session: Any,
    span_exporter: TestExporter,
) -> None:
    """A scripted turn produces the hierarchical agent/session/thread span tree."""
    ctx = make_session("telemetry-spans", mode="chat")
    queue_agent_turn(ctx["session_id"], text="traced answer")

    await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "traced question"},
    )

    session = resolve_session(ctx["session_id"])
    runner = get_runner_registry().get_runner(session)
    await _drain(runner)

    spans = span_exporter.exported_spans_as_dict()
    by_name = {s["name"]: s for s in spans}

    agent_span = by_name.get("agent telemetry-spans")
    session_span = by_name.get(f"session {ctx['session_id']}")
    thread_span = by_name.get(f"thread {ctx['thread_id']}")

    assert agent_span is not None, "agent span missing"
    assert session_span is not None, "session span missing"
    assert thread_span is not None, "thread span missing"

    assert agent_span["attributes"]["agent_id"] == ctx["agent_id"]
    assert session_span["attributes"]["session_id"] == ctx["session_id"]
    assert thread_span["attributes"]["thread_id"] == ctx["thread_id"]

    # The hierarchy must nest thread inside session inside agent.
    assert thread_span["parent"]["span_id"] == session_span["context"]["span_id"]
    assert session_span["parent"]["span_id"] == agent_span["context"]["span_id"]
    assert thread_span["context"]["trace_id"] == agent_span["context"]["trace_id"]


@pytest.mark.asyncio
async def test_api_request_emits_span_but_health_probe_does_not(
    client: httpx.AsyncClient,
    span_exporter: TestExporter,
) -> None:
    """API calls are traced; the health probe is excluded from tracing."""
    health = await client.get("/health")
    assert health.status_code == 200

    health_spans = [
        s
        for s in span_exporter.exported_spans_as_dict()
        if "/health" in str(s.get("attributes", {})) or "/health" in s.get("name", "")
    ]
    assert health_spans == []

    info = await client.get("/api/v-alpha/system/info")
    assert info.status_code == 200

    api_spans = [
        s
        for s in span_exporter.exported_spans_as_dict()
        if "/api/v-alpha" in s.get("name", "") or "/system/info" in str(s.get("attributes", {}))
    ]
    assert api_spans, "no span emitted for the API request"


@pytest.mark.asyncio
async def test_events_carry_authoritative_emission_timestamps(
    client: httpx.AsyncClient,
    make_session: Any,
    queue_agent_turn: Any,
    resolve_session: Any,
) -> None:
    """INV-056: AG-UI events carry the backend emission timestamp.

    Currently unimplemented — the backend emits events without a
    ``timestamp`` value, so the UI falls back to client-side render time.
    Tracked as technical debt in ``knowledge/backlog.md``.
    """
    ctx = make_session("event-timestamps", mode="chat")
    queue_agent_turn(ctx["session_id"], text="timestamped answer")

    await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "timestamped question"},
    )

    session = resolve_session(ctx["session_id"])
    runner = get_runner_registry().get_runner(session)
    await _drain(runner)

    thread = session.get_open_thread()
    assert thread is not None
    assert thread.events, "no events recorded"

    missing = [type(ev).__name__ for ev in thread.events if getattr(ev, "timestamp", None) is None]
    assert not missing, f"events without an emission timestamp: {sorted(set(missing))}"


@pytest.mark.asyncio
async def test_streamed_events_expose_timestamps_to_clients(
    client: httpx.AsyncClient,
    make_session: Any,
    queue_agent_turn: Any,
    resolve_session: Any,
) -> None:
    """The SSE replay exposes the emission timestamp of each event.

    Currently unimplemented — see the technical-debt entry on client-side
    render-time timestamps in ``knowledge/backlog.md``.
    """
    ctx = make_session("stream-timestamps", mode="chat")
    queue_agent_turn(ctx["session_id"], text="streamed answer")

    await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "streamed question"},
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

    assert "TEXT_MESSAGE_START" in body
    assert '"timestamp"' in body, "streamed events carry no timestamp field"
