"""Tests for the DeepAgent inspector service and endpoint."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from seamus.config.models import AgentConfig, InferenceConfig, InferenceFormat
from seamus.config.template import ConfigTemplateStore, reset_config_template_store
from seamus.harness.inspector import (
    build_agent_inspect_report,
    get_default_tools_inspect_info,
)
from seamus.harness.runner import reset_runner_registry
from seamus.harness.store import HarnessStore, reset_harness_store
from seamus.persistence import get_workspace_manager
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
        system_prompt="You are a specialized code reviewer.",
    )
    reset_config_template_store(ConfigTemplateStore(initial_template=template))
    reset_harness_store(HarnessStore())
    reset_runner_registry()


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    return TestClient(app)


def test_get_default_tools_inspect_info() -> None:
    """Verify that default tools are extracted with expected tool names and backend annotations."""
    tools = get_default_tools_inspect_info()
    assert len(tools) >= 8
    tool_names = {t.name for t in tools}
    expected_tools = [
        "ls",
        "read_file",
        "write_file",
        "edit_file",
        "delete",
        "glob",
        "grep",
        "execute",
        "task",
    ]
    for expected in expected_tools:
        assert expected in tool_names

    # Filesystem and execute tools should target opensandbox
    sandbox_tools = {
        "ls",
        "read_file",
        "write_file",
        "edit_file",
        "delete",
        "glob",
        "grep",
        "execute",
    }
    for tool in tools:
        if tool.name in sandbox_tools:
            assert tool.backend == "opensandbox"
        elif tool.name == "task":
            assert tool.backend == "harness"


def test_build_agent_inspect_report(tmp_path: pytest.MonkeyPatch) -> None:
    """Verify build_agent_inspect_report assembles identity, prompt, and git state."""
    store = HarnessStore()
    reset_harness_store(store)

    config = AgentConfig(
        inference=InferenceConfig(
            format=InferenceFormat.OPENAI,
            base_url="https://openrouter.ai/api/v1",
            api_key="sk-secret-key-12345",
        ),
        model_name="openai/gpt-oss-120b",
        system_prompt="Always write tests before code.",
    )

    agent = store.create_agent(config=config, name="agent-inspector-test")
    session = list(agent.sessions.values())[0]

    report = build_agent_inspect_report(str(agent.id), str(session.id))

    assert report.agent_id == agent.id
    assert report.agent_name == "agent-inspector-test"
    assert report.session_id == session.id
    assert report.status.value == "AWAITING_USER"

    # Verify sensitive inference API key is NOT exposed
    assert report.inference.model_name == "openai/gpt-oss-120b"
    assert report.inference.base_url == "https://openrouter.ai/api/v1"
    assert report.inference.api_key_configured is True

    # Verify prompt decomposition
    assert "Always write tests before code." in report.prompts.custom
    assert "/workspace" in report.prompts.scaffold
    assert "<identity>" in report.prompts.scaffold
    assert "<custom_instructions>" in report.prompts.composite
    assert "Always write tests before code." in report.prompts.composite
    assert "<operating_environment>" in report.prompts.composite

    # Verify tools
    assert len(report.tools) >= 8
    assert any(t.name == "execute" for t in report.tools)
    assert any(t.name == "read_file" for t in report.tools)

    # Verify git branch
    assert report.git.branch == f"session/{session.id}"
    assert report.git.repo_name == f"agent-{agent.id}"


def test_inspect_endpoint_http(client: TestClient) -> None:
    """Verify GET /api/v-alpha/agent/{agent}/session/{session}/inspect endpoint via HTTP."""
    # 1. Create an agent
    create_res = client.post(
        "/api/v-alpha/agents",
        json={"name": "inspect-http-agent"},
    )
    assert create_res.status_code == 201
    agent_id = create_res.json()["id"]

    agent_detail = client.get(f"/api/v-alpha/agent/{agent_id}").json()
    session_id = agent_detail["sessions"][0]["id"]

    # 2. Inspect session
    inspect_res = client.get(f"/api/v-alpha/agent/{agent_id}/session/{session_id}/inspect")
    assert inspect_res.status_code == 200
    data = inspect_res.json()

    assert data["agent_id"] == agent_id
    assert data["session_id"] == session_id
    assert data["status"] == "AWAITING_USER"
    assert "inference" in data
    assert "prompts" in data
    assert "tools" in data
    assert "git" in data
    assert "history" in data
    assert "workspace" in data
    assert data["git"]["branch"] == f"session/{session_id}"


def test_inspect_endpoint_not_found(client: TestClient) -> None:
    """Verify 404 response for unknown agent or session."""
    random_id = str(uuid4())
    res = client.get(f"/api/v-alpha/agent/{random_id}/session/{random_id}/inspect")
    assert res.status_code == 404


def test_inspect_workspace_files(client: TestClient) -> None:
    """Verify that files created in session data/ directory are listed in inspect report."""
    create_res = client.post(
        "/api/v-alpha/agents",
        json={"name": "files-inspect-agent"},
    )
    agent_id = create_res.json()["id"]
    agent_detail = client.get(f"/api/v-alpha/agent/{agent_id}").json()
    session_id = agent_detail["sessions"][0]["id"]

    # Write a test file in session data/ directory
    ws_mgr = get_workspace_manager()
    from uuid import UUID

    data_dir = ws_mgr.get_session_data_dir(UUID(agent_id), UUID(session_id))
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "output.txt").write_text("Hello from sandbox", encoding="utf-8")
    sub = data_dir / "src"
    sub.mkdir(exist_ok=True)
    (sub / "main.py").write_text("print('hello')", encoding="utf-8")

    res = client.get(f"/api/v-alpha/agent/{agent_id}/session/{session_id}/inspect")
    assert res.status_code == 200
    data = res.json()
    files = data["workspace"]["files"]
    assert "output.txt" in files
    assert "src/main.py" in files
