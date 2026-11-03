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
        "write_todos",
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
        elif tool.name in {"task", "write_todos"}:
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
    assert "todos" in data
    assert isinstance(data["todos"], list)
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


def test_inspect_extracts_todos_from_workspace() -> None:
    """Verify that todos saved to thread state are extracted into inspect report."""
    store = HarnessStore()
    reset_harness_store(store)
    ws_mgr = get_workspace_manager()

    config = AgentConfig(
        inference=InferenceConfig(
            format=InferenceFormat.OPENAI,
            base_url="https://openrouter.ai/api/v1",
            api_key="sk-secret-key-12345",
        ),
        model_name="openai/gpt-oss-120b",
    )
    agent = store.create_agent(config=config, name="todos-inspect-agent")
    session = list(agent.sessions.values())[0]
    thread = session.get_open_thread()

    raw_todos = [
        {"content": "Step 1: Write tests", "status": "completed"},
        {"content": "Step 2: Implement feature", "status": "in_progress"},
        {"content": "Step 3: Document changes", "status": "pending"},
    ]
    ws_mgr.save_thread_todos(agent.id, session.id, thread.id, raw_todos)

    report = build_agent_inspect_report(str(agent.id), str(session.id), str(thread.id))
    assert len(report.todos) == 3
    assert report.todos[0].content == "Step 1: Write tests"
    assert report.todos[0].status == "completed"
    assert report.todos[1].content == "Step 2: Implement feature"
    assert report.todos[1].status == "in_progress"
    assert report.todos[2].content == "Step 3: Document changes"
    assert report.todos[2].status == "pending"


def test_extract_thread_todos_from_jsonplus_checkpoints() -> None:
    """Verify that checkpoint blobs encoded with JsonPlusSerializer (msgpack) decode cleanly."""
    import base64

    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

    from seamus.harness.inspector import extract_thread_messages, extract_thread_todos

    store = HarnessStore()
    reset_harness_store(store)
    ws_mgr = get_workspace_manager()

    config = AgentConfig(
        inference=InferenceConfig(
            format=InferenceFormat.OPENAI,
            base_url="https://openrouter.ai/api/v1",
            api_key="sk-secret-key-12345",
        ),
        model_name="openai/gpt-oss-120b",
    )
    agent = store.create_agent(config=config, name="jsonplus-checkpoint-agent")
    session = list(agent.sessions.values())[0]
    thread = session.get_open_thread()

    serializer = JsonPlusSerializer()
    checkpoint_state = {
        "channel_values": {
            "todos": [
                {"content": "Fix bug", "status": "completed"},
                {"content": "Write docs", "status": "in_progress"},
            ],
            "messages": [
                {"role": "user", "content": "Start work"},
                {"role": "assistant", "content": "Working on it"},
            ],
        }
    }
    val_type, raw_bytes = serializer.dumps_typed(checkpoint_state)
    b64_blob = base64.b64encode(raw_bytes).decode("ascii")

    cp_dump = {
        "storage": {
            str(thread.id): {
                "root": {
                    "cp-1": [
                        [val_type, b64_blob],
                        ["json", ""],
                        None,
                    ]
                }
            }
        }
    }
    ws_mgr.save_thread_checkpoints(agent.id, session.id, thread.id, cp_dump)

    # 1. extract_thread_todos must succeed and not raise unpickling error
    todos = extract_thread_todos(agent.id, session.id, thread)
    assert len(todos) == 2
    assert todos[0].content == "Fix bug"
    assert todos[0].status == "completed"
    assert todos[1].content == "Write docs"
    assert todos[1].status == "in_progress"

    # 2. extract_thread_messages must succeed and not raise unpickling error
    messages, cp_count = extract_thread_messages(agent.id, session.id, thread)
    assert cp_count == 1
    assert len(messages) == 2
    assert messages[0].role == "user"
    assert messages[0].content == "Start work"
    assert messages[1].role == "assistant"
    assert messages[1].content == "Working on it"


def test_default_tools_inspect_info_includes_todos_schema() -> None:
    """Verify that default tools inspect list contains write_todos with schemas."""
    from seamus.harness.inspector import get_default_tools_inspect_info

    tools = get_default_tools_inspect_info()
    write_todos_tool = next((t for t in tools if t.name == "write_todos"), None)
    assert write_todos_tool is not None
    assert write_todos_tool.backend == "harness"
    assert "todos" in write_todos_tool.parameters.get("properties", {})
