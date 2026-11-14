"""End-to-end tests for the Sync PR and thread-acceptance lifecycle.

These tests require Gitea-backed persistence (the ephemeral test container
started by ``tests/conftest.py``). They assert the observable contract of
[INV-022] and [INV-025]:

* every session with an open thread keeps an open Sync PR from
  ``session/{session_id}`` to ``main``;
* the reviewable diff served by the API contains only ``data/`` deliverables;
* accepting a thread merges the Sync PR into ``main``, closes the thread,
  opens a successor thread and renews the Sync PR.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest

from seamus.harness.runner import get_runner_registry
from seamus.harness.steerable import SteerableToolCall
from seamus.persistence.workspace import get_workspace_manager


async def _drain(runner: Any, *, timeout: float = 60.0) -> None:
    """Wait for a runner's active turn to finish."""
    task = runner._active_task
    if task is not None and not task.done():
        await asyncio.wait_for(asyncio.shield(task), timeout=timeout)


def _open_sync_prs(session: Any) -> list[dict[str, Any]]:
    """Return the open Sync PRs of the session's agent repository."""
    ws_mgr = get_workspace_manager()
    repo_name = ws_mgr.get_agent_repo_name(session.agent_id)
    head_branch = f"session/{session.id}"
    return [
        pr
        for pr in ws_mgr.client.list_pull_requests(repo_name, state="open")
        if pr.get("head", {}).get("ref") == head_branch
    ]


@pytest.mark.asyncio
async def test_session_creation_opens_sync_pr(
    client: httpx.AsyncClient,
    make_session: Any,
    gitea_enabled: None,
) -> None:
    """INV-022: creating a session opens a Sync PR from the session branch to main."""
    ctx = make_session("sync-pr-create", mode="chat")

    prs = _open_sync_prs(ctx["session"])
    assert len(prs) == 1
    pr = prs[0]
    assert pr["head"]["ref"] == f"session/{ctx['session_id']}"
    assert pr["base"]["ref"] == "main"


@pytest.mark.asyncio
async def test_sync_pr_diff_exposes_only_data_deliverables(
    client: httpx.AsyncClient,
    make_session: Any,
    queue_agent_turn: Any,
    resolve_session: Any,
    gitea_enabled: None,
) -> None:
    """INV-025: the reviewable diff contains data/ changes and hides harness state."""
    ctx = make_session("sync-pr-diff", mode="chat")
    queue_agent_turn(
        ctx["session_id"],
        tool_calls=[
            SteerableToolCall(
                name="write_file",
                args={"file_path": "/workspace/report.md", "content": "# Report\n"},
            )
        ],
    )
    queue_agent_turn(ctx["session_id"], text="Wrote the report.")

    await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "write the report"},
    )

    session = resolve_session(ctx["session_id"])
    runner = get_runner_registry().get_runner(session)
    await _drain(runner)

    diff = await client.get(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/diff"
    )
    assert diff.status_code == 200
    body = diff.json()

    assert body["pr_number"] is not None
    assert body["pr_url"] is not None
    assert "data/report.md" in body["diff"]
    # Harness-internal directories never leak into the reviewable diff.
    assert "agent/state/" not in body["diff"]
    assert "agent/config/" not in body["diff"]


@pytest.mark.asyncio
async def test_thread_acceptance_merges_sync_pr_and_renews_it(
    client: httpx.AsyncClient,
    make_session: Any,
    queue_agent_turn: Any,
    resolve_session: Any,
    gitea_enabled: None,
) -> None:
    """INV-022: acceptance merges the Sync PR, closes the thread and renews the PR."""
    ctx = make_session("sync-pr-accept", mode="chat")
    queue_agent_turn(
        ctx["session_id"],
        tool_calls=[
            SteerableToolCall(
                name="write_file",
                args={"file_path": "/workspace/deliverable.txt", "content": "done\n"},
            )
        ],
    )
    queue_agent_turn(ctx["session_id"], text="Delivered.")

    await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "deliver"},
    )

    session = resolve_session(ctx["session_id"])
    runner = get_runner_registry().get_runner(session)
    await _drain(runner)

    before = _open_sync_prs(session)
    assert len(before) == 1
    original_pr_number = before[0]["number"]

    accepted = await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}"
        f"/thread/{ctx['thread_id']}/accept"
    )
    assert accepted.status_code == 200
    new_thread = accepted.json()
    assert new_thread["is_open"] is True
    assert str(new_thread["id"]) != ctx["thread_id"]

    session = resolve_session(ctx["session_id"])

    # The original Sync PR is merged and no longer open.
    after = _open_sync_prs(session)
    assert all(pr["number"] != original_pr_number for pr in after)

    # A renewed Sync PR exists for the same session branch.
    assert len(after) == 1
    assert after[0]["head"]["ref"] == f"session/{ctx['session_id']}"
    assert after[0]["base"]["ref"] == "main"


@pytest.mark.asyncio
async def test_acceptance_merges_data_deliverable_into_main(
    client: httpx.AsyncClient,
    make_session: Any,
    queue_agent_turn: Any,
    resolve_session: Any,
    gitea_enabled: None,
) -> None:
    """INV-025: the data-scoped merge lands the deliverable on main."""
    ctx = make_session("sync-pr-merge-main", mode="chat")
    queue_agent_turn(
        ctx["session_id"],
        tool_calls=[
            SteerableToolCall(
                name="write_file",
                args={"file_path": "/workspace/merged.txt", "content": "merged\n"},
            )
        ],
    )
    queue_agent_turn(ctx["session_id"], text="Done.")

    await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "produce"},
    )

    session = resolve_session(ctx["session_id"])
    runner = get_runner_registry().get_runner(session)
    await _drain(runner)

    accepted = await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}"
        f"/thread/{ctx['thread_id']}/accept"
    )
    assert accepted.status_code == 200

    ws_mgr = get_workspace_manager()
    repo_name = ws_mgr.get_agent_repo_name(ctx["agent"].id)
    content = ws_mgr.client.get_file_content(repo_name, "main", "data/merged.txt")
    assert content == "merged\n"
