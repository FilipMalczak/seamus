"""End-to-end tests for message pagination, bubble slicing, and stream replay controls."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from seamus.harness.runner import get_runner_registry
from seamus.harness.steerable import SteerableToolCall


async def _drain(runner: Any, *, timeout: float = 30.0) -> None:
    """Wait for runner's active turn to finish."""
    import asyncio

    task = runner._active_task
    if task is not None and not task.done():
        await asyncio.wait_for(asyncio.shield(task), timeout=timeout)


@pytest.mark.asyncio
async def test_e2e_conversation_pagination_and_stream_replay(
    client: httpx.AsyncClient,
    make_session: Any,
    queue_agent_turn: Any,
    resolve_session: Any,
) -> None:
    """Drive multi-turn conversation and verify paginated bubbles and replay toggle."""
    ctx = make_session("pagination-agent", mode="chat")
    agent_id = ctx["agent_id"]
    session_id = ctx["session_id"]

    session = resolve_session(session_id)
    runner = get_runner_registry().get_runner(session)

    # 1. Execute 3 multi-bubble assistant turns
    for i in range(3):
        # Turn with reasoning + tool call
        queue_agent_turn(
            session_id,
            reasoning=f"Reasoning for turn {i}",
            tool_calls=[
                SteerableToolCall(
                    name="write_file",
                    args={"file_path": f"/workspace/out-{i}.txt", "content": "hi"},
                )
            ],
            text=f"Tool output explanation {i}",
        )
        # Follow-up final text
        queue_agent_turn(
            session_id,
            text=f"Final answer for turn {i}",
        )

        input_res = await client.post(
            f"/api/v-alpha/agent/{agent_id}/session/{session_id}/input",
            json={"message": f"User prompt {i}"},
        )
        assert input_res.status_code == 202
        await _drain(runner)

    # 2. Verify total visual bubbles via paginated endpoint
    res_all = await client.get(
        f"/api/v-alpha/agent/{agent_id}/session/{session_id}/messages?limit=100"
    )
    assert res_all.status_code == 200
    all_data = res_all.json()
    total_bubbles = all_data["total_bubbles"]
    assert total_bubbles >= 9  # Multiple bubbles per turn

    # 3. Tail pagination: request limit 4 bubbles
    res_tail = await client.get(
        f"/api/v-alpha/agent/{agent_id}/session/{session_id}/messages?limit=4&tail=true"
    )
    assert res_tail.status_code == 200
    tail_data = res_tail.json()
    assert tail_data["total_bubbles"] == total_bubbles
    assert tail_data["has_more_before"] is True
    assert tail_data["has_more_after"] is False
    assert tail_data["newest_bubble_id"] == all_data["newest_bubble_id"]

    # 4. Backward pagination: fetch 4 bubbles before the oldest in tail
    before_id = tail_data["oldest_bubble_id"]
    res_before = await client.get(
        f"/api/v-alpha/agent/{agent_id}/session/{session_id}/messages?before_id={before_id}&limit=4"
    )
    assert res_before.status_code == 200
    before_data = res_before.json()
    assert before_data["has_more_after"] is True

    # 5. Verify SSE stream replay toggle
    # With replay=false: no past events are emitted
    res_stream_no_replay = await client.get(
        f"/api/v-alpha/agent/{agent_id}/session/{session_id}/stream?follow=false&replay=false",
        headers={"Accept": "text/event-stream"},
    )
    assert res_stream_no_replay.status_code == 200
    assert res_stream_no_replay.text.strip() == ""

    # With replay=true: replays past events
    res_stream_replay = await client.get(
        f"/api/v-alpha/agent/{agent_id}/session/{session_id}/stream?follow=false&replay=true",
        headers={"Accept": "text/event-stream"},
    )
    assert res_stream_replay.status_code == 200
    assert "User prompt 0" in res_stream_replay.text
