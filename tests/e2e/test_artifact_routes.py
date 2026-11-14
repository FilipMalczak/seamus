"""End-to-end baseline for the A2UI artifact routes.

The artifact routes are how the web UI discovers, renders, and interacts with
the artifacts an agent produces. This file drives them through the real ASGI
application: a scripted model turn creates a real questionnaire artifact on
disk, and the tests then exercise listing, fetching, clicking, and submitting
against it.

The only substitution is the inference provider (the ``steerable`` scripted
provider) and the container (the in-process stub sandbox).
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest

from seamus.harness.runner import get_runner_registry
from seamus.harness.steerable import SteerableToolCall


async def _drain(runner: Any, *, timeout: float = 30.0) -> None:
    """Wait for a runner's active turn to finish."""
    task = runner._active_task
    if task is not None and not task.done():
        await asyncio.wait_for(asyncio.shield(task), timeout=timeout)


def _artifact_url(ctx: dict[str, Any], suffix: str = "") -> str:
    """Return the artifact collection URL for a session."""
    base = f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/artifact"
    return f"{base}{suffix}"


async def _make_questionnaire(
    client: httpx.AsyncClient,
    ctx: dict[str, Any],
    queue_agent_turn: Any,
    resolve_session: Any,
    *,
    title: str = "Pick one",
    blocking: bool = False,
) -> str:
    """Run a scripted turn that creates a questionnaire, and return its UUID."""
    queue_agent_turn(
        ctx["session_id"],
        tool_calls=[
            SteerableToolCall(
                name="make_questionnaire",
                args={
                    "title": title,
                    "questions": [{"body": "Which one?", "answers": ["Alpha", "Beta"]}],
                    "blocking": blocking,
                },
            )
        ],
    )
    queue_agent_turn(ctx["session_id"], text="Questionnaire created.")

    await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "Ask me something."},
    )

    session = resolve_session(ctx["session_id"])
    runner = get_runner_registry().get_runner(session)
    await _drain(runner)

    listed = (await client.get(_artifact_url(ctx))).json()
    assert listed, "expected the scripted turn to create an artifact"
    return str(listed[0]["uuid"])


@pytest.mark.asyncio
async def test_artifact_list_is_empty_for_a_fresh_session(
    client: httpx.AsyncClient,
    make_session: Any,
) -> None:
    """A session with no artifacts lists none."""
    ctx = make_session("artifact-empty")

    res = await client.get(_artifact_url(ctx))

    assert res.status_code == 200
    assert res.json() == []


@pytest.mark.asyncio
async def test_artifact_list_reports_the_created_artifact(
    client: httpx.AsyncClient,
    make_session: Any,
    queue_agent_turn: Any,
    resolve_session: Any,
) -> None:
    """A scripted questionnaire turn makes the artifact discoverable."""
    ctx = make_session("artifact-list")
    uuid = await _make_questionnaire(client, ctx, queue_agent_turn, resolve_session)

    res = await client.get(_artifact_url(ctx))

    assert res.status_code == 200
    artifacts = res.json()
    assert len(artifacts) == 1
    assert artifacts[0]["uuid"] == uuid
    assert artifacts[0]["family"] == "questionnaires"
    assert artifacts[0]["title"] == "Pick one"
    assert artifacts[0]["is_closed"] is False


@pytest.mark.asyncio
async def test_artifact_detail_returns_manifest_body_and_state(
    client: httpx.AsyncClient,
    make_session: Any,
    queue_agent_turn: Any,
    resolve_session: Any,
) -> None:
    """The detail route returns the manifest, the component body, and the state."""
    ctx = make_session("artifact-detail")
    uuid = await _make_questionnaire(client, ctx, queue_agent_turn, resolve_session)

    res = await client.get(_artifact_url(ctx, f"/questionnaires/{uuid}"))

    assert res.status_code == 200
    body = res.json()
    assert body["uuid"] == uuid
    assert body["manifest"]["name"] == "Pick one"
    assert body["manifest"]["blocking"] is False
    assert body["body"], "expected the artifact body to carry components"
    # The state carries the remaining click budget per declared button.
    assert body["state"]["clicksLeft"]["submit_btn"] == "*"


@pytest.mark.asyncio
async def test_artifact_detail_rejects_an_unknown_artifact(
    client: httpx.AsyncClient,
    make_session: Any,
) -> None:
    """Fetching an unknown artifact is a 404."""
    ctx = make_session("artifact-missing")

    res = await client.get(_artifact_url(ctx, "/questionnaires/does-not-exist"))

    assert res.status_code == 404


@pytest.mark.asyncio
async def test_artifact_click_dispatches_and_records_the_interaction(
    client: httpx.AsyncClient,
    make_session: Any,
    queue_agent_turn: Any,
    resolve_session: Any,
) -> None:
    """A click is dispatched to the artifact and recorded on the thread."""
    ctx = make_session("artifact-click")
    uuid = await _make_questionnaire(client, ctx, queue_agent_turn, resolve_session)

    res = await client.post(
        _artifact_url(ctx, f"/questionnaires/{uuid}/click"),
        json={"button_id": "submit_btn", "event": "submit"},
    )

    assert res.status_code == 200
    result = res.json()
    assert result["artifact_id"] == uuid
    assert result["button_id"] == "submit_btn"
    assert result["event"] == "submit"

    session = resolve_session(ctx["session_id"])
    thread = session.get_open_thread()
    assert thread is not None
    interactions = [
        ev
        for ev in thread.events
        if (ev.get("type") if isinstance(ev, dict) else None) == "ARTIFACT_INTERACTION"
    ]
    assert len(interactions) == 1
    assert interactions[0]["uuid"] == uuid
    assert interactions[0]["button_id"] == "submit_btn"


@pytest.mark.asyncio
async def test_artifact_click_resolves_the_family_from_the_uuid(
    client: httpx.AsyncClient,
    make_session: Any,
    queue_agent_turn: Any,
    resolve_session: Any,
) -> None:
    """The UUID-only click route resolves the artifact family automatically."""
    ctx = make_session("artifact-click-uuid")
    uuid = await _make_questionnaire(client, ctx, queue_agent_turn, resolve_session)

    res = await client.post(
        _artifact_url(ctx, f"/{uuid}/click"),
        json={"button_id": "submit_btn"},
    )

    assert res.status_code == 200
    assert res.json()["artifact_id"] == uuid


@pytest.mark.asyncio
async def test_artifact_click_rejects_an_unknown_uuid(
    client: httpx.AsyncClient,
    make_session: Any,
) -> None:
    """Clicking an unknown artifact UUID is a 404."""
    ctx = make_session("artifact-click-missing")

    res = await client.post(
        _artifact_url(ctx, "/does-not-exist/click"),
        json={"button_id": "submit_btn"},
    )

    assert res.status_code == 404


@pytest.mark.asyncio
async def test_artifact_click_rejects_an_unknown_button(
    client: httpx.AsyncClient,
    make_session: Any,
    queue_agent_turn: Any,
    resolve_session: Any,
) -> None:
    """Clicking a button the artifact does not declare is a 400."""
    ctx = make_session("artifact-click-bad-button")
    uuid = await _make_questionnaire(client, ctx, queue_agent_turn, resolve_session)

    res = await client.post(
        _artifact_url(ctx, f"/questionnaires/{uuid}/click"),
        json={"button_id": "not_a_button"},
    )

    assert res.status_code == 400


@pytest.mark.asyncio
async def test_artifact_submit_is_accepted(
    client: httpx.AsyncClient,
    make_session: Any,
    queue_agent_turn: Any,
    resolve_session: Any,
) -> None:
    """Submitting artifact data is accepted and returns a tool-call identifier."""
    ctx = make_session("artifact-submit")
    uuid = await _make_questionnaire(client, ctx, queue_agent_turn, resolve_session)

    res = await client.post(
        _artifact_url(ctx, f"/questionnaires/{uuid}/submit"),
        json={"data": {"q1": "Alpha"}},
    )

    assert res.status_code == 202
    body = res.json()
    assert body["status"] == "accepted"
    assert body["artifact_id"] == uuid
    assert body["kind"] == "questionnaires"
    assert body["session_id"] == ctx["session_id"]
    assert body["tool_call_id"]


@pytest.mark.asyncio
async def test_artifact_routes_reject_an_unknown_session(
    client: httpx.AsyncClient,
    make_session: Any,
) -> None:
    """The artifact routes are a 404 for an unknown session."""
    ctx = make_session("artifact-unknown-session")
    url = f"/api/v-alpha/agent/{ctx['agent_id']}/session/does-not-exist/artifact"

    res = await client.get(url)

    assert res.status_code == 404
