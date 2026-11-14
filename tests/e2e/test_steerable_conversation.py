"""End-to-end tests for scripted (``steerable``) conversations.

These tests drive a real session through the production runner and the public
HTTP API. The only substitution is the inference provider: instead of calling a
model, the session consumes a scripted response queue. Everything else — event
generation, tool execution, status transitions, history persistence and replay
— is the production code path.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from seamus.domain.entities import AgentStatus
from seamus.harness.runner import get_runner_registry
from seamus.harness.steerable import (
    SteerableResponse,
    SteerableToolCall,
    agent_instance_id,
    daemon_instance_id,
    get_steerable_registry,
)


def _event_types(thread: Any) -> list[str]:
    """Return the AG-UI event types recorded on a thread.

    AG-UI event types are enum members; they are normalised to their plain
    string value so assertions read like the wire format.
    """
    types: list[str] = []
    for ev in thread.events:
        ev_type = getattr(ev, "type", None)
        if ev_type is None and isinstance(ev, dict):
            ev_type = ev.get("type")
        value = getattr(ev_type, "value", ev_type)
        types.append(str(value))
    return types


async def _drain(runner: Any, *, timeout: float = 30.0) -> None:
    """Wait for a runner's active turn to finish."""
    import asyncio

    task = runner._active_task
    if task is not None and not task.done():
        await asyncio.wait_for(asyncio.shield(task), timeout=timeout)


@pytest.mark.asyncio
async def test_agent_creation_yields_default_session_and_open_thread(
    client: httpx.AsyncClient,
) -> None:
    """REQ-009 / INV-009: creating an agent yields one unnamed session and one open thread."""
    res = await client.post("/api/v-alpha/agents", json={"name": "zero-prompt-agent"})
    assert res.status_code == 201
    agent = res.json()

    detail = (await client.get(f"/api/v-alpha/agent/{agent['id']}")).json()
    assert len(detail["sessions"]) == 1
    session = detail["sessions"][0]
    assert session["name"] is None

    session_detail = (
        await client.get(f"/api/v-alpha/agent/{agent['id']}/session/{session['id']}")
    ).json()
    assert len(session_detail["threads"]) == 1
    thread = session_detail["threads"][0]
    assert thread["is_open"] is True
    assert thread["name"] is None
    assert thread["status"] == AgentStatus.AWAITING_USER.value


@pytest.mark.asyncio
async def test_scripted_turn_emits_full_event_sequence(
    client: httpx.AsyncClient,
    make_session: Any,
    queue_agent_turn: Any,
    resolve_session: Any,
) -> None:
    """A scripted turn produces user text, reasoning, assistant text and a finished run."""
    ctx = make_session("scripted-turn")
    queue_agent_turn(
        ctx["session_id"],
        reasoning="The user asked a question.",
        text="Here is the answer.",
    )

    res = await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "What is the answer?"},
    )
    assert res.status_code == 202

    session = resolve_session(ctx["session_id"])
    runner = get_runner_registry().get_runner(session)
    await _drain(runner)

    thread = session.get_open_thread()
    assert thread is not None
    types = _event_types(thread)
    assert "TEXT_MESSAGE_START" in types
    assert "TEXT_MESSAGE_CONTENT" in types
    assert "TEXT_MESSAGE_END" in types
    assert any(t.startswith("REASONING") for t in types)
    assert "RUN_STARTED" in types
    assert "RUN_FINISHED" in types
    assert thread.status is AgentStatus.AWAITING_USER


@pytest.mark.asyncio
async def test_scripted_tool_call_executes_and_reports_result(
    client: httpx.AsyncClient,
    make_session: Any,
    queue_agent_turn: Any,
    resolve_session: Any,
    session_dir: Any,
) -> None:
    """A scripted tool call runs the real tool and produces a tool-call result event."""
    ctx = make_session("tool-call-session", mode="chat")
    queue_agent_turn(
        ctx["session_id"],
        tool_calls=[
            SteerableToolCall(
                name="write_file",
                args={"file_path": "/workspace/out.txt", "content": "hi"},
            )
        ],
    )
    queue_agent_turn(ctx["session_id"], text="Wrote the file.")

    res = await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "write a file"},
    )
    assert res.status_code == 202

    session = resolve_session(ctx["session_id"])
    runner = get_runner_registry().get_runner(session)
    await _drain(runner)

    dirs = session_dir(session)
    assert (dirs["data"] / "out.txt").read_text(encoding="utf-8") == "hi"

    thread = session.get_open_thread()
    types = _event_types(thread)
    assert "TOOL_CALL_START" in types
    assert "TOOL_CALL_RESULT" in types


@pytest.mark.asyncio
async def test_thread_stream_replays_history_after_turn(
    client: httpx.AsyncClient,
    make_session: Any,
    queue_agent_turn: Any,
    resolve_session: Any,
) -> None:
    """The thread stream replays the user message and the assistant answer."""
    ctx = make_session("replay-session", mode="chat")
    queue_agent_turn(ctx["session_id"], text="The replayed answer.")

    await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "The replayed question."},
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
    assert "The replayed question." in body
    assert "The replayed answer." in body
    assert "RUN_FINISHED" in body


@pytest.mark.asyncio
async def test_session_stream_replays_all_threads(
    client: httpx.AsyncClient,
    make_session: Any,
    queue_agent_turn: Any,
    resolve_session: Any,
) -> None:
    """The session stream concatenates events of every thread with delimiters."""
    ctx = make_session("session-stream", mode="chat")
    queue_agent_turn(ctx["session_id"], text="First answer.")
    await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "First question."},
    )

    session = resolve_session(ctx["session_id"])
    runner = get_runner_registry().get_runner(session)
    await _drain(runner)

    stream = await client.get(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/stream?follow=false"
    )
    assert stream.status_code == 200
    assert "THREAD_TRANSITION" in stream.text
    assert "First question." in stream.text
    assert "First answer." in stream.text


@pytest.mark.asyncio
async def test_agent_and_daemon_queues_are_independent(
    make_session: Any,
) -> None:
    """INV-062: steering the daemon never consumes the agent's queued turn."""
    ctx = make_session("independent-queues")
    registry = get_steerable_registry()
    agent_instance = registry.get_or_create(agent_instance_id(ctx["session_id"]), "agent")
    daemon_instance = registry.get_or_create(daemon_instance_id(ctx["session_id"]), "daemon")

    agent_instance.push(SteerableResponse(text="agent answer"))
    daemon_instance.push(SteerableResponse(text="daemon slug"))

    assert agent_instance.pending_count == 1
    assert daemon_instance.pending_count == 1
    assert agent_instance.responses[0].text == "agent answer"
    assert daemon_instance.responses[0].text == "daemon slug"


@pytest.mark.asyncio
async def test_repeated_scripted_scenarios_are_deterministic(
    client: httpx.AsyncClient,
    make_session: Any,
    queue_agent_turn: Any,
    resolve_session: Any,
) -> None:
    """Two identical scripted scenarios produce identical event type sequences."""
    sequences: list[list[str]] = []
    for index in range(2):
        ctx = make_session(f"deterministic-{index}", mode="chat")
        queue_agent_turn(ctx["session_id"], reasoning="thinking", text="answer")
        await client.post(
            f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
            json={"message": "question"},
        )

        session = resolve_session(ctx["session_id"])
        runner = get_runner_registry().get_runner(session)
        await _drain(runner)

        thread = session.get_open_thread()
        assert thread is not None
        sequences.append(_event_types(thread))

    assert sequences[0] == sequences[1]
