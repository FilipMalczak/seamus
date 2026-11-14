"""End-to-end baseline for the web-search toolset.

The web-search tools (``web_search`` and ``fetch_web_page``) are bound to the
agent only when the session's config selects the DuckDuckGo implementation.
This file covers both halves of that rule through the HTTP surface:

* with web search enabled, the tools are bound and a scripted call reaches the
  real tool implementation (with the DuckDuckGo client stubbed, so no network
  traffic and no inference randomness);
* with web search disabled, the tools are not bound at all.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest

from seamus.config.models import (
    AgentConfig,
    InferenceConfig,
    InferenceFormat,
    SteerableConfig,
    WebSearchImplementation,
)
from seamus.harness.runner import get_runner_registry
from seamus.harness.steerable import SteerableToolCall


async def _drain(runner: Any, *, timeout: float = 30.0) -> None:
    """Wait for a runner's active turn to finish."""
    task = runner._active_task
    if task is not None and not task.done():
        await asyncio.wait_for(asyncio.shield(task), timeout=timeout)


def _make_session_with_config(steerable_store: Any, name: str, **overrides: Any) -> dict[str, Any]:
    """Create an agent/session pair with a custom configuration."""
    config = AgentConfig(
        inference=InferenceConfig(
            format=InferenceFormat.STEERABLE,
            base_url="https://openrouter.ai/api/v1",
            steerable=SteerableConfig(wait_timeout=10.0),
        ),
        model_name="steerable-model",
        mode="chat",
        **overrides,
    )
    agent = steerable_store.create_agent(config=config, name=name)
    session = steerable_store.create_session(agent_identifier=str(agent.id))
    thread = session.get_open_thread()
    return {
        "agent": agent,
        "session": session,
        "thread": thread,
        "agent_id": str(agent.id),
        "session_id": str(session.id),
        "thread_id": str(thread.id) if thread else None,
    }


def _tool_results(thread: Any) -> list[str]:
    """Return the textual results of the tool calls recorded on a thread."""
    results: list[str] = []
    for event in thread.events:
        ev_type = getattr(event, "type", None)
        if ev_type is None and isinstance(event, dict):
            ev_type = event.get("type")
        if str(getattr(ev_type, "value", ev_type)) != "TOOL_CALL_RESULT":
            continue
        content = getattr(event, "content", None)
        if content is None and isinstance(event, dict):
            content = event.get("content")
        results.append(str(content or ""))
    return results


@pytest.mark.asyncio
async def test_web_search_tool_returns_stubbed_results(
    client: httpx.AsyncClient,
    steerable_store: Any,
    queue_agent_turn: Any,
    resolve_session: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A scripted ``web_search`` call reaches the real tool and returns results."""
    import seamus.harness.web_search as web_search_module

    class StubDDGS:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def text(self, query: str, max_results: int = 5) -> list[dict[str, str]]:
            return [
                {
                    "title": "Seamus documentation",
                    "href": "https://example.invalid/seamus",
                    "body": "How to run Seamus.",
                }
            ]

    monkeypatch.setattr(web_search_module, "DDGS", StubDDGS)

    ctx = _make_session_with_config(
        steerable_store,
        "web-search-e2e",
        web_search=WebSearchImplementation.DUCKDUCKGO,
    )

    queue_agent_turn(
        ctx["session_id"],
        tool_calls=[SteerableToolCall(name="web_search", args={"query": "seamus docs"})],
    )
    queue_agent_turn(ctx["session_id"], text="Found the docs.")

    await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "Search the web for the Seamus docs."},
    )

    session = resolve_session(ctx["session_id"])
    runner = get_runner_registry().get_runner(session)
    await _drain(runner)

    thread = session.get_open_thread()
    assert thread is not None
    results = _tool_results(thread)
    assert any("Seamus documentation" in r for r in results)
    assert any("https://example.invalid/seamus" in r for r in results)


@pytest.mark.asyncio
async def test_web_search_tools_are_absent_when_disabled(
    client: httpx.AsyncClient,
    steerable_store: Any,
    queue_agent_turn: Any,
    resolve_session: Any,
) -> None:
    """With web search disabled the tools are not bound to the agent."""
    ctx = _make_session_with_config(
        steerable_store,
        "web-search-disabled",
        web_search=WebSearchImplementation.NONE,
    )

    queue_agent_turn(
        ctx["session_id"],
        tool_calls=[
            SteerableToolCall(name="write_file", args={"file_path": "/workspace/x", "content": "x"})
        ],
    )
    queue_agent_turn(ctx["session_id"], text="Wrote a file.")

    await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "Write a file."},
    )

    session = resolve_session(ctx["session_id"])
    runner = get_runner_registry().get_runner(session)
    await _drain(runner)

    res = await client.get(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/steerable"
    )

    assert res.status_code == 200
    instances = res.json()
    assert instances
    tools = instances[0]["known_tools"]
    assert "web_search" not in tools
    assert "fetch_web_page" not in tools
