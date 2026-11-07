"""Integration tests for session-level SSE stream endpoint."""

import json

import pytest
from fastapi.testclient import TestClient

from seamus.config.models import AgentConfig, InferenceConfig, InferenceFormat
from seamus.config.settings import (
    SystemSettings,
    SystemSettingsStore,
    reset_system_settings_store,
)
from seamus.config.template import ConfigTemplateStore, reset_config_template_store
from seamus.domain.entities import SessionStatus
from seamus.harness.runner import reset_runner_registry
from seamus.harness.store import HarnessStore, get_harness_store, reset_harness_store
from seamus.server.app import create_app


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


def test_session_stream_replays_multi_thread_events_with_delimiters(client: TestClient) -> None:
    """Test that stream_session concatenates events across threads with transition delimiters."""
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

    # Thread 1: initial open thread
    t1 = session.get_open_thread()
    t1.append_event({"type": "USER_MESSAGE", "content": "Hello in thread 1"})
    t1.append_event({"type": "TEXT_CHUNK", "delta": "Reply in thread 1"})

    # Thread 2: create new thread (closing thread 1)
    t2 = store.create_thread(str(agent.id), str(session.id), name="second-thread")
    t2.append_event({"type": "USER_MESSAGE", "content": "Hello in thread 2"})
    t2.append_event({"type": "TEXT_CHUNK", "delta": "Reply in thread 2"})

    response = client.get(
        f"/api/v-alpha/agent/{agent.id}/session/{session.id}/stream?follow=false",
        headers={"Accept": "text/event-stream"},
    )
    assert response.status_code == 200

    # Parse SSE data lines
    events = []
    for line in response.text.split("\n"):
        line = line.strip()
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))

    assert len(events) == 6
    # 1. Delimiter for Thread 1
    assert events[0]["type"] == "THREAD_TRANSITION"
    assert events[0]["thread_id"] == str(t1.id)
    assert events[0]["is_first"] is True
    # 2. Thread 1 events
    assert events[1]["content"] == "Hello in thread 1"
    assert events[2]["delta"] == "Reply in thread 1"
    # 3. Delimiter for Thread 2
    assert events[3]["type"] == "THREAD_TRANSITION"
    assert events[3]["thread_id"] == str(t2.id)
    assert events[3]["is_first"] is False
    # 4. Thread 2 events
    assert events[4]["content"] == "Hello in thread 2"
    assert events[5]["delta"] == "Reply in thread 2"


def test_session_stream_terminal_session_closes_immediately(client: TestClient) -> None:
    """Test that stream_session closes immediately if session is not active."""
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
    session.status = SessionStatus.KILLED

    t1 = session.get_open_thread()
    t1.append_event({"type": "USER_MESSAGE", "content": "Prior message"})

    response = client.get(
        f"/api/v-alpha/agent/{agent.id}/session/{session.id}/stream?follow=true",
        headers={"Accept": "text/event-stream"},
    )
    assert response.status_code == 200

    events = [
        json.loads(line[6:])
        for line in response.text.split("\n")
        if line.strip().startswith("data: ")
    ]
    assert len(events) == 2
    assert events[0]["type"] == "THREAD_TRANSITION"
    assert events[1]["content"] == "Prior message"
