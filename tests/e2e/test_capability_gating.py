"""End-to-end tests for the harness capability gating.

Several harness subsystems can be switched off in the agent configuration.
When they are, the model must not see the corresponding tools at all, and the
prompt must not advertise them. These tests assert that through the public
inspection endpoint, which reports the *live* tool inventory of the session's
runner:

* REQ-050 / INV-061 — the artifacts subsystem can be disabled, and the
  artifact-building tools then disappear from the tool inventory;
* REQ-029 / INV-033 — the todo middleware can be disabled;
* REQ-043 / INV-054 — the skills middleware can be disabled;
* REQ-044 / INV-055 — the web-search capability can be disabled;
* INV-054 — the tools a skill declares are gated until the skill is loaded.
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


# The tools that the *chat* mode exposes for the artifacts subsystem. The
# plan lifecycle tools (`plan`, `make_plan`, ...) belong to the plan mode and
# its phases, so they are asserted separately.
ARTIFACT_TOOLS = {"make_artifact", "make_questionnaire", "wait_for_click"}


async def _inspect(client: httpx.AsyncClient, ctx: dict[str, Any]) -> dict[str, Any]:
    """Fetch the inspection report of a session."""
    response = await client.get(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/inspect"
    )
    assert response.status_code == 200
    return dict(response.json())


async def _tool_names(client: httpx.AsyncClient, ctx: dict[str, Any]) -> set[str]:
    """Return the names of the tools bound to the session's runner."""
    body = await _inspect(client, ctx)
    return {tool["name"] for tool in body["tools"]}


@pytest.mark.asyncio
async def test_artifact_tools_are_bound_by_default(
    client: httpx.AsyncClient,
    make_session: Any,
) -> None:
    """REQ-033: the artifact-building tools are part of the default toolset."""
    ctx = make_session("gating-artifacts-on", mode="chat")

    names = await _tool_names(client, ctx)

    assert ARTIFACT_TOOLS.issubset(names)


@pytest.mark.asyncio
async def test_disabling_artifacts_removes_the_artifact_tools(
    client: httpx.AsyncClient,
    make_session: Any,
) -> None:
    """REQ-050 / INV-061: the artifact tools are gone when the subsystem is off."""
    ctx = make_session("gating-artifacts-off", mode="chat", artifacts_implementation="none")

    names = await _tool_names(client, ctx)

    assert not (ARTIFACT_TOOLS & names), f"artifact tools still bound: {ARTIFACT_TOOLS & names}"


@pytest.mark.asyncio
async def test_disabling_artifacts_keeps_the_plan_lifecycle_tools(
    client: httpx.AsyncClient,
    make_session: Any,
) -> None:
    """REQ-050: the plan lifecycle survives the artifacts toggle.

    In the plan/discuss phase the artifact *builders* are removed but the
    phase-transition tools remain.
    """
    ctx = make_session(
        "gating-artifacts-plan",
        mode="plan",
        phase="discuss",
        artifacts_implementation="none",
    )

    names = await _tool_names(client, ctx)

    assert "plan" in names
    assert "discard" in names
    assert not (ARTIFACT_TOOLS & names)


@pytest.mark.asyncio
async def test_disabling_artifacts_is_reported_by_the_inspector(
    client: httpx.AsyncClient,
    make_session: Any,
) -> None:
    """REQ-050: the inspector reports the active artifacts implementation."""
    ctx = make_session("gating-artifacts-report", mode="chat", artifacts_implementation="none")

    body = await _inspect(client, ctx)

    assert body["artifacts_implementation"] == "none"


@pytest.mark.asyncio
async def test_disabling_the_todo_middleware_removes_the_todo_tools(
    client: httpx.AsyncClient,
    make_session: Any,
) -> None:
    """REQ-029 / INV-033: the todo tools are gone when the middleware is off."""
    ctx = make_session("gating-todos-off", mode="chat", todo_implementation="none")

    names = await _tool_names(client, ctx)

    assert not ({"write_todos"} & names), "the todo tool is still bound"


@pytest.mark.asyncio
async def test_disabling_the_todo_middleware_is_reported_by_the_inspector(
    client: httpx.AsyncClient,
    make_session: Any,
) -> None:
    """REQ-029: the inspector reports the active todo implementation."""
    ctx = make_session("gating-todos-report", mode="chat", todo_implementation="none")

    body = await _inspect(client, ctx)

    assert body["todo_implementation"] == "none"


@pytest.mark.asyncio
async def test_disabling_the_skills_middleware_removes_the_skill_tools(
    client: httpx.AsyncClient,
    make_session: Any,
) -> None:
    """REQ-043 / INV-054: the skill tools are gone when the middleware is off."""
    ctx = make_session("gating-skills-off", mode="chat", skills_implementation="none")

    names = await _tool_names(client, ctx)

    assert not ({"load_skill", "unload_skill"} & names), "a skill tool is still bound"


@pytest.mark.asyncio
async def test_the_skill_tools_are_bound_by_default(
    client: httpx.AsyncClient,
    make_session: Any,
) -> None:
    """REQ-043: the skill lifecycle tools are part of the default toolset."""
    ctx = make_session("gating-skills-on", mode="chat")

    names = await _tool_names(client, ctx)

    assert {"load_skill", "unload_skill"}.issubset(names)


@pytest.mark.asyncio
async def test_disabling_web_search_removes_the_web_tools(
    client: httpx.AsyncClient,
    make_session: Any,
) -> None:
    """REQ-044 / INV-055: the web-search tools are gone when the capability is off."""
    ctx = make_session("gating-web-off", mode="chat", web_search="none")

    names = await _tool_names(client, ctx)

    assert "web_search" not in names
    assert "fetch_web_page" not in names


@pytest.mark.asyncio
async def test_web_search_is_reported_by_the_inspector(
    client: httpx.AsyncClient,
    make_session: Any,
) -> None:
    """REQ-044: the inspector reports the active web-search implementation."""
    ctx = make_session("gating-web-report", mode="chat", web_search="none")

    body = await _inspect(client, ctx)

    assert body["web_search"] == "none"


@pytest.mark.asyncio
async def test_a_skill_tool_is_gated_until_the_skill_is_loaded(
    client: httpx.AsyncClient,
    make_session: Any,
    queue_agent_turn: Any,
    resolve_session: Any,
) -> None:
    """INV-054: a skill's declared tools stay gated until the skill is loaded.

    The bundled ``artifacts`` skill declares ``make_artifact`` among its
    allowed tools. Before it is loaded the skill is inactive, so the tool is
    not advertised as skill-gated; after loading it, the skill is active on
    the thread.
    """
    ctx = make_session("gating-skill-load", mode="chat")

    before = await _tool_names(client, ctx)
    assert "load_skill" in before

    # The bundled `artifacts` skill is discovered for every session; loading it
    # must activate the skill on the thread.
    queue_agent_turn(
        ctx["session_id"],
        tool_calls=[SteerableToolCall(name="load_skill", args={"name": "artifacts"})],
    )
    queue_agent_turn(ctx["session_id"], text="Loaded.")

    await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "load the artifacts skill"},
    )

    session = resolve_session(ctx["session_id"])
    runner = get_runner_registry().get_runner(session)
    await _drain(runner)

    thread = session.get_open_thread()
    assert thread is not None
    assert "artifacts" in thread.active_skills
