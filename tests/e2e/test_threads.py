"""End-to-end baseline for the thread lifecycle routes.

Threads are the unit of conversation in Seamus. This file covers the routes
that create, address, inspect, rename, and redirect to threads — the surface
the web UI leans on for navigation.

The tests drive the real ASGI application against the real harness store. The
only substitution is the inference provider (the ``steerable`` scripted
provider) and the container (the in-process stub sandbox).
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest

from seamus.domain.entities import AgentStatus


def _thread_url(ctx: dict[str, Any], suffix: str = "") -> str:
    """Return the thread collection URL for a session."""
    base = f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/thread"
    return f"{base}{suffix}"


async def _run_turn(
    client: httpx.AsyncClient,
    ctx: dict[str, Any],
    queue_agent_turn: Any,
    resolve_session: Any,
    *,
    text: str = "Answer.",
) -> None:
    """Run one scripted turn so the session's open thread is no longer empty."""
    queue_agent_turn(ctx["session_id"], text=text)

    await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "Say something."},
    )

    session = resolve_session(ctx["session_id"])

    # The runner schedules its turn asynchronously, so the active task is not
    # necessarily observable yet. Poll the thread instead: it is non-empty and
    # back to `AWAITING_USER` once the scripted turn has been recorded.
    deadline = asyncio.get_running_loop().time() + 30.0
    while asyncio.get_running_loop().time() < deadline:
        thread = session.get_open_thread()
        if thread is not None and thread.events and thread.status is AgentStatus.AWAITING_USER:
            return
        await asyncio.sleep(0.05)
    raise AssertionError("The scripted turn did not complete within 30s")


@pytest.mark.asyncio
async def test_thread_creation_returns_an_open_thread(
    client: httpx.AsyncClient,
    make_session: Any,
) -> None:
    """Creating a thread yields an open thread in the requested session."""
    ctx = make_session("thread-create")

    res = await client.post(_thread_url(ctx), json={"name": "first-thread"})

    assert res.status_code == 201
    body = res.json()
    assert body["name"] == "first-thread"
    assert body["is_open"] is True
    assert body["status"] == AgentStatus.AWAITING_USER.value
    assert body["id"]


@pytest.mark.asyncio
async def test_thread_creation_reuses_an_empty_open_thread(
    client: httpx.AsyncClient,
    make_session: Any,
) -> None:
    """INV-028: an empty open thread is reused in place rather than duplicated."""
    ctx = make_session("thread-reuse")
    first = (await client.post(_thread_url(ctx), json={"name": "first"})).json()

    second = (await client.post(_thread_url(ctx), json={"name": "second"})).json()

    assert second["id"] == first["id"], "the empty thread should be reused in place"
    assert second["name"] == "second"

    detail = (
        await client.get(f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}")
    ).json()
    assert len(detail["threads"]) == 1


@pytest.mark.asyncio
async def test_thread_creation_closes_a_non_empty_open_thread(
    client: httpx.AsyncClient,
    make_session: Any,
    queue_agent_turn: Any,
    resolve_session: Any,
) -> None:
    """A session has at most one open thread: creating a new one closes the old."""
    ctx = make_session("thread-exclusive")
    await _run_turn(client, ctx, queue_agent_turn, resolve_session)

    # The first creation replaces the now non-empty thread with a fresh, empty
    # one. A second turn makes that thread non-empty too, so the next creation
    # has to open yet another thread rather than reusing it.
    first = (await client.post(_thread_url(ctx), json={"name": "first"})).json()
    await _run_turn(client, ctx, queue_agent_turn, resolve_session)
    second = (await client.post(_thread_url(ctx), json={"name": "second"})).json()

    assert second["id"] != first["id"]
    assert second["is_open"] is True

    detail = (
        await client.get(f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}")
    ).json()
    open_threads = [t for t in detail["threads"] if t["is_open"]]
    assert len(open_threads) == 1
    assert open_threads[0]["id"] == second["id"]


@pytest.mark.asyncio
async def test_thread_creation_rejects_a_duplicate_name(
    client: httpx.AsyncClient,
    make_session: Any,
) -> None:
    """A duplicate thread slug is rejected with a 409."""
    ctx = make_session("thread-duplicate")
    await client.post(_thread_url(ctx), json={"name": "duplicate"})

    res = await client.post(_thread_url(ctx), json={"name": "duplicate"})

    assert res.status_code == 409


@pytest.mark.asyncio
async def test_thread_creation_rejects_an_unknown_session(
    client: httpx.AsyncClient,
    make_session: Any,
) -> None:
    """Creating a thread under an unknown session is a 404."""
    ctx = make_session("thread-unknown-session")
    url = f"/api/v-alpha/agent/{ctx['agent_id']}/session/does-not-exist/thread"

    res = await client.post(url, json={"name": "orphan"})

    assert res.status_code == 404


@pytest.mark.asyncio
async def test_thread_status_reports_the_current_status(
    client: httpx.AsyncClient,
    make_session: Any,
) -> None:
    """The status route reports the thread's execution status."""
    ctx = make_session("thread-status")
    thread = (await client.post(_thread_url(ctx), json={"name": "status-thread"})).json()

    res = await client.get(_thread_url(ctx, f"/{thread['id']}/status"))

    assert res.status_code == 200
    assert res.json()["status"] == AgentStatus.AWAITING_USER.value


@pytest.mark.asyncio
async def test_thread_status_rejects_an_unknown_thread(
    client: httpx.AsyncClient,
    make_session: Any,
) -> None:
    """The status route is a 404 for an unknown thread."""
    ctx = make_session("thread-status-missing")

    res = await client.get(_thread_url(ctx, "/does-not-exist/status"))

    assert res.status_code == 404


@pytest.mark.asyncio
async def test_thread_rename_updates_the_thread(
    client: httpx.AsyncClient,
    make_session: Any,
) -> None:
    """Renaming a thread is observable on the next read of the session."""
    ctx = make_session("thread-rename")
    thread = (await client.post(_thread_url(ctx), json={"name": "before"})).json()

    res = await client.post(_thread_url(ctx, f"/{thread['id']}"), json={"name": "after"})

    assert res.status_code == 200
    assert res.json()["name"] == "after"

    detail = (
        await client.get(f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}")
    ).json()
    names = {t["id"]: t["name"] for t in detail["threads"]}
    assert names[thread["id"]] == "after"


@pytest.mark.asyncio
async def test_thread_rename_rejects_a_duplicate_name(
    client: httpx.AsyncClient,
    make_session: Any,
    queue_agent_turn: Any,
    resolve_session: Any,
) -> None:
    """Renaming a thread onto an existing slug is rejected with a 409."""
    ctx = make_session("thread-rename-duplicate")

    # "taken" is created and then made non-empty, so the next creation opens a
    # second, distinct thread that can collide with it.
    await client.post(_thread_url(ctx), json={"name": "taken"})
    await _run_turn(client, ctx, queue_agent_turn, resolve_session)
    other = (await client.post(_thread_url(ctx), json={"name": "other"})).json()
    assert other["name"] == "other"

    res = await client.post(_thread_url(ctx, f"/{other['id']}"), json={"name": "taken"})

    assert res.status_code == 409


@pytest.mark.asyncio
async def test_thread_collection_redirects_to_the_open_thread(
    client: httpx.AsyncClient,
    make_session: Any,
) -> None:
    """The thread collection redirects to the session's open thread."""
    ctx = make_session("thread-redirect")
    thread = (await client.post(_thread_url(ctx), json={"name": "redirect-target"})).json()

    res = await client.get(_thread_url(ctx), follow_redirects=False)

    assert res.status_code == 307
    # A named thread is addressed by its slug; an unnamed one by its id.
    assert res.headers["location"].endswith("/thread/redirect-target")
    assert thread["name"] == "redirect-target"


@pytest.mark.asyncio
async def test_thread_collection_redirects_to_an_unnamed_thread_by_id(
    client: httpx.AsyncClient,
    make_session: Any,
) -> None:
    """An unnamed open thread is addressed by its identifier."""
    ctx = make_session("thread-redirect-unnamed")
    thread = ctx["thread"]

    res = await client.get(_thread_url(ctx), follow_redirects=False)

    assert res.status_code == 307
    assert res.headers["location"].endswith(f"/thread/{thread.id}")


@pytest.mark.asyncio
async def test_thread_stream_replays_recorded_events(
    client: httpx.AsyncClient,
    make_session: Any,
    queue_agent_turn: Any,
    resolve_session: Any,
) -> None:
    """The thread stream replays the events recorded on the thread."""
    ctx = make_session("thread-stream")
    await _run_turn(client, ctx, queue_agent_turn, resolve_session, text="Streamed answer.")

    session = resolve_session(ctx["session_id"])
    thread = session.get_open_thread()
    assert thread is not None

    res = await client.get(
        _thread_url(ctx, f"/{thread.id}"),
        headers={"accept": "text/event-stream"},
        params={"follow": "false"},
    )

    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/event-stream")
    body = res.text
    assert "RUN_FINISHED" in body
    assert "Streamed answer." in body
