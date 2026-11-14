"""End-to-end tests for the Plan-mode lifecycle and blocking artifacts.

The scenarios drive a real session through ``discuss -> make -> execute`` using
scripted model responses, and verify the mount policy, the plan artifact on
disk, the Proceed transition and the blocking-questionnaire handshake.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import pytest

from seamus.domain.entities import AgentStatus
from seamus.domain.modes import PlanPhase
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
async def test_discuss_to_make_transition_creates_new_thread(
    client: httpx.AsyncClient,
    make_session: Any,
    queue_agent_turn: Any,
    resolve_session: Any,
) -> None:
    """INV-028: calling ``plan`` moves the session to Make in a fresh thread."""
    ctx = make_session("plan-transition", mode="plan", phase=PlanPhase.DISCUSS.value)
    queue_agent_turn(
        ctx["session_id"],
        tool_calls=[SteerableToolCall(name="plan", args={})],
    )
    queue_agent_turn(ctx["session_id"], text="Notes recorded.")

    await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "I have finished exploring."},
    )

    session = resolve_session(ctx["session_id"])
    runner = get_runner_registry().get_runner(session)
    await _drain(runner)

    open_thread = session.get_open_thread()
    assert open_thread is not None
    assert open_thread.mode == "plan"
    assert open_thread.phase == PlanPhase.MAKE.value
    assert str(open_thread.id) != ctx["thread_id"]

    # The previous thread is closed: exactly one thread remains open.
    open_threads = [t for t in session.threads.values() if t.is_open]
    assert len(open_threads) == 1


@pytest.mark.asyncio
async def test_make_plan_creates_plan_artifact_on_disk(
    client: httpx.AsyncClient,
    make_session: Any,
    queue_agent_turn: Any,
    resolve_session: Any,
    session_dir: Any,
) -> None:
    """REQ-034: ``make_plan`` persists a plan artifact with canonical ``plan.md``."""
    ctx = make_session("plan-artifact", mode="plan", phase=PlanPhase.MAKE.value)
    queue_agent_turn(
        ctx["session_id"],
        tool_calls=[
            SteerableToolCall(
                name="make_plan",
                args={"title": "My Plan", "content": "# Step 1\n\nDo the thing."},
            )
        ],
    )
    queue_agent_turn(ctx["session_id"], text="Plan created.")

    await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "Write the plan."},
    )

    session = resolve_session(ctx["session_id"])
    runner = get_runner_registry().get_runner(session)
    await _drain(runner)

    assert session.active_plan_id is not None
    dirs = session_dir(session)
    plan_dir = dirs["artifacts"] / "plans" / str(session.active_plan_id)
    assert (plan_dir / "manifest.json").is_file()
    assert (plan_dir / "body.json").is_file()
    assert (plan_dir / "plan.md").is_file()
    assert "Do the thing." in (plan_dir / "plan.md").read_text(encoding="utf-8")

    # The artifact is announced to the client.
    thread = session.get_open_thread()
    assert thread is not None
    assert "ARTIFACT_CREATED" in _event_types(thread)


@pytest.mark.asyncio
async def test_workspace_is_read_only_during_make_phase(
    client: httpx.AsyncClient,
    make_session: Any,
    queue_agent_turn: Any,
    resolve_session: Any,
    stub_sandbox: list[Any],
) -> None:
    """INV-041: the workspace mount is read-only while the plan is authored."""
    ctx = make_session("make-readonly", mode="plan", phase=PlanPhase.MAKE.value)
    queue_agent_turn(
        ctx["session_id"],
        tool_calls=[
            SteerableToolCall(
                name="write_file",
                args={"file_path": "/workspace/should-not-exist.txt", "content": "nope"},
            )
        ],
    )
    queue_agent_turn(ctx["session_id"], text="The write was refused.")

    await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "Try to write a file."},
    )

    session = resolve_session(ctx["session_id"])
    runner = get_runner_registry().get_runner(session)
    await _drain(runner)

    # The sandbox serving this session has the workspace mounted read-only.
    assert stub_sandbox
    assert stub_sandbox[-1].workspace_readonly is True

    thread = session.get_open_thread()
    assert thread is not None
    results = [
        str(getattr(ev, "content", "") or (ev.get("content") if isinstance(ev, dict) else ""))
        for ev in thread.events
    ]
    assert any("read-only" in content for content in results)


@pytest.mark.asyncio
async def test_proceed_advances_to_execute_phase(
    client: httpx.AsyncClient,
    make_session: Any,
    queue_agent_turn: Any,
    resolve_session: Any,
    session_dir: Any,
) -> None:
    """REQ-034: clicking Proceed moves the session from Make to Execute."""
    ctx = make_session("plan-proceed", mode="plan", phase=PlanPhase.MAKE.value)
    queue_agent_turn(
        ctx["session_id"],
        tool_calls=[
            SteerableToolCall(
                name="make_plan",
                args={"title": "Approved Plan", "content": "# Approved"},
            )
        ],
    )
    queue_agent_turn(ctx["session_id"], text="Plan ready for review.")

    await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "Draft the plan."},
    )

    session = resolve_session(ctx["session_id"])
    runner = get_runner_registry().get_runner(session)
    await _drain(runner)

    plan_id = session.active_plan_id
    assert plan_id is not None

    queue_agent_turn(ctx["session_id"], text="Implementing the approved plan.")
    click = await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}"
        f"/artifact/plans/{plan_id}/click",
        json={"button_id": "proceed_btn"},
    )
    assert click.status_code == 200

    await _drain(runner)

    open_thread = session.get_open_thread()
    assert open_thread is not None
    assert open_thread.phase == PlanPhase.EXECUTE.value
    assert session.active_plan_id == plan_id

    dirs = session_dir(session)
    assert (dirs["artifacts"] / "plans" / str(plan_id) / "plan.md").is_file()


@pytest.mark.asyncio
async def test_blocking_questionnaire_blocks_text_input_until_click(
    client: httpx.AsyncClient,
    make_session: Any,
    queue_agent_turn: Any,
    resolve_session: Any,
    session_dir: Any,
) -> None:
    """INV-040: an open blocking artifact rejects ordinary text input."""
    ctx = make_session("blocking-questionnaire", mode="chat")
    queue_agent_turn(
        ctx["session_id"],
        tool_calls=[
            SteerableToolCall(
                name="make_questionnaire",
                args={
                    "title": "Pick one",
                    "questions": [
                        {"body": "Which one?", "answers": ["Alpha", "Beta"]},
                    ],
                    "blocking": True,
                },
            )
        ],
    )
    queue_agent_turn(ctx["session_id"], text="Waiting for your answer.")

    await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "Ask me something."},
    )

    session = resolve_session(ctx["session_id"])
    runner = get_runner_registry().get_runner(session)
    await _drain(runner)

    # The questionnaire exists and is listed for the session.
    listed = await client.get(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/artifact"
    )
    assert listed.status_code == 200
    families = {entry["family"] for entry in listed.json()}
    assert "questionnaires" in families

    # Ordinary text input is refused while the blocking artifact is open.
    blocked = await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "just text"},
    )
    assert blocked.status_code == 409
    assert "blocking artifact" in blocked.json()["detail"]


@pytest.mark.asyncio
async def test_questionnaire_click_records_answers_and_resumes(
    client: httpx.AsyncClient,
    make_session: Any,
    queue_agent_turn: Any,
    resolve_session: Any,
    session_dir: Any,
) -> None:
    """A questionnaire click is recorded and summarised into ``answers.md``."""
    ctx = make_session("questionnaire-click", mode="chat")
    queue_agent_turn(
        ctx["session_id"],
        tool_calls=[
            SteerableToolCall(
                name="make_questionnaire",
                args={
                    "title": "Pick one",
                    "questions": [
                        {"body": "Which one?", "answers": ["Alpha", "Beta"]},
                    ],
                    "blocking": True,
                },
            )
        ],
    )
    queue_agent_turn(ctx["session_id"], text="Waiting for your answer.")

    await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "Ask me something."},
    )

    session = resolve_session(ctx["session_id"])
    runner = get_runner_registry().get_runner(session)
    await _drain(runner)

    listed = (
        await client.get(
            f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/artifact"
        )
    ).json()
    questionnaire = next(e for e in listed if e["family"] == "questionnaires")
    uuid = questionnaire["uuid"]

    click = await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}"
        f"/artifact/questionnaires/{uuid}/click",
        json={"button_id": "submit_btn", "data": {"Which one?": "Alpha"}},
    )
    assert click.status_code == 200

    dirs = session_dir(session)
    answers = dirs["artifacts"] / "questionnaires" / uuid / "answers.md"
    assert answers.is_file()
    assert "Alpha" in answers.read_text(encoding="utf-8")

    # The interaction is appended to the thread history.
    thread = session.get_open_thread()
    assert thread is not None
    assert "ARTIFACT_INTERACTION" in _event_types(thread)


@pytest.mark.asyncio
async def test_wait_for_click_suspends_turn_until_artifact_click(
    client: httpx.AsyncClient,
    make_session: Any,
    queue_agent_turn: Any,
    resolve_session: Any,
    session_dir: Any,
) -> None:
    """``wait_for_click`` suspends the turn; a click resumes it."""
    ctx = make_session("wait-for-click", mode="chat")
    queue_agent_turn(
        ctx["session_id"],
        tool_calls=[
            SteerableToolCall(
                name="make_questionnaire",
                args={
                    "title": "Confirm",
                    "questions": [
                        {"body": "Continue?", "answers": ["Yes", "No"]},
                    ],
                    "blocking": False,
                },
            )
        ],
    )
    queue_agent_turn(ctx["session_id"], text="Questionnaire ready.")
    await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "Create the questionnaire."},
    )

    session = resolve_session(ctx["session_id"])
    runner = get_runner_registry().get_runner(session)
    await _drain(runner)

    listed = (
        await client.get(
            f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/artifact"
        )
    ).json()
    questionnaire = next(e for e in listed if e["family"] == "questionnaires")
    uuid = questionnaire["uuid"]

    queue_agent_turn(
        ctx["session_id"],
        tool_calls=[
            SteerableToolCall(name="wait_for_click", args={"artifact_id": uuid}),
        ],
    )
    queue_agent_turn(ctx["session_id"], text="Thanks for the answer.")

    await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "Now wait for the click."},
    )

    # The turn is suspended: the thread waits for the user and the
    # restart-safe pending-wait marker has been written.
    thread = await _wait_for_status(session, AgentStatus.AWAITING_USER)
    assert runner._active_task is not None
    assert not runner._active_task.done()

    dirs = session_dir(session)
    pending_wait = (
        dirs["workspace"] / "agent" / "state" / "threads" / str(thread.id) / "pending_wait.json"
    )
    assert pending_wait.is_file()
    assert json.loads(pending_wait.read_text(encoding="utf-8"))["artifact_id"] == uuid

    click = await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}"
        f"/artifact/questionnaires/{uuid}/click",
        json={"button_id": "submit_btn", "data": {"Continue?": "Yes"}},
    )
    assert click.status_code == 200

    await _drain(runner)
    assert runner._active_task is None or runner._active_task.done()
