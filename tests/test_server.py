"""Integration tests for FastAPI endpoints under /api/v-alpha/."""

from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient

from seamus.config.models import AgentConfig, InferenceConfig, InferenceFormat
from seamus.config.settings import (
    SystemSettings,
    SystemSettingsStore,
    reset_system_settings_store,
)
from seamus.config.template import ConfigTemplateStore, reset_config_template_store
from seamus.domain.entities import AgentStatus
from seamus.harness.runner import (
    SessionAgentRunner,
    get_runner_registry,
    reset_runner_registry,
)
from seamus.harness.store import HarnessStore, get_harness_store, reset_harness_store
from seamus.server.app import create_app
from tests.test_runner import FakeAgent


@pytest.fixture(autouse=True)
def reset_globals() -> None:
    """Ensure clean isolation between tests."""
    template = AgentConfig(
        inference=InferenceConfig(
            format=InferenceFormat.OPENAI,
            base_url="https://openrouter.ai/api/v1",
            api_key="test-api-key",
        ),
        model_name="openai/gpt-oss-120b",
    )
    reset_config_template_store(ConfigTemplateStore(initial_template=template))
    reset_system_settings_store(SystemSettingsStore(initial_settings=SystemSettings()))
    reset_harness_store(HarnessStore())
    reset_runner_registry()


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    return TestClient(app)


def test_health_check(client: TestClient) -> None:
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "service": "seamus"}


def test_system_info_endpoint(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that /api/v-alpha/system/info returns system info with Logfire metadata."""
    monkeypatch.setenv("LOGFIRE_ORG", "test-org")
    monkeypatch.setenv("LOGFIRE_BASE_URL", "https://logfire-custom.pydantic.dev")
    res = client.get("/api/v-alpha/system/info")
    assert res.status_code == 200
    data = res.json()
    assert "logfire" in data
    assert "enabled" in data["logfire"]
    assert "service_name" in data["logfire"]
    assert "url" in data["logfire"]
    if data["logfire"]["enabled"]:
        assert (
            data["logfire"]["url"]
            == f"https://logfire-custom.pydantic.dev/test-org/{data['logfire']['service_name']}"
        )
    else:
        assert data["logfire"]["url"] is None

    assert "gitea" in data
    assert "enabled" in data["gitea"]
    assert "url" in data["gitea"]
    assert "owner" in data["gitea"]


def test_ui_root_serving(tmp_path: Path) -> None:
    """Verify that root / serves the built React UI when dist exists, or returns 404 when absent."""
    # 1. When dist does not exist
    empty_dist = tmp_path / "empty_dist"
    app_without_ui = create_app(dist_dir=empty_dist)
    client_without_ui = TestClient(app_without_ui)
    res_absent = client_without_ui.get("/")
    assert res_absent.status_code == 404

    # 2. When dist exists
    dist_dir = tmp_path / "mock_dist"
    assets_dir = dist_dir / "assets"
    assets_dir.mkdir(parents=True)
    index_file = dist_dir / "index.html"
    index_file.write_text(
        "<!DOCTYPE html><html><head><title>Seamus Agent Harness</title></head>"
        '<body><div id="root"></div></body></html>'
    )

    app_with_ui = create_app(dist_dir=dist_dir)
    client_with_ui = TestClient(app_with_ui)
    res_present = client_with_ui.get("/")
    assert res_present.status_code == 200
    assert "Seamus Agent Harness" in res_present.text
    assert '<div id="root">' in res_present.text


def test_no_delete_invariant_on_routes() -> None:
    """Enforce INV-007: No DELETE routes exist anywhere in the application."""
    app = create_app()
    # The OpenAPI schema is the authoritative route table: it includes routes
    # mounted through nested routers, which a scan of `app.routes` alone misses.
    paths = app.openapi().get("paths", {})
    for path, operations in paths.items():
        assert "delete" not in operations, f"Forbidden DELETE method found on route: {path}"


def test_config_template_endpoints(client: TestClient) -> None:
    # 1. GET template
    res = client.get("/api/v-alpha/config-template")
    assert res.status_code == 200
    data = res.json()
    assert data["config"]["model_name"] == "openai/gpt-oss-120b"
    assert data["is_complete"] is True

    # 2. POST template with full object and clearing api_key to null
    update_payload = {
        "inference": {
            "format": "openai",
            "base_url": "https://custom-openrouter.org/v1",
            "api_key": None,
        },
        "model_name": "custom/model",
    }
    res_post = client.post("/api/v-alpha/config-template", json=update_payload)
    assert res_post.status_code == 200
    updated_data = res_post.json()
    assert updated_data["config"]["inference"]["base_url"] == "https://custom-openrouter.org/v1"
    assert updated_data["config"]["inference"]["api_key"] is None
    assert updated_data["config"]["model_name"] == "custom/model"
    assert updated_data["is_complete"] is False


def test_settings_endpoints(client: TestClient) -> None:
    # 1. GET settings defaults
    res = client.get("/api/v-alpha/settings")
    assert res.status_code == 200
    data = res.json()
    assert "settings" in data
    assert data["settings"]["skill_directories"] == ["~/.seamus/skills", "~/.skills"]

    # 2. POST settings update
    payload = {"skill_directories": ["/opt/system-skills", "/home/test/.skills"]}
    res_post = client.post("/api/v-alpha/settings", json=payload)
    assert res_post.status_code == 200
    updated_data = res_post.json()
    assert updated_data["settings"]["skill_directories"] == [
        "/opt/system-skills",
        "/home/test/.skills",
    ]

    # 3. GET reflects update
    res_get2 = client.get("/api/v-alpha/settings")
    assert res_get2.status_code == 200
    assert res_get2.json()["settings"]["skill_directories"] == [
        "/opt/system-skills",
        "/home/test/.skills",
    ]


def test_agent_lifecycle_endpoints(client: TestClient) -> None:
    # 1. List agents initially empty
    res = client.get("/api/v-alpha/agents")
    assert res.status_code == 200
    assert res.json() == []

    # 2. Create agent (inherits template with test-api-key)
    create_res = client.post("/api/v-alpha/agents", json={"name": "agent-one"})
    assert create_res.status_code == 201
    agent_data = create_res.json()
    assert agent_data["name"] == "agent-one"
    agent_id = agent_data["id"]

    # 3. Conflict on duplicate slug returns 409
    res_conflict = client.post("/api/v-alpha/agents", json={"name": "agent-one"})
    assert res_conflict.status_code == 409

    # 4. GET on agent lists sessions (contains default initial session with no name)
    detail_res = client.get(f"/api/v-alpha/agent/{agent_id}")
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["name"] == "agent-one"
    assert len(detail["sessions"]) == 1
    assert detail["sessions"][0]["name"] is None

    # Can also resolve by slug
    slug_detail = client.get("/api/v-alpha/agent/agent-one")
    assert slug_detail.status_code == 200
    assert slug_detail.json()["id"] == agent_id

    # 5. POST on agent updates with full object
    update_payload = {
        "name": "agent-one-renamed",
        "config": {
            "inference": {
                "format": "openai",
                "base_url": "https://openrouter.ai/api/v1",
                "api_key": "updated-agent-key",
            },
            "model_name": "openai/gpt-4o",
        },
    }
    update_res = client.post("/api/v-alpha/agent/agent-one", json=update_payload)
    assert update_res.status_code == 200
    assert update_res.json()["name"] == "agent-one-renamed"
    assert update_res.json()["config"]["model_name"] == "openai/gpt-4o"


def test_session_and_thread_endpoints(client: TestClient) -> None:
    # Create agent
    agent = client.post("/api/v-alpha/agents", json={"name": "my-agent"}).json()
    agent_id = agent["id"]

    # 1. Create session (automatically creates initial open thread)
    session_res = client.post(
        f"/api/v-alpha/agent/{agent_id}/session",
        json={"name": "session-one"},
    )
    assert session_res.status_code == 201
    session_data = session_res.json()
    assert len(session_data["threads"]) == 1
    initial_thread = session_data["threads"][0]
    assert initial_thread["is_open"] is True

    # 2. GET on session lists threads
    get_session_res = client.get("/api/v-alpha/agent/my-agent/session/session-one")
    assert get_session_res.status_code == 200
    assert len(get_session_res.json()["threads"]) == 1

    # 3. GET on thread without <T> redirects (307) to open thread
    redirect_res = client.get(
        "/api/v-alpha/agent/my-agent/session/session-one/thread",
        follow_redirects=False,
    )
    assert redirect_res.status_code == 307
    expected_location = (
        f"/api/v-alpha/agent/my-agent/session/session-one/thread/{initial_thread['id']}"
    )
    assert redirect_res.headers["location"] == expected_location

    # 4. Check thread status
    status_res = client.get(
        f"/api/v-alpha/agent/my-agent/session/session-one/thread/{initial_thread['id']}/status"
    )
    assert status_res.status_code == 200
    assert status_res.json()["status"] == "AWAITING_USER"

    # 5. Create new thread closes the first thread
    new_thread_res = client.post(
        "/api/v-alpha/agent/my-agent/session/session-one/thread",
        json={"name": "thread-two"},
    )
    assert new_thread_res.status_code == 201
    assert new_thread_res.json()["name"] == "thread-two"

    # Redirect now points to thread-two
    redirect_res2 = client.get(
        "/api/v-alpha/agent/my-agent/session/session-one/thread",
        follow_redirects=False,
    )
    assert redirect_res2.status_code == 307
    assert redirect_res2.headers["location"].endswith("thread-two")


def test_accept_thread_endpoint(client: TestClient) -> None:
    # 1. Setup agent and session
    agent_res = client.post("/api/v-alpha/agents", json={"name": "accept-agent"})
    agent_id = agent_res.json()["id"]

    session_res = client.post(
        f"/api/v-alpha/agent/{agent_id}/session",
        json={"name": "accept-session"},
    )
    session_data = session_res.json()
    t1 = session_data["threads"][0]
    assert t1["is_open"] is True

    # 2. Accept thread T1
    accept_res = client.post(
        f"/api/v-alpha/agent/{agent_id}/session/{session_data['id']}/thread/{t1['id']}/accept"
    )
    assert accept_res.status_code == 200
    t2 = accept_res.json()
    assert t2["id"] != t1["id"]
    assert t2["is_open"] is True

    # 3. Verify session threads list shows T1 closed and T2 open
    get_session_res = client.get(f"/api/v-alpha/agent/{agent_id}/session/{session_data['id']}")
    threads = get_session_res.json()["threads"]
    assert len(threads) == 2
    t1_check = next(t for t in threads if t["id"] == t1["id"])
    t2_check = next(t for t in threads if t["id"] == t2["id"])
    assert t1_check["is_open"] is False
    assert t2_check["is_open"] is True

    # 4. Attempting to accept already closed thread returns 400
    closed_accept_res = client.post(
        f"/api/v-alpha/agent/{agent_id}/session/{session_data['id']}/thread/{t1['id']}/accept"
    )
    assert closed_accept_res.status_code == 400
    assert "already closed" in closed_accept_res.json()["detail"]

    # 5. Non-existent thread returns 404
    non_existent_res = client.post(
        f"/api/v-alpha/agent/{agent_id}/session/{session_data['id']}/thread/unknown-thread/accept"
    )
    assert non_existent_res.status_code == 404


@pytest.mark.asyncio
async def test_user_input_and_streaming() -> None:
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Set up agent and session
        agent_res = await client.post("/api/v-alpha/agents", json={"name": "chat-agent"})
        agent = agent_res.json()
        await client.post(
            f"/api/v-alpha/agent/{agent['id']}/session",
            json={"name": "chat-session"},
        )

        store = get_harness_store()
        agent_entity = store.resolve_agent("chat-agent")
        from seamus.domain.resolution import resolve_session

        session_entity = resolve_session(agent_entity, "chat-session")

        # Inject fake runner with a small delay
        fake_agent = FakeAgent(delay=0.04)
        runner = SessionAgentRunner(session=session_entity, agent=fake_agent)
        get_runner_registry().set_runner(str(session_entity.id), runner)

        # 1. Post input
        res_input = await client.post(
            "/api/v-alpha/agent/chat-agent/session/chat-session/input",
            json={"message": "Tell me a joke"},
        )
        assert res_input.status_code == 202
        assert res_input.json()["status"] == "accepted"

        # 2. While agent is executing, posting another input returns 409 Conflict
        busy_res = await client.post(
            "/api/v-alpha/agent/chat-agent/session/chat-session/input",
            json={"message": "Wait, another question!"},
        )
        assert busy_res.status_code == 409
        assert "not in AWAITING_USER state" in busy_res.json()["detail"]

        # 3. Wait for active task to finish
        if runner._active_task is not None:
            await runner._active_task

        open_thread = session_entity.get_open_thread()
        assert open_thread.status == AgentStatus.AWAITING_USER

        # 4. Stream past events over SSE from the open thread (follow=False for replay)
        prefix = "/api/v-alpha/agent/chat-agent/session/chat-session/thread"
        stream_url = f"{prefix}/{open_thread.id}?follow=false"
        stream_res = await client.get(stream_url)
        assert stream_res.status_code == 200
        content = stream_res.text
        assert "Tell me a joke" in content
        assert "RUN_STARTED" in content
        assert "TOOL_CALL_START" in content
        assert "RUN_FINISHED" in content


@pytest.mark.asyncio
async def test_thread_switching_replays_user_messages() -> None:
    """Verify that switching between threads preserves and replays user messages."""
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Create agent
        agent_res = await client.post("/api/v-alpha/agents", json={"name": "multi-thread-agent"})
        agent_id = agent_res.json()["id"]

        # Default session is automatically created; get its ID
        agent_detail = (await client.get(f"/api/v-alpha/agent/{agent_id}")).json()
        session_id = agent_detail["sessions"][0]["id"]

        # Thread 1 is the default open thread
        session_detail = (
            await client.get(f"/api/v-alpha/agent/{agent_id}/session/{session_id}")
        ).json()
        t1_id = session_detail["threads"][0]["id"]

        # Inject fake runner
        store = get_harness_store()
        agent_entity = store.resolve_agent(agent_id)
        from seamus.domain.resolution import resolve_session

        session_entity = resolve_session(agent_entity, session_id)
        fake_agent = FakeAgent(delay=0.01)
        runner = SessionAgentRunner(session=session_entity, agent=fake_agent)
        get_runner_registry().set_runner(session_id, runner)

        # 1. Post to Thread 1 with a specific message_id
        res1 = await client.post(
            f"/api/v-alpha/agent/{agent_id}/session/{session_id}/input",
            json={"message": "First message in T1", "message_id": "user-msg-t1"},
        )
        assert res1.status_code == 202
        if runner._active_task is not None:
            await runner._active_task

        # 2. Create Thread 2 in the same session
        t2_res = await client.post(
            f"/api/v-alpha/agent/{agent_id}/session/{session_id}/thread",
            json={"name": "thread-two"},
        )
        assert t2_res.status_code == 201
        t2_id = t2_res.json()["id"]

        # Post to Thread 2
        res2 = await client.post(
            f"/api/v-alpha/agent/{agent_id}/session/{session_id}/input",
            json={"message": "Second message in T2", "message_id": "user-msg-t2"},
        )
        assert res2.status_code == 202
        if runner._active_task is not None:
            await runner._active_task

        # 3. Stream Thread 1 (closed now)
        t1_stream = await client.get(
            f"/api/v-alpha/agent/{agent_id}/session/{session_id}/thread/{t1_id}?follow=false"
        )
        assert t1_stream.status_code == 200
        assert "First message in T1" in t1_stream.text
        assert "user-msg-t1" in t1_stream.text
        assert "Second message in T2" not in t1_stream.text

        # 4. Stream Thread 2 (open)
        t2_stream = await client.get(
            f"/api/v-alpha/agent/{agent_id}/session/{session_id}/thread/{t2_id}?follow=false"
        )
        assert t2_stream.status_code == 200
        assert "Second message in T2" in t2_stream.text
        assert "user-msg-t2" in t2_stream.text
        assert "First message in T1" not in t2_stream.text

        # 5. Switch back to Thread 1
        t1_stream_back = await client.get(
            f"/api/v-alpha/agent/{agent_id}/session/{session_id}/thread/{t1_id}?follow=false"
        )
        assert t1_stream_back.status_code == 200
        assert "First message in T1" in t1_stream_back.text
        assert "user-msg-t1" in t1_stream_back.text


def test_session_diff_endpoint(client: TestClient) -> None:
    # 1. Create agent and session
    agent_res = client.post("/api/v-alpha/agents", json={"name": "diff-agent"})
    assert agent_res.status_code == 201
    agent_id = agent_res.json()["id"]

    session_res = client.post(
        f"/api/v-alpha/agent/{agent_id}/session", json={"name": "diff-session"}
    )
    assert session_res.status_code == 201
    session_id = session_res.json()["id"]

    # 2. Query diff with mocked WorkspaceManager
    mock_pr = {"id": 1, "number": 7, "head": {"ref": f"session/{session_id}"}}
    mock_diff = "diff --git a/a.txt b/a.txt\n+hello"

    with patch(
        "seamus.persistence.workspace.GitWorkspaceManager.get_sync_pr_diff",
        return_value=(mock_pr, mock_diff),
    ):
        diff_res = client.get(f"/api/v-alpha/agent/{agent_id}/session/{session_id}/diff")
        assert diff_res.status_code == 200
        data = diff_res.json()
        assert data["agent_id"] == agent_id
        assert data["session_id"] == session_id
        assert data["pr_number"] == 7
        assert data["diff"] == mock_diff
        if data["pr_url"] is not None:
            assert "pulls/7" in data["pr_url"]

    # 3. Non-existent session returns 404
    missing_res = client.get(f"/api/v-alpha/agent/{agent_id}/session/unknown-session/diff")
    assert missing_res.status_code == 404


def test_session_and_template_todo_implementation_config(client: TestClient) -> None:
    """Verify todo_implementation and skills_implementation config across template and session."""
    # 1. Template validation
    tmpl_res = client.get("/api/v-alpha/config-template")
    assert tmpl_res.status_code == 200
    tmpl_data = tmpl_res.json()["config"]
    assert tmpl_data["todo_implementation"] == "seamus"
    assert tmpl_data["skills_implementation"] == "seamus"

    # Invalid template value -> 422
    tmpl_data["todo_implementation"] = "invalid_choice"
    bad_tmpl_res = client.post("/api/v-alpha/config-template", json=tmpl_data)
    assert bad_tmpl_res.status_code == 422

    # Valid template value -> 200
    tmpl_data["todo_implementation"] = "none"
    tmpl_data["skills_implementation"] = "none"
    ok_tmpl_res = client.post("/api/v-alpha/config-template", json=tmpl_data)
    assert ok_tmpl_res.status_code == 200
    assert ok_tmpl_res.json()["config"]["todo_implementation"] == "none"
    assert ok_tmpl_res.json()["config"]["skills_implementation"] == "none"

    # Reset template back to none for session inheritance check below
    tmpl_data["todo_implementation"] = "none"
    tmpl_data["skills_implementation"] = "none"
    client.post("/api/v-alpha/config-template", json=tmpl_data)

    # 2. Session update and validation
    agent = client.post("/api/v-alpha/agents", json={"name": "todo-agent"}).json()
    session = client.post(
        f"/api/v-alpha/agent/{agent['id']}/session", json={"name": "todo-session"}
    ).json()

    assert session["config"]["todo_implementation"] == "none"
    assert session["config"]["skills_implementation"] == "none"

    # Invalid session todo_implementation -> 422
    bad_session_update = {
        "name": "todo-session",
        "config": {
            **session["config"],
            "todo_implementation": "invalid_value",
        },
    }
    bad_res = client.post(
        f"/api/v-alpha/agent/{agent['id']}/session/{session['id']}",
        json=bad_session_update,
    )
    assert bad_res.status_code == 422

    # Invalid session skills_implementation -> 422
    bad_skills_update = {
        "name": "todo-session",
        "config": {
            **session["config"],
            "skills_implementation": "invalid_value",
        },
    }
    bad_skills_res = client.post(
        f"/api/v-alpha/agent/{agent['id']}/session/{session['id']}",
        json=bad_skills_update,
    )
    assert bad_skills_res.status_code == 422

    # Valid session update -> 200
    good_session_update = {
        "name": "todo-session",
        "config": {
            **session["config"],
            "todo_implementation": "deepagents",
            "skills_implementation": "deepagents",
        },
    }
    good_res = client.post(
        f"/api/v-alpha/agent/{agent['id']}/session/{session['id']}",
        json=good_session_update,
    )
    assert good_res.status_code == 200
    assert good_res.json()["config"]["todo_implementation"] == "deepagents"
    assert good_res.json()["config"]["skills_implementation"] == "deepagents"


def test_session_and_template_artifacts_implementation_config(client: TestClient) -> None:
    """Verify artifacts_implementation config across template and session."""
    # 1. Template validation
    tmpl_res = client.get("/api/v-alpha/config-template")
    assert tmpl_res.status_code == 200
    tmpl_data = tmpl_res.json()["config"]
    assert tmpl_data["artifacts_implementation"] == "seamus"

    # Invalid template value -> 422
    tmpl_data["artifacts_implementation"] = "invalid_choice"
    bad_tmpl_res = client.post("/api/v-alpha/config-template", json=tmpl_data)
    assert bad_tmpl_res.status_code == 422

    # Valid template value -> 200
    tmpl_data["artifacts_implementation"] = "none"
    ok_tmpl_res = client.post("/api/v-alpha/config-template", json=tmpl_data)
    assert ok_tmpl_res.status_code == 200
    assert ok_tmpl_res.json()["config"]["artifacts_implementation"] == "none"

    # 2. Session update and validation
    agent = client.post("/api/v-alpha/agents", json={"name": "art-agent"}).json()
    session = client.post(
        f"/api/v-alpha/agent/{agent['id']}/session", json={"name": "art-session"}
    ).json()

    assert session["config"]["artifacts_implementation"] == "none"

    # Invalid session artifacts_implementation -> 422
    bad_session_update = {
        "name": "art-session",
        "config": {
            **session["config"],
            "artifacts_implementation": "invalid_value",
        },
    }
    bad_res = client.post(
        f"/api/v-alpha/agent/{agent['id']}/session/{session['id']}",
        json=bad_session_update,
    )
    assert bad_res.status_code == 422

    # Valid session update -> 200
    good_session_update = {
        "name": "art-session",
        "config": {
            **session["config"],
            "artifacts_implementation": "seamus",
        },
    }
    good_res = client.post(
        f"/api/v-alpha/agent/{agent['id']}/session/{session['id']}",
        json=good_session_update,
    )
    assert good_res.status_code == 200
    assert good_res.json()["config"]["artifacts_implementation"] == "seamus"
