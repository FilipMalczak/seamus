"""End-to-end baseline for the interactive web terminal.

The terminal routes are the only part of the HTTP surface that talks to the
sandbox container directly rather than through the agent. This file drives
them end to end against the in-process sandbox stub, so the SSE framing, the
exit-code contract and the working-directory continuity are all observed
through the public API.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest


def _parse_events(body: str) -> list[dict[str, Any]]:
    """Parse the SSE payload of a terminal stream into event dictionaries."""
    events: list[dict[str, Any]] = []
    for chunk in body.strip().split("\n\n"):
        for line in chunk.splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[len("data: ") :]))
    return events


@pytest.mark.asyncio
async def test_terminal_info_reports_the_session_workspace(
    client: httpx.AsyncClient,
    make_session: Any,
) -> None:
    """The terminal info route reports the operational directory and status."""
    ctx = make_session("terminal-info")

    res = await client.get(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/terminal/info"
    )

    assert res.status_code == 200
    body = res.json()
    assert body["agent_id"] == ctx["agent_id"]
    assert body["session_id"] == ctx["session_id"]
    assert body["operational_dir"] == "/workspace"
    assert body["status"] == "ACTIVE"


@pytest.mark.asyncio
async def test_terminal_info_rejects_an_unknown_session(client: httpx.AsyncClient) -> None:
    """An unknown session identifier is a 404, not a 500."""
    res = await client.get(
        "/api/v-alpha/agent/00000000-0000-0000-0000-000000000000"
        "/session/00000000-0000-0000-0000-000000000000/terminal/info"
    )

    assert res.status_code == 404


@pytest.mark.asyncio
async def test_terminal_stream_runs_a_command_and_reports_the_exit_code(
    client: httpx.AsyncClient,
    make_session: Any,
) -> None:
    """A command is executed in the sandbox and its output is streamed back."""
    ctx = make_session("terminal-stream")

    res = await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/terminal/stream",
        json={"command": "echo hello-from-terminal", "working_directory": "/workspace"},
    )

    assert res.status_code == 200
    assert "text/event-stream" in res.headers["content-type"]

    events = _parse_events(res.text)
    stdout = [e for e in events if e["type"] == "stdout"]
    exits = [e for e in events if e["type"] == "exit"]

    assert any("hello-from-terminal" in e["data"] for e in stdout)
    assert len(exits) == 1
    assert exits[0]["exit_code"] == 0
    assert exits[0]["working_directory"] == "/workspace"


@pytest.mark.asyncio
async def test_terminal_stream_reports_a_failing_exit_code(
    client: httpx.AsyncClient,
    make_session: Any,
) -> None:
    """A failing command is reported with its non-zero exit code."""
    ctx = make_session("terminal-failure")

    res = await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/terminal/stream",
        json={"command": "exit 3", "working_directory": "/workspace"},
    )

    assert res.status_code == 200
    events = _parse_events(res.text)
    exits = [e for e in events if e["type"] == "exit"]
    assert len(exits) == 1
    assert exits[0]["exit_code"] == 3


@pytest.mark.asyncio
async def test_terminal_stream_of_an_empty_command_exits_cleanly(
    client: httpx.AsyncClient,
    make_session: Any,
) -> None:
    """An empty command is a no-op that still terminates the stream."""
    ctx = make_session("terminal-empty")

    res = await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/terminal/stream",
        json={"command": "   ", "working_directory": "/workspace"},
    )

    assert res.status_code == 200
    events = _parse_events(res.text)
    assert len(events) == 1
    assert events[0]["type"] == "exit"
    assert events[0]["exit_code"] == 0
    assert events[0]["working_directory"] == "/workspace"


@pytest.mark.asyncio
async def test_terminal_stream_reports_the_working_directory_after_a_cd(
    client: httpx.AsyncClient,
    make_session: Any,
) -> None:
    """The stream reports the directory the command ended up in."""
    ctx = make_session("terminal-cwd")

    res = await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/terminal/stream",
        json={"command": "cd /workspace && pwd", "working_directory": "/workspace"},
    )

    assert res.status_code == 200
    events = _parse_events(res.text)
    exits = [e for e in events if e["type"] == "exit"]
    assert len(exits) == 1
    assert exits[0]["exit_code"] == 0
    assert exits[0]["working_directory"] == "/workspace"
