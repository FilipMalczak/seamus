"""Tests for Logfire telemetry setup, hierarchical spans, and FastAPI instrumentation."""

import asyncio
import os
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import logfire
import pytest
from fastapi.testclient import TestClient
from logfire.testing import TestExporter
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

from seamus.config.models import AgentConfig, InferenceConfig
from seamus.domain.entities import Agent
from seamus.harness.runner import SessionAgentRunner
from seamus.harness.store import HarnessStore
from seamus.server.app import create_app
from seamus.telemetry import (
    _scrub_callback,
    get_logfire_service_name,
    is_logfire_enabled,
    setup_telemetry,
)


class MockLangGraphAgent:
    """Mock LangGraph agent for testing execution traces."""

    def clone(self) -> "MockLangGraphAgent":
        return self

    async def run(self, input_data: Any) -> AsyncGenerator[Any, None]:
        await asyncio.sleep(0.01)
        yield {"type": "RUN_STARTED"}
        yield {"type": "RUN_FINISHED"}


@pytest.fixture
def logfire_test_exporter() -> TestExporter:
    """Configure Logfire with a TestExporter for inspecting captured spans."""
    exporter = TestExporter()
    logfire.configure(
        send_to_logfire=False,
        console=False,
        scrubbing=logfire.ScrubbingOptions(callback=_scrub_callback),
        additional_span_processors=[SimpleSpanProcessor(exporter)],
        inspect_arguments=False,
    )
    return exporter


def test_setup_telemetry() -> None:
    """Verify setup_telemetry configures OTel environment variables."""
    setup_telemetry(send_to_logfire=False)
    assert os.environ.get("LANGSMITH_OTEL_ENABLED") == "true"
    assert os.environ.get("LANGSMITH_OTEL_ONLY") == "true"
    assert os.environ.get("LANGSMITH_TRACING") == "true"


def test_setup_telemetry_loads_env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify setup_telemetry loads environment variables from a custom or found .env file."""
    monkeypatch.delenv("LOGFIRE_SERVICE_NAME", raising=False)
    monkeypatch.delenv("TEST_ENV_VAR", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("LOGFIRE_SERVICE_NAME=custom-seamus-test\nTEST_ENV_VAR=loaded_ok\n")

    setup_telemetry(send_to_logfire=False, force_reconfigure=True, env_file=env_file)
    assert os.environ.get("TEST_ENV_VAR") == "loaded_ok"
    assert os.environ.get("LOGFIRE_SERVICE_NAME") == "custom-seamus-test"


def test_is_logfire_enabled_and_service_name(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify is_logfire_enabled evaluates LOGFIRE_SEND_TO_LOGFIRE and LOGFIRE_TOKEN properly."""
    monkeypatch.setenv("LOGFIRE_SERVICE_NAME", "my-test-service")
    assert get_logfire_service_name() == "my-test-service"

    # Explicit send_to_logfire=False
    setup_telemetry(send_to_logfire=False, force_reconfigure=True)
    assert not is_logfire_enabled()

    # Explicit send_to_logfire=True
    setup_telemetry(send_to_logfire=True, force_reconfigure=True)
    assert is_logfire_enabled()

    # Via LOGFIRE_SEND_TO_LOGFIRE=false
    monkeypatch.setenv("LOGFIRE_SEND_TO_LOGFIRE", "false")
    monkeypatch.setenv("LOGFIRE_TOKEN", "some-token")
    setup_telemetry(force_reconfigure=True)
    assert not is_logfire_enabled()

    # Via LOGFIRE_SEND_TO_LOGFIRE=if-token-present with token
    monkeypatch.setenv("LOGFIRE_SEND_TO_LOGFIRE", "if-token-present")
    monkeypatch.setenv("LOGFIRE_TOKEN", "valid-token")
    setup_telemetry(force_reconfigure=True)
    assert is_logfire_enabled()

    # Via LOGFIRE_SEND_TO_LOGFIRE=if-token-present without token
    monkeypatch.setenv("LOGFIRE_TOKEN", "")
    logfire.DEFAULT_LOGFIRE_INSTANCE.config.token = None
    setup_telemetry(force_reconfigure=True)
    assert not is_logfire_enabled()


def test_env_template_exists_and_contains_logfire_vars() -> None:
    """Verify that .env.template exists and specifies Logfire and inference configurations."""
    template_path = Path(__file__).resolve().parents[1] / ".env.template"
    assert template_path.exists()
    content = template_path.read_text()
    assert "LOGFIRE_TOKEN=" in content
    assert "LOGFIRE_SERVICE_NAME=" in content
    assert "OPENROUTER_API_KEY=" in content


async def test_runner_hierarchical_spans(logfire_test_exporter: TestExporter) -> None:
    """Verify that agent, session, and thread execution generates a 3-level hierarchical trace."""
    config = AgentConfig(
        inference=InferenceConfig(
            base_url="https://api.openai.com/v1",
            api_key="sk-test",
        ),
        model_name="gpt-4o",
    )
    agent = Agent(name="agent-alpha", config=config)
    session = agent.create_session(name="session-beta")
    thread = session.get_open_thread()
    thread.name = "thread-gamma"

    runner = SessionAgentRunner(
        session=session,
        agent=MockLangGraphAgent(),
        agent_entity=agent,
    )

    await runner.dispatch_user_input("Hello, test!")
    assert runner._active_task is not None
    await runner._active_task

    spans = logfire_test_exporter.exported_spans_as_dict()
    span_by_name = {s["name"]: s for s in spans}

    assert "thread thread-gamma" in span_by_name
    assert "session session-beta" in span_by_name
    assert "agent agent-alpha" in span_by_name

    thread_span = span_by_name["thread thread-gamma"]
    session_span = span_by_name["session session-beta"]
    agent_span = span_by_name["agent agent-alpha"]

    # Verify attributes
    assert thread_span["attributes"]["thread_id"] == str(thread.id)
    assert thread_span["attributes"]["thread_name"] == "thread-gamma"
    assert thread_span["attributes"]["session_id"] == str(session.id)
    assert thread_span["attributes"]["agent_id"] == str(agent.id)

    assert session_span["attributes"]["session_id"] == str(session.id)
    assert session_span["attributes"]["session_name"] == "session-beta"
    assert session_span["attributes"]["agent_id"] == str(agent.id)

    assert agent_span["attributes"]["agent_id"] == str(agent.id)
    assert agent_span["attributes"]["agent_name"] == "agent-alpha"
    assert agent_span["attributes"]["model"] == "gpt-4o"

    # Verify hierarchy: thread is child of session, session is child of agent
    assert thread_span["parent"]["span_id"] == session_span["context"]["span_id"]
    assert session_span["parent"]["span_id"] == agent_span["context"]["span_id"]
    assert thread_span["context"]["trace_id"] == agent_span["context"]["trace_id"]


def test_store_entity_lifecycle_spans(logfire_test_exporter: TestExporter) -> None:
    """Verify that store lifecycle operations emit structured spans."""
    store = HarnessStore()
    config = AgentConfig(
        inference=InferenceConfig(
            base_url="https://api.openai.com/v1",
            api_key="sk-test",
        ),
        model_name="gpt-4o",
    )

    agent = store.create_agent(config=config, name="store-agent")
    session = store.create_session(agent_identifier=str(agent.id), name="store-session")
    store.create_thread(
        agent_identifier=str(agent.id),
        session_identifier=str(session.id),
        name="store-thread",
    )

    spans = logfire_test_exporter.exported_spans_as_dict()
    names = [s["name"] for s in spans]

    assert "agent store-agent" in names
    assert "session store-session" in names
    assert "thread store-thread" in names


def test_fastapi_request_instrumentation(logfire_test_exporter: TestExporter) -> None:
    """Verify that FastAPI requests produce Logfire spans while /health is excluded."""
    app = create_app()
    client = TestClient(app)

    # Health check should NOT generate trace spans
    health_response = client.get("/health")
    assert health_response.status_code == 200

    spans_after_health = logfire_test_exporter.exported_spans_as_dict()
    health_spans = [
        s
        for s in spans_after_health
        if "/health" in s.get("name", "")
        or s.get("attributes", {}).get("http.target") == "/health"
        or "health" in str(s.get("attributes", {}))
    ]
    assert len(health_spans) == 0

    # API endpoints SHOULD generate trace spans
    api_response = client.get("/api/v-alpha/system/info")
    assert api_response.status_code == 200

    spans_after_api = logfire_test_exporter.exported_spans_as_dict()
    api_spans = [
        s
        for s in spans_after_api
        if "/api/v-alpha" in s.get("name", "")
        or "/system/info" in str(s.get("attributes", {}))
        or "FastAPI" in s.get("name", "")
    ]
    assert len(api_spans) > 0


async def test_langgraph_multi_turn_no_duplicate_user_message(
    logfire_test_exporter: TestExporter,
) -> None:
    """Verify multi-turn SeamusLangGraphAgent runs do not duplicate the leading user message."""
    import json

    from ag_ui.core.types import RunAgentInput, TextInputContent, UserMessage
    from langchain_core.messages import AIMessage
    from langchain_core.tracers.langchain import wait_for_all_tracers
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.graph import MessagesState, StateGraph

    from seamus.harness.runner import SeamusLangGraphAgent

    setup_telemetry(send_to_logfire=False)

    async def call_model(state: MessagesState) -> dict[str, Any]:
        turn = len(state["messages"])
        return {"messages": [AIMessage(id=f"ai-{turn}", content=f"Reply {turn}")]}

    builder = StateGraph(MessagesState)
    builder.add_node("model", call_model)
    builder.set_entry_point("model")
    graph = builder.compile(checkpointer=MemorySaver())

    agent = SeamusLangGraphAgent(name="test-agent", graph=graph)

    inp1 = RunAgentInput(
        thread_id="thread-1",
        run_id="run-1",
        messages=[UserMessage(id="u1", role="user", content=[TextInputContent(text="hey there")])],
    )
    async for _ in agent.run(inp1):
        pass
    wait_for_all_tracers()
    logfire_test_exporter.clear()

    inp2 = RunAgentInput(
        thread_id="thread-1",
        run_id="run-2",
        messages=[
            UserMessage(
                id="u2",
                role="user",
                content=[TextInputContent(text="what can you help me with>")],
            )
        ],
    )
    async for _ in agent.run(inp2):
        pass
    wait_for_all_tracers()

    spans = logfire_test_exporter.exported_spans_as_dict()
    lg_spans = [s for s in spans if s["name"] == "LangGraph"]
    assert len(lg_spans) == 1
    raw_all_msgs = lg_spans[0]["attributes"].get("all_messages_events")
    assert isinstance(raw_all_msgs, str)
    all_msgs = json.loads(raw_all_msgs)

    assert len(all_msgs) == 4
    assert [m["role"] for m in all_msgs] == ["user", "assistant", "user", "assistant"]
    assert all_msgs[0]["content"] == [{"type": "text", "text": "hey there"}]
    assert all_msgs[2]["content"] == [{"type": "text", "text": "what can you help me with>"}]
