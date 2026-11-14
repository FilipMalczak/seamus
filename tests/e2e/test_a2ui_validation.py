"""End-to-end tests for the A2UI artifact authoring surface.

An agent authors an artifact by calling the `make_artifact` tool. The
harness *loosely normalizes* the surface and then *strictly validates* it,
so a malformed artifact never reaches the workspace. These tests drive the
tool through a scripted turn and assert on the tool result and on the
filesystem:

* REQ-046 / INV-057 — a component identifier that is not a valid UAX #31
  identifier is normalized, and the repair is reported to the model;
* REQ-046 — a surface with an unknown component type, a dangling child
  reference or an empty component list is rejected, and nothing is written;
* REQ-033 / INV-040 — a valid artifact is written atomically, with its
  manifest, body and state, and is reachable through the artifact route.
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


def _event_type(event: Any) -> str:
    """Return the normalised event type of a thread event."""
    ev_type = getattr(event, "type", None)
    if ev_type is None and isinstance(event, dict):
        ev_type = event.get("type")
    return str(getattr(ev_type, "value", ev_type))


def _tool_results(thread: Any) -> list[str]:
    """Return the textual results of the tool calls recorded on a thread."""
    results: list[str] = []
    for event in thread.events:
        if _event_type(event) != "TOOL_CALL_RESULT":
            continue
        content = getattr(event, "content", None)
        if content is None and isinstance(event, dict):
            content = event.get("content")
        results.append(str(content or ""))
    return results


async def _make_artifact(
    client: httpx.AsyncClient,
    ctx: dict[str, Any],
    queue_agent_turn: Any,
    resolve_session: Any,
    components: list[dict[str, Any]],
    *,
    manifest: dict[str, Any] | None = None,
) -> Any:
    """Run one scripted turn that calls `make_artifact`, and return the session."""
    queue_agent_turn(
        ctx["session_id"],
        tool_calls=[
            SteerableToolCall(
                name="make_artifact",
                args={
                    "family": "custom",
                    "manifest": manifest
                    or {
                        "name": "Demo",
                        "exposition": "embedded",
                        "blocking": False,
                        "commentable": False,
                        "buttons": [],
                    },
                    "components": components,
                },
            )
        ],
    )
    queue_agent_turn(ctx["session_id"], text="Done.")

    await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "make the artifact"},
    )

    session = resolve_session(ctx["session_id"])
    runner = get_runner_registry().get_runner(session)
    await _drain(runner)
    return session


def _stored_artifacts(session_dir: Any, ctx: dict[str, Any]) -> list[Any]:
    """Return the manifests of the artifacts stored for the session."""
    artifacts_dir = session_dir(ctx["session"])["artifacts"]
    if not artifacts_dir.exists():
        return []
    return list(artifacts_dir.glob("custom/*/manifest.json"))


@pytest.mark.asyncio
async def test_an_invalid_component_identifier_is_normalized(
    client: httpx.AsyncClient,
    make_session: Any,
    queue_agent_turn: Any,
    resolve_session: Any,
    session_dir: Any,
) -> None:
    """REQ-046 / INV-057: an invalid component id is repaired and reported."""
    ctx = make_session("a2ui-invalid-id", mode="chat")

    session = await _make_artifact(
        client,
        ctx,
        queue_agent_turn,
        resolve_session,
        [
            {"id": "root", "component": "Column", "children": ["not-an-identifier"]},
            {"id": "not-an-identifier", "component": "Text", "text": "hello"},
        ],
    )

    thread = session.get_open_thread()
    assert thread is not None
    results = _tool_results(thread)
    assert any("UAX #31" in result for result in results), results

    # The persisted body carries the repaired identifier.
    manifests = _stored_artifacts(session_dir, ctx)
    assert manifests, "the normalized artifact must be written"

    body = manifests[0].parent / "body.json"
    assert "not_an_identifier" in body.read_text(encoding="utf-8")
    assert "not-an-identifier" not in body.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_an_unknown_component_type_is_rejected(
    client: httpx.AsyncClient,
    make_session: Any,
    queue_agent_turn: Any,
    resolve_session: Any,
    session_dir: Any,
) -> None:
    """REQ-046: an unsupported component type is refused."""
    ctx = make_session("a2ui-unknown-type", mode="chat")

    session = await _make_artifact(
        client,
        ctx,
        queue_agent_turn,
        resolve_session,
        [
            {"id": "root", "component": "Column", "children": ["widget"]},
            {"id": "widget", "component": "Wombat", "text": "hello"},
        ],
    )

    thread = session.get_open_thread()
    assert thread is not None
    results = _tool_results(thread)
    assert any("Wombat" in result for result in results), results
    assert any("not stored" in result for result in results), results

    assert not _stored_artifacts(session_dir, ctx), "a rejected artifact must not be written"


@pytest.mark.asyncio
async def test_a_dangling_child_reference_is_rejected(
    client: httpx.AsyncClient,
    make_session: Any,
    queue_agent_turn: Any,
    resolve_session: Any,
    session_dir: Any,
) -> None:
    """REQ-046: a child that does not exist is refused."""
    ctx = make_session("a2ui-dangling-child", mode="chat")

    session = await _make_artifact(
        client,
        ctx,
        queue_agent_turn,
        resolve_session,
        [{"id": "root", "component": "Column", "children": ["missing"]}],
    )

    thread = session.get_open_thread()
    assert thread is not None
    results = _tool_results(thread)
    assert any("Dangling child reference" in result for result in results), results

    assert not _stored_artifacts(session_dir, ctx)


@pytest.mark.asyncio
async def test_an_empty_component_list_is_rejected(
    client: httpx.AsyncClient,
    make_session: Any,
    queue_agent_turn: Any,
    resolve_session: Any,
    session_dir: Any,
) -> None:
    """REQ-046: an empty surface is refused."""
    ctx = make_session("a2ui-empty", mode="chat")

    session = await _make_artifact(
        client,
        ctx,
        queue_agent_turn,
        resolve_session,
        [],
    )

    thread = session.get_open_thread()
    assert thread is not None
    results = _tool_results(thread)
    assert any("cannot be empty" in result for result in results), results

    assert not _stored_artifacts(session_dir, ctx)


@pytest.mark.asyncio
async def test_a_valid_artifact_is_written_to_the_workspace(
    client: httpx.AsyncClient,
    make_session: Any,
    queue_agent_turn: Any,
    resolve_session: Any,
    session_dir: Any,
) -> None:
    """REQ-033 / INV-040: a valid artifact is persisted with its full structure."""
    ctx = make_session("a2ui-valid", mode="chat")

    session = await _make_artifact(
        client,
        ctx,
        queue_agent_turn,
        resolve_session,
        [
            {"id": "root", "component": "Column", "children": ["caption"]},
            {"id": "caption", "component": "Text", "text": "hello"},
        ],
    )

    thread = session.get_open_thread()
    assert thread is not None
    results = _tool_results(thread)
    assert any("not stored" not in result for result in results), results

    manifests = _stored_artifacts(session_dir, ctx)
    assert manifests, "the artifact must be written to disk"

    artifact_dir = manifests[0].parent
    assert (artifact_dir / "body.json").is_file()
    assert (artifact_dir / "state.json").is_file()


@pytest.mark.asyncio
async def test_a_created_artifact_is_listed_by_the_api(
    client: httpx.AsyncClient,
    make_session: Any,
    queue_agent_turn: Any,
    resolve_session: Any,
) -> None:
    """REQ-033: the created artifact is reachable through the artifact route."""
    ctx = make_session("a2ui-listed", mode="chat")

    await _make_artifact(
        client,
        ctx,
        queue_agent_turn,
        resolve_session,
        [
            {"id": "root", "component": "Column", "children": ["caption"]},
            {"id": "caption", "component": "Text", "text": "hello"},
        ],
    )

    listed = await client.get(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/artifact"
    )
    assert listed.status_code == 200

    artifacts = listed.json()
    assert artifacts, "the created artifact must be listed"
    assert artifacts[0]["family"] == "custom"
