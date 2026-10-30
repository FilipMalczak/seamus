"""Integration tests for FastAPI endpoints under /api/v-alpha/."""

import httpx
import pytest
from fastapi.testclient import TestClient

from seamus.config.models import AgentConfig, InferenceConfig, InferenceFormat
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


def test_ui_root_serving(client: TestClient) -> None:
    """Verify that root / serves the built React UI if ui/dist exists."""
    res = client.get("/")
    assert res.status_code == 200
    assert "Seamus Agent Harness" in res.text
    assert '<div id="root">' in res.text


def test_no_delete_invariant_on_routes() -> None:
    """Enforce INV-007: No DELETE routes exist anywhere in the application."""
    app = create_app()
    for route in app.routes:
        methods: set[str] = getattr(route, "methods", set())
        assert "DELETE" not in methods, f"Forbidden DELETE method found on route: {route}"


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

    # 4. GET on agent lists sessions (initially empty)
    detail_res = client.get(f"/api/v-alpha/agent/{agent_id}")
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["name"] == "agent-one"
    assert detail["sessions"] == []

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
        session_entity = list(agent_entity.sessions.values())[0]

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
        assert "RUN_STARTED" in content
        assert "TOOL_CALL_START" in content
        assert "RUN_FINISHED" in content
