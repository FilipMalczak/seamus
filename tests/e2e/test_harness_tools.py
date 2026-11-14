"""End-to-end baseline for the harness tool middlewares.

Seamus exposes three native tool surfaces to the agent: the todo planner
(``create_todo_item`` / ``edit_todo_item`` / ``delete_todo_item``), the skills
loader (``load_skill`` / ``unload_skill``), and the web-search tools
(``web_search`` / ``fetch_web_page``).

This file drives them the way a user would: a scripted model turn calls the
tool, the real middleware executes it, and the test asserts on the observable
result — the thread's todo list, the thread's active skills, the tool-call
result event, and the persisted state on disk.

The only substitution is the inference provider (the ``steerable`` scripted
provider) and the container (the in-process stub sandbox).
"""

from __future__ import annotations

import asyncio
import json
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


async def _run_tool_turn(
    client: httpx.AsyncClient,
    ctx: dict[str, Any],
    queue_agent_turn: Any,
    resolve_session: Any,
    tool_calls: list[SteerableToolCall],
    *,
    text: str = "Done.",
) -> Any:
    """Run one scripted turn that calls ``tool_calls``, and return the session."""
    queue_agent_turn(ctx["session_id"], tool_calls=tool_calls)
    queue_agent_turn(ctx["session_id"], text=text)

    await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "Do the thing."},
    )

    session = resolve_session(ctx["session_id"])
    runner = get_runner_registry().get_runner(session)
    await _drain(runner)
    return session


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


@pytest.mark.asyncio
async def test_create_todo_item_adds_a_todo_to_the_thread(
    client: httpx.AsyncClient,
    make_session: Any,
    queue_agent_turn: Any,
    resolve_session: Any,
) -> None:
    """A scripted ``create_todo_item`` call adds a todo to the active thread."""
    ctx = make_session("todo-create", mode="chat")

    session = await _run_tool_turn(
        client,
        ctx,
        queue_agent_turn,
        resolve_session,
        [
            SteerableToolCall(
                name="create_todo_item",
                args={"content": "Write the report", "status": "pending"},
            )
        ],
    )

    thread = session.get_open_thread()
    assert thread is not None
    assert len(thread.todos) == 1
    todo = thread.todos[0]
    assert todo.content == "Write the report"
    assert todo.status == "pending"
    assert todo.parent_id is None
    assert todo.id


@pytest.mark.asyncio
async def test_create_todo_item_persists_the_todos_to_disk(
    client: httpx.AsyncClient,
    make_session: Any,
    queue_agent_turn: Any,
    resolve_session: Any,
) -> None:
    """The todo list is persisted to the thread's state directory."""
    ctx = make_session("todo-persist", mode="chat")

    session = await _run_tool_turn(
        client,
        ctx,
        queue_agent_turn,
        resolve_session,
        [
            SteerableToolCall(
                name="create_todo_item",
                args={"content": "Persisted task"},
            )
        ],
    )

    thread = session.get_open_thread()
    assert thread is not None
    todos_file = session_dir_path(session, thread.id) / "todos.json"
    assert todos_file.is_file()
    persisted = json.loads(todos_file.read_text(encoding="utf-8"))
    assert [t["content"] for t in persisted] == ["Persisted task"]


def session_dir_path(session: Any, thread_id: Any) -> Any:
    """Return the on-disk state directory of a thread."""
    from seamus.persistence.workspace import get_workspace_manager

    ws_mgr = get_workspace_manager()
    return ws_mgr.get_thread_state_dir(session.agent_id, session.id, thread_id)


@pytest.mark.asyncio
async def test_create_todo_item_rejects_an_unknown_parent(
    client: httpx.AsyncClient,
    make_session: Any,
    queue_agent_turn: Any,
    resolve_session: Any,
) -> None:
    """Creating a subtask under an unknown parent reports an error and adds nothing."""
    ctx = make_session("todo-bad-parent", mode="chat")

    session = await _run_tool_turn(
        client,
        ctx,
        queue_agent_turn,
        resolve_session,
        [
            SteerableToolCall(
                name="create_todo_item",
                args={"content": "Orphan", "parent_id": "zzzz"},
            )
        ],
    )

    thread = session.get_open_thread()
    assert thread is not None
    assert thread.todos == []
    assert any("not found" in r for r in _tool_results(thread))


@pytest.mark.asyncio
async def test_edit_todo_item_updates_the_status(
    client: httpx.AsyncClient,
    make_session: Any,
    queue_agent_turn: Any,
    resolve_session: Any,
) -> None:
    """A scripted ``edit_todo_item`` call updates the todo's status."""
    ctx = make_session("todo-edit", mode="chat")

    session = await _run_tool_turn(
        client,
        ctx,
        queue_agent_turn,
        resolve_session,
        [
            SteerableToolCall(
                name="create_todo_item",
                args={"content": "Finish the task"},
            )
        ],
    )
    thread = session.get_open_thread()
    assert thread is not None
    todo_id = thread.todos[0].id

    session = await _run_tool_turn(
        client,
        ctx,
        queue_agent_turn,
        resolve_session,
        [
            SteerableToolCall(
                name="edit_todo_item",
                args={"id": todo_id, "new_status": "done"},
            )
        ],
    )

    thread = session.get_open_thread()
    assert thread is not None
    assert thread.todos[0].status == "done"


@pytest.mark.asyncio
async def test_delete_todo_item_removes_the_todo(
    client: httpx.AsyncClient,
    make_session: Any,
    queue_agent_turn: Any,
    resolve_session: Any,
) -> None:
    """A scripted ``delete_todo_item`` call removes the todo."""
    ctx = make_session("todo-delete", mode="chat")

    session = await _run_tool_turn(
        client,
        ctx,
        queue_agent_turn,
        resolve_session,
        [
            SteerableToolCall(
                name="create_todo_item",
                args={"content": "Temporary task"},
            )
        ],
    )
    thread = session.get_open_thread()
    assert thread is not None
    todo_id = thread.todos[0].id

    session = await _run_tool_turn(
        client,
        ctx,
        queue_agent_turn,
        resolve_session,
        [
            SteerableToolCall(
                name="delete_todo_item",
                args={"id": todo_id},
            )
        ],
    )

    thread = session.get_open_thread()
    assert thread is not None
    assert thread.todos == []


@pytest.mark.asyncio
async def test_load_skill_activates_the_skill_on_the_thread(
    client: httpx.AsyncClient,
    make_session: Any,
    queue_agent_turn: Any,
    resolve_session: Any,
) -> None:
    """A scripted ``load_skill`` call activates the skill on the thread."""
    ctx = make_session("skill-load", mode="chat")

    session = await _run_tool_turn(
        client,
        ctx,
        queue_agent_turn,
        resolve_session,
        [SteerableToolCall(name="load_skill", args={"name": "artifacts"})],
    )

    thread = session.get_open_thread()
    assert thread is not None
    assert "artifacts" in thread.active_skills
    assert any("loaded successfully" in r for r in _tool_results(thread))


@pytest.mark.asyncio
async def test_load_skill_reports_an_unknown_skill(
    client: httpx.AsyncClient,
    make_session: Any,
    queue_agent_turn: Any,
    resolve_session: Any,
) -> None:
    """Loading a skill that does not exist reports an error and activates nothing."""
    ctx = make_session("skill-unknown", mode="chat")

    session = await _run_tool_turn(
        client,
        ctx,
        queue_agent_turn,
        resolve_session,
        [SteerableToolCall(name="load_skill", args={"name": "no-such-skill"})],
    )

    thread = session.get_open_thread()
    assert thread is not None
    assert thread.active_skills == []
    assert any("not found" in r for r in _tool_results(thread))


@pytest.mark.asyncio
async def test_unload_skill_deactivates_the_skill(
    client: httpx.AsyncClient,
    make_session: Any,
    queue_agent_turn: Any,
    resolve_session: Any,
) -> None:
    """A scripted ``unload_skill`` call deactivates the skill again."""
    ctx = make_session("skill-unload", mode="chat")

    session = await _run_tool_turn(
        client,
        ctx,
        queue_agent_turn,
        resolve_session,
        [SteerableToolCall(name="load_skill", args={"name": "artifacts"})],
    )
    thread = session.get_open_thread()
    assert thread is not None
    assert "artifacts" in thread.active_skills

    session = await _run_tool_turn(
        client,
        ctx,
        queue_agent_turn,
        resolve_session,
        [SteerableToolCall(name="unload_skill", args={"name": "artifacts"})],
    )

    thread = session.get_open_thread()
    assert thread is not None
    assert "artifacts" not in thread.active_skills


@pytest.mark.asyncio
async def test_web_search_tool_is_bound_to_the_agent(
    client: httpx.AsyncClient,
    make_session: Any,
    queue_agent_turn: Any,
    resolve_session: Any,
) -> None:
    """The web-search tools are bound to the agent when web search is enabled."""
    ctx = make_session("web-search-tools", mode="chat")

    await _run_tool_turn(
        client,
        ctx,
        queue_agent_turn,
        resolve_session,
        [SteerableToolCall(name="write_file", args={"file_path": "/workspace/x", "content": "x"})],
    )

    res = await client.get(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/steerable"
    )

    assert res.status_code == 200
    instances = res.json()
    assert instances
    tools = instances[0]["known_tools"]
    assert "web_search" in tools
    assert "fetch_web_page" in tools
