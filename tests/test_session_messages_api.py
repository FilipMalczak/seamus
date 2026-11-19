"""Integration tests for session-level and thread-level paginated messages endpoints."""

import pytest
from fastapi.testclient import TestClient

from seamus.config.models import AgentConfig, InferenceConfig, InferenceFormat
from seamus.config.settings import (
    SystemSettings,
    SystemSettingsStore,
    reset_system_settings_store,
)
from seamus.config.template import ConfigTemplateStore, reset_config_template_store
from seamus.harness.runner import reset_runner_registry
from seamus.harness.store import HarnessStore, get_harness_store, reset_harness_store
from seamus.server.app import create_app


@pytest.fixture(autouse=True)
def reset_globals() -> None:
    template = AgentConfig(
        inference=InferenceConfig(
            format=InferenceFormat.OPENAI,
            base_url="https://openrouter.ai/api/v1",
            api_key="test-api-key",
        ),
        model_name="openai/gpt-oss-120b",
    )
    reset_config_template_store(ConfigTemplateStore(initial_template=template))
    reset_system_settings_store(
        SystemSettingsStore(
            initial_settings=SystemSettings(
                api_batch_size=50, ui_batch_size=200, memory_batch_size=300
            )
        )
    )
    reset_harness_store(HarnessStore())
    reset_runner_registry()


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    return TestClient(app)


def test_session_and_thread_messages_pagination(client: TestClient) -> None:
    store = get_harness_store()
    cfg = AgentConfig(
        inference=InferenceConfig(
            format=InferenceFormat.OPENAI,
            base_url="https://openrouter.ai/api/v1",
            api_key="test-api-key",
        ),
        model_name="openai/gpt-oss-120b",
    )
    agent = store.create_agent(config=cfg, name="test-agent")
    session = store.create_session(str(agent.id), name="test-session")

    # Thread 1: 30 messages
    t1 = session.get_open_thread()
    for i in range(30):
        t1.append_event({"type": "USER_MESSAGE", "id": f"t1-msg-{i}", "content": f"T1 Msg {i}"})

    # Thread 2: 40 messages
    t2 = store.create_thread(str(agent.id), str(session.id), name="thread-2")
    for i in range(40):
        t2.append_event({"type": "USER_MESSAGE", "id": f"t2-msg-{i}", "content": f"T2 Msg {i}"})

    # 1. Thread 1 messages (scoped to t1)
    res_t1 = client.get(
        f"/api/v-alpha/agent/{agent.id}/session/{session.id}/thread/{t1.id}/messages"
    )
    assert res_t1.status_code == 200
    data_t1 = res_t1.json()
    assert data_t1["total_bubbles"] == 30
    assert len(data_t1["messages"]) == 30
    assert data_t1["oldest_bubble_id"] == "t1-msg-0"
    assert data_t1["newest_bubble_id"] == "t1-msg-29"

    # 2. Thread 2 messages (scoped to t2)
    res_t2 = client.get(
        f"/api/v-alpha/agent/{agent.id}/session/{session.id}/thread/{t2.id}/messages"
    )
    assert res_t2.status_code == 200
    data_t2 = res_t2.json()
    assert data_t2["total_bubbles"] == 40
    assert len(data_t2["messages"]) == 40
    assert data_t2["oldest_bubble_id"] == "t2-msg-0"
    assert data_t2["newest_bubble_id"] == "t2-msg-39"

    # 3. Session messages: spans t1 + transition + t2 = 30 + 1 + 40 = 71 bubbles
    res_session = client.get(f"/api/v-alpha/agent/{agent.id}/session/{session.id}/messages")
    assert res_session.status_code == 200
    data_session = res_session.json()
    assert data_session["total_bubbles"] == 71
    # By default limit is 50, so tail 50 bubbles
    assert len(data_session["messages"]) <= 50
    assert data_session["has_more_before"] is True
    assert data_session["has_more_after"] is False
    assert data_session["newest_bubble_id"] == "t2-msg-39"

    # Backward pagination from oldest in current batch
    oldest_in_tail = data_session["oldest_bubble_id"]
    res_older = client.get(
        f"/api/v-alpha/agent/{agent.id}/session/{session.id}/messages?before_id={oldest_in_tail}&limit=50"
    )
    assert res_older.status_code == 200
    data_older = res_older.json()
    assert data_older["has_more_after"] is True
    assert data_older["oldest_bubble_id"] == "t1-msg-0"


def test_session_stream_replay_false(client: TestClient) -> None:
    store = get_harness_store()
    cfg = AgentConfig(
        inference=InferenceConfig(
            format=InferenceFormat.OPENAI,
            base_url="https://openrouter.ai/api/v1",
            api_key="test-api-key",
        ),
        model_name="openai/gpt-oss-120b",
    )
    agent = store.create_agent(config=cfg, name="test-agent")
    session = store.create_session(str(agent.id), name="test-session")
    t1 = session.get_open_thread()
    t1.append_event({"type": "USER_MESSAGE", "content": "Hello past"})

    # With replay=false, no past events are emitted
    res = client.get(
        f"/api/v-alpha/agent/{agent.id}/session/{session.id}/stream?follow=false&replay=false",
        headers={"Accept": "text/event-stream"},
    )
    assert res.status_code == 200
    assert res.text.strip() == ""

    # With replay=true (default), past events are emitted
    res_replay = client.get(
        f"/api/v-alpha/agent/{agent.id}/session/{session.id}/stream?follow=false",
        headers={"Accept": "text/event-stream"},
    )
    assert res_replay.status_code == 200
    assert "Hello past" in res_replay.text
