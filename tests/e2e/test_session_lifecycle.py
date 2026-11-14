"""End-to-end tests for session lifecycle, branching and mode switching.

These scenarios exercise the public HTTP API against a real session driven by
scripted model responses: terminal-state teardown, granular branching with
provenance, and operational-mode switching.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest

from seamus.domain.entities import AgentStatus
from seamus.harness.runner import get_runner_registry
from seamus.harness.steerable import SteerableToolCall


async def _drain(runner: Any, *, timeout: float = 30.0) -> None:
    """Wait for a runner's active turn to finish."""
    task = runner._active_task
    if task is not None and not task.done():
        await asyncio.wait_for(asyncio.shield(task), timeout=timeout)


async def _wait_for_status(session: Any, status: AgentStatus, *, timeout: float = 30.0) -> Any:
    """Poll the open thread until it reaches ``status``."""
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        thread = session.get_open_thread()
        if thread is not None and thread.status is status:
            return thread
        await asyncio.sleep(0.1)
    raise AssertionError(f"Thread did not reach status {status!r} within {timeout}s")


def _event_types(thread: Any) -> list[str]:
    """Return the normalised AG-UI event types recorded on a thread."""
    types: list[str] = []
    for ev in thread.events:
        ev_type = getattr(ev, "type", None)
        if ev_type is None and isinstance(ev, dict):
            ev_type = ev.get("type")
        types.append(str(getattr(ev_type, "value", ev_type)))
    return types


@pytest.mark.asyncio
async def test_killed_session_rejects_further_input(
    client: httpx.AsyncClient,
    make_session: Any,
    queue_agent_turn: Any,
    resolve_session: Any,
    stub_sandbox: list[Any],
) -> None:
    """INV-029: a killed session rejects further input and tears down its sandbox."""
    ctx = make_session("kill-session", mode="chat")
    queue_agent_turn(ctx["session_id"], text="First answer.")

    await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "hello"},
    )
    session = resolve_session(ctx["session_id"])
    runner = get_runner_registry().get_runner(session)
    await _drain(runner)

    killed = await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/kill"
    )
    assert killed.status_code == 200
    assert killed.json()["status"] == "KILLED"

    # The sandbox backing the session has been destroyed.
    assert stub_sandbox
    assert stub_sandbox[-1].destroyed is True

    # Further input is refused with 409 Conflict.
    rejected = await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "are you there?"},
    )
    assert rejected.status_code == 409


@pytest.mark.asyncio
async def test_killed_session_cannot_switch_mode(
    client: httpx.AsyncClient,
    make_session: Any,
    resolve_session: Any,
) -> None:
    """INV-029: a terminal session blocks thread creation via mode switching."""
    ctx = make_session("kill-mode-switch", mode="chat")
    await client.post(f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/kill")

    switched = await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/mode",
        json={"mode": "plan"},
    )
    assert switched.status_code == 400


@pytest.mark.asyncio
async def test_branch_after_user_message_creates_child_session(
    client: httpx.AsyncClient,
    make_session: Any,
    queue_agent_turn: Any,
    resolve_session: Any,
) -> None:
    """INV-030: branching after a user message yields a child session with provenance."""
    ctx = make_session("branch-parent", mode="chat")
    queue_agent_turn(ctx["session_id"], text="Parent answer.")

    posted = await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "the question"},
    )
    assert posted.status_code == 202
    message_id = posted.json()["message_id"]

    session = resolve_session(ctx["session_id"])
    runner = get_runner_registry().get_runner(session)
    await _drain(runner)

    branched = await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/branch",
        json={
            "target_id": message_id,
            "position": "after",
            "item_type": "user_message",
            "name": "branch-child",
        },
    )
    assert branched.status_code == 201
    child = branched.json()

    assert child["name"] == "branch-child"
    assert child["provenance"] is not None
    assert child["provenance"]["parent_session_id"] == ctx["session_id"]
    assert child["provenance"]["parent_message_id"] == message_id
    assert child["provenance"]["branch_position"] == "after"
    assert child["provenance"]["item_type"] == "user_message"
    assert len(child["lineage"]) == 1

    # The parent session is untouched.
    parent = resolve_session(ctx["session_id"])
    assert parent.provenance is None
    assert parent.lineage == []


@pytest.mark.asyncio
async def test_branch_before_user_message_preserves_parent_history(
    client: httpx.AsyncClient,
    make_session: Any,
    queue_agent_turn: Any,
    resolve_session: Any,
) -> None:
    """INV-030: branching before a user message slices history and keeps the parent intact."""
    ctx = make_session("branch-before", mode="chat")
    queue_agent_turn(ctx["session_id"], text="First answer.")

    first = await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "first question"},
    )
    first_message_id = first.json()["message_id"]

    session = resolve_session(ctx["session_id"])
    runner = get_runner_registry().get_runner(session)
    await _drain(runner)

    queue_agent_turn(ctx["session_id"], text="Second answer.")
    second = await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "second question"},
    )
    second_message_id = second.json()["message_id"]
    await _drain(runner)

    # The two turns are distinct messages, so branching before the second one
    # cannot accidentally target the first.
    assert first_message_id != second_message_id

    branched = await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/branch",
        json={
            "target_id": second_message_id,
            "position": "before",
            "item_type": "user_message",
            "name": "branch-before-child",
        },
    )
    assert branched.status_code == 201
    child = branched.json()
    assert child["provenance"]["branch_position"] == "before"
    assert child["provenance"]["parent_message_id"] == second_message_id

    # The parent still holds both turns.
    parent = resolve_session(ctx["session_id"])
    parent_thread = parent.get_open_thread()
    assert parent_thread is not None
    types = _event_types(parent_thread)
    assert types.count("TEXT_MESSAGE_START") >= 4


@pytest.mark.asyncio
async def test_multi_level_branching_keeps_lineage_chain(
    client: httpx.AsyncClient,
    make_session: Any,
    queue_agent_turn: Any,
    resolve_session: Any,
) -> None:
    """INV-030: a second-generation branch records the full ancestor chain."""
    ctx = make_session("lineage-root", mode="chat")
    queue_agent_turn(ctx["session_id"], text="Root answer.")

    posted = await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "root question"},
    )
    root_message_id = posted.json()["message_id"]

    session = resolve_session(ctx["session_id"])
    runner = get_runner_registry().get_runner(session)
    await _drain(runner)

    first_branch = await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/branch",
        json={
            "target_id": root_message_id,
            "position": "after",
            "item_type": "user_message",
            "name": "lineage-child",
        },
    )
    assert first_branch.status_code == 201
    child_id = first_branch.json()["id"]

    # Branching "after" a user message auto-resumes inference in the child
    # session, so the child turn is already in flight.
    queue_agent_turn(child_id, text="Child answer.")
    child_session = resolve_session(child_id)
    child_runner = get_runner_registry().get_runner(child_session)
    await _wait_for_status(child_session, AgentStatus.AWAITING_USER)

    queue_agent_turn(child_id, text="Child answer 2.")
    child_posted = await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{child_id}/input",
        json={"message": "child question"},
    )
    assert child_posted.status_code == 202
    child_message_id = child_posted.json()["message_id"]
    await _drain(child_runner)

    second_branch = await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{child_id}/branch",
        json={
            "target_id": child_message_id,
            "position": "after",
            "item_type": "user_message",
            "name": "lineage-grandchild",
        },
    )
    assert second_branch.status_code == 201
    grandchild = second_branch.json()

    assert grandchild["provenance"]["parent_session_id"] == child_id
    assert len(grandchild["lineage"]) == 2
    ancestor_ids = {entry["parent_session_id"] for entry in grandchild["lineage"]}
    assert ctx["session_id"] in ancestor_ids
    assert child_id in ancestor_ids


@pytest.mark.asyncio
async def test_branch_preserves_mode_and_phase(
    client: httpx.AsyncClient,
    make_session: Any,
    queue_agent_turn: Any,
    resolve_session: Any,
) -> None:
    """INV-030: a branched session keeps the parent's operational mode and phase."""
    ctx = make_session("branch-mode", mode="plan", phase="make")
    queue_agent_turn(ctx["session_id"], text="Plan answer.")

    posted = await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "plan question"},
    )
    message_id = posted.json()["message_id"]

    session = resolve_session(ctx["session_id"])
    runner = get_runner_registry().get_runner(session)
    await _drain(runner)

    branched = await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/branch",
        json={
            "target_id": message_id,
            "position": "after",
            "item_type": "user_message",
            "name": "branch-mode-child",
        },
    )
    assert branched.status_code == 201
    child = branched.json()

    open_threads = [t for t in child["threads"] if t["is_open"]]
    assert len(open_threads) == 1
    assert open_threads[0]["mode"] == "plan"
    assert open_threads[0]["phase"] == "make"


@pytest.mark.asyncio
async def test_mode_switch_spawns_new_thread_and_closes_plan(
    client: httpx.AsyncClient,
    make_session: Any,
    queue_agent_turn: Any,
    resolve_session: Any,
    session_dir: Any,
) -> None:
    """INV-028: switching mode closes the active plan and spawns a fresh thread."""
    ctx = make_session("mode-switch", mode="plan", phase="make")
    queue_agent_turn(
        ctx["session_id"],
        tool_calls=[
            SteerableToolCall(
                name="make_plan",
                args={"title": "Plan", "content": "# Plan"},
            )
        ],
    )
    queue_agent_turn(ctx["session_id"], text="Plan ready.")

    await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "draft the plan"},
    )

    session = resolve_session(ctx["session_id"])
    runner = get_runner_registry().get_runner(session)
    await _drain(runner)

    plan_id = session.active_plan_id
    assert plan_id is not None

    switched = await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/mode",
        json={"mode": "chat"},
    )
    assert switched.status_code == 200
    body = switched.json()

    assert body["config"]["mode"] == "chat"
    assert body["active_plan_id"] is None

    open_threads = [t for t in body["threads"] if t["is_open"]]
    assert len(open_threads) == 1
    assert open_threads[0]["mode"] == "chat"
    assert str(open_threads[0]["id"]) != ctx["thread_id"]

    # The plan artifact is closed on disk.
    dirs = session_dir(session)
    plan_dir = dirs["artifacts"] / "plans" / str(plan_id)
    assert (plan_dir / "closed.marker").is_file()


@pytest.mark.asyncio
async def test_mode_switch_closes_open_blocking_questionnaire(
    client: httpx.AsyncClient,
    make_session: Any,
    queue_agent_turn: Any,
    resolve_session: Any,
) -> None:
    """INV-040: switching mode unblocks the session by closing open artifacts."""
    ctx = make_session("mode-switch-blocking", mode="chat")
    queue_agent_turn(
        ctx["session_id"],
        tool_calls=[
            SteerableToolCall(
                name="make_questionnaire",
                args={
                    "title": "Pick",
                    "questions": [{"body": "Which?", "answers": ["A", "B"]}],
                    "blocking": True,
                },
            )
        ],
    )
    queue_agent_turn(ctx["session_id"], text="Waiting.")

    await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "ask me"},
    )

    session = resolve_session(ctx["session_id"])
    runner = get_runner_registry().get_runner(session)
    await _drain(runner)

    blocked = await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "text"},
    )
    assert blocked.status_code == 409

    switched = await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/mode",
        json={"mode": "plan"},
    )
    assert switched.status_code == 200

    # After the switch the session accepts input again.
    queue_agent_turn(ctx["session_id"], text="New mode answer.")
    accepted = await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "now we can talk"},
    )
    assert accepted.status_code == 202


@pytest.mark.asyncio
async def test_thread_acceptance_closes_thread_and_spawns_successor(
    client: httpx.AsyncClient,
    make_session: Any,
    queue_agent_turn: Any,
    resolve_session: Any,
) -> None:
    """INV-022: accepting a thread closes it and spawns a successor thread."""
    ctx = make_session("accept-thread", mode="chat")
    queue_agent_turn(ctx["session_id"], text="Done.")

    await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "work"},
    )

    session = resolve_session(ctx["session_id"])
    runner = get_runner_registry().get_runner(session)
    await _drain(runner)

    accepted = await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}"
        f"/thread/{ctx['thread_id']}/accept"
    )
    assert accepted.status_code == 200
    new_thread = accepted.json()
    assert new_thread["is_open"] is True
    assert str(new_thread["id"]) != ctx["thread_id"]

    session = resolve_session(ctx["session_id"])
    open_threads = [t for t in session.threads.values() if t.is_open]
    assert len(open_threads) == 1
    assert str(open_threads[0].id) == str(new_thread["id"])
    assert open_threads[0].status is AgentStatus.AWAITING_USER
