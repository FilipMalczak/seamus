"""Unit and integration tests for sandbox terminal streaming endpoints."""

import json
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from seamus.config.models import AgentConfig, InferenceConfig, InferenceFormat
from seamus.config.settings import SystemSettings, SystemSettingsStore, reset_system_settings_store
from seamus.config.template import ConfigTemplateStore, reset_config_template_store
from seamus.harness.runner import reset_runner_registry
from seamus.harness.sandbox import SeamusOpenSandboxBackend
from seamus.harness.store import HarnessStore, reset_harness_store
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


def test_terminal_info_endpoint(client: TestClient) -> None:
    """Test retrieving terminal information for an active session."""
    agent_res = client.post("/api/v-alpha/agents", json={"name": "terminal-agent"})
    assert agent_res.status_code == 201
    agent_data = agent_res.json()
    agent_id = agent_data["id"]

    session_res = client.post(f"/api/v-alpha/agent/{agent_id}/session", json={})
    assert session_res.status_code == 201
    session_id = session_res.json()["id"]

    info_res = client.get(f"/api/v-alpha/agent/{agent_id}/session/{session_id}/terminal/info")
    assert info_res.status_code == 200
    info = info_res.json()
    assert info["agent_id"] == agent_id
    assert info["session_id"] == session_id
    assert info["operational_dir"] == "/workspace"
    assert info["status"] == "ACTIVE"


def test_terminal_info_404_on_missing_session(client: TestClient) -> None:
    """Test that terminal info returns 404 for unknown agents or sessions."""
    res = client.get(
        "/api/v-alpha/agent/nonexistent-agent/session/00000000-0000-0000-0000-000000000000/terminal/info"
    )
    assert res.status_code == 404


def test_terminal_stream_empty_command(client: TestClient) -> None:
    """Test streaming an empty command exits cleanly with status 0."""
    agent = client.post("/api/v-alpha/agents", json={"name": "stream-agent"}).json()
    session = client.post(f"/api/v-alpha/agent/{agent['id']}/session", json={}).json()

    res = client.post(
        f"/api/v-alpha/agent/{agent['id']}/session/{session['id']}/terminal/stream",
        json={"command": "   ", "working_directory": "/workspace"},
    )
    assert res.status_code == 200
    assert "text/event-stream" in res.headers["content-type"]

    events = [
        json.loads(line.replace("data: ", ""))
        for line in res.text.strip().split("\n\n")
        if line.startswith("data: ")
    ]
    assert len(events) == 1
    assert events[0]["type"] == "exit"
    assert events[0]["exit_code"] == 0
    assert events[0]["working_directory"] == "/workspace"


def test_terminal_stream_execution_success(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test streaming execution capturing stdout and exit code via simulated sandbox execution."""
    agent = client.post("/api/v-alpha/agents", json={"name": "stream-agent-exec"}).json()
    session = client.post(f"/api/v-alpha/agent/{agent['id']}/session", json={}).json()

    # Create mock sandbox commands.run
    mock_sandbox = MagicMock()
    mock_run = MagicMock()

    class FakeMessage:
        def __init__(self, text: str) -> None:
            self.text = text

    class FakeExecution:
        def __init__(self) -> None:
            self.exit_code = 0
            self.logs = MagicMock(
                stdout=[FakeMessage("total 4"), FakeMessage("-rw-r--r-- file.txt")],
                stderr=[],
            )

    def fake_run(command: str, opts: object = None, handlers: object = None) -> FakeExecution:
        if handlers is not None:
            on_stdout = getattr(handlers, "on_stdout", None)
            if on_stdout:
                on_stdout(FakeMessage("total 4"))
                on_stdout(FakeMessage("-rw-r--r-- file.txt"))
                on_stdout(FakeMessage("__SEAMUS_CWD__=/workspace/subdir"))
        return FakeExecution()

    mock_run.side_effect = fake_run
    mock_sandbox.commands.run = mock_run

    # Inject mock into backend._sandbox
    orig_ensure = SeamusOpenSandboxBackend._ensure_sandbox

    def fake_ensure(self: SeamusOpenSandboxBackend) -> MagicMock:
        return mock_sandbox

    monkeypatch.setattr(SeamusOpenSandboxBackend, "_ensure_sandbox", fake_ensure)

    try:
        res = client.post(
            f"/api/v-alpha/agent/{agent['id']}/session/{session['id']}/terminal/stream",
            json={"command": "ls -la", "working_directory": "/workspace"},
        )
        assert res.status_code == 200

        events = [
            json.loads(line.replace("data: ", ""))
            for line in res.text.strip().split("\n\n")
            if line.startswith("data: ")
        ]

        stdout_events = [e for e in events if e["type"] == "stdout"]
        exit_events = [e for e in events if e["type"] == "exit"]

        assert len(stdout_events) == 2
        assert stdout_events[0]["data"] == "total 4"
        assert stdout_events[1]["data"] == "-rw-r--r-- file.txt"

        assert len(exit_events) == 1
        assert exit_events[0]["exit_code"] == 0
        assert exit_events[0]["working_directory"] == "/workspace/subdir"
    finally:
        monkeypatch.setattr(SeamusOpenSandboxBackend, "_ensure_sandbox", orig_ensure)


def test_terminal_stream_execution_error_exit(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test streaming execution capturing stderr and non-zero exit code."""
    agent = client.post("/api/v-alpha/agents", json={"name": "stream-agent-err"}).json()
    session = client.post(f"/api/v-alpha/agent/{agent['id']}/session", json={}).json()

    mock_sandbox = MagicMock()

    class FakeMessage:
        def __init__(self, text: str) -> None:
            self.text = text

    class FakeExecution:
        def __init__(self) -> None:
            self.exit_code = 2
            self.logs = MagicMock(
                stdout=[],
                stderr=[FakeMessage("cat: nonexistent: No such file or directory")],
            )

    def fake_run(command: str, opts: object = None, handlers: object = None) -> FakeExecution:
        if handlers is not None:
            on_stderr = getattr(handlers, "on_stderr", None)
            if on_stderr:
                on_stderr(FakeMessage("cat: nonexistent: No such file or directory"))
        return FakeExecution()

    mock_sandbox.commands.run.side_effect = fake_run

    monkeypatch.setattr(SeamusOpenSandboxBackend, "_ensure_sandbox", lambda self: mock_sandbox)

    res = client.post(
        f"/api/v-alpha/agent/{agent['id']}/session/{session['id']}/terminal/stream",
        json={"command": "cat nonexistent", "working_directory": "/workspace"},
    )
    assert res.status_code == 200

    events = [
        json.loads(line.replace("data: ", ""))
        for line in res.text.strip().split("\n\n")
        if line.startswith("data: ")
    ]

    stderr_events = [e for e in events if e["type"] == "stderr"]
    exit_events = [e for e in events if e["type"] == "exit"]

    assert len(stderr_events) == 1
    assert "No such file or directory" in stderr_events[0]["data"]
    assert len(exit_events) == 1
    assert exit_events[0]["exit_code"] == 2
