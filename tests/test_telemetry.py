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
from seamus.telemetry import _scrub_callback, setup_telemetry


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


def test_setup_telemetry_loads_env_file(tmp_path: Path) -> None:
    """Verify setup_telemetry loads environment variables from a custom or found .env file."""
    env_file = tmp_path / ".env"
    env_file.write_text("LOGFIRE_SERVICE_NAME=custom-seamus-test\nTEST_ENV_VAR=loaded_ok\n")

    setup_telemetry(send_to_logfire=False, force_reconfigure=True, env_file=env_file)
    assert os.environ.get("TEST_ENV_VAR") == "loaded_ok"
    assert os.environ.get("LOGFIRE_SERVICE_NAME") == "custom-seamus-test"


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
    """Verify that FastAPI requests produce Logfire spans."""
    app = create_app()
    client = TestClient(app)

    response = client.get("/health")
    assert response.status_code == 200

    spans = logfire_test_exporter.exported_spans_as_dict()
    http_spans = [
        s
        for s in spans
        if "/health" in s.get("name", "")
        or s.get("attributes", {}).get("http.target") == "/health"
        or "health" in str(s.get("attributes", {}))
    ]
    assert len(http_spans) > 0
