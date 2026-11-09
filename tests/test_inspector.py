"""Tests for the DeepAgent inspector service and endpoint."""

from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from seamus.config.models import (
    AgentConfig,
    InferenceConfig,
    InferenceFormat,
    SkillsImplementation,
    TodoImplementation,
)
from seamus.config.template import ConfigTemplateStore, reset_config_template_store
from seamus.harness.inspector import (
    build_agent_inspect_report,
    get_default_tools_inspect_info,
)
from seamus.harness.runner import reset_runner_registry
from seamus.harness.store import HarnessStore, get_harness_store, reset_harness_store
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
        todo_implementation=TodoImplementation.DEEPAGENTS,
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
        todo_implementation=TodoImplementation.DEEPAGENTS,
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


def test_inspector_todo_implementation_toggle() -> None:
    """Verify inspector tools and todos reflect session todo_implementation setting."""
    store = HarnessStore()
    reset_harness_store(store)

    config_none = AgentConfig(
        inference=InferenceConfig(api_key="key"),
        model_name="test-model",
        todo_implementation=TodoImplementation.NONE,
    )
    agent = store.create_agent(config=config_none, name="toggle-agent")
    session = list(agent.sessions.values())[0]

    report_none = build_agent_inspect_report(str(agent.id), str(session.id))
    assert report_none.todo_implementation == TodoImplementation.NONE
    assert not any(t.name == "write_todos" for t in report_none.tools)
    assert len(report_none.todos) == 0

    # Update session to deepagents and reload runner
    session.config.todo_implementation = TodoImplementation.DEEPAGENTS
    reset_runner_registry()
    report_deep = build_agent_inspect_report(str(agent.id), str(session.id))
    assert report_deep.todo_implementation == TodoImplementation.DEEPAGENTS
    assert any(t.name == "write_todos" for t in report_deep.tools)


def test_inspector_skills_discovery_and_project_rules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify inspector extracts skills across precedence layers and project_rules."""
    from seamus.config.settings import (
        SystemSettings,
        SystemSettingsStore,
        reset_system_settings_store,
    )

    sys_skills_dir = tmp_path / "sys_skills"
    sys_skill_a = sys_skills_dir / "skill-a"
    sys_skill_a.mkdir(parents=True)
    (sys_skill_a / "SKILL.md").write_text(
        "---\nname: skill-a\ndescription: System skill A { key: value }\n---\nSystem A body",
        encoding="utf-8",
    )

    sys_skill_b = sys_skills_dir / "skill-b"
    sys_skill_b.mkdir(parents=True)
    (sys_skill_b / "SKILL.md").write_text(
        "---\nname: skill-b\ndescription: System skill B\n---\nSystem B body",
        encoding="utf-8",
    )

    reset_system_settings_store(
        SystemSettingsStore(
            initial_settings=SystemSettings(skill_directories=[str(sys_skills_dir)])
        )
    )

    store = HarnessStore()
    reset_harness_store(store)
    ws_mgr = get_workspace_manager()

    config = AgentConfig(
        inference=InferenceConfig(api_key="key"),
        model_name="test-model",
        skills_implementation=SkillsImplementation.DEEPAGENTS,
    )
    agent = store.create_agent(config=config, name="skills-inspect-agent")
    session = list(agent.sessions.values())[0]

    data_dir = ws_mgr.get_session_data_dir(agent.id, session.id)
    ws_skill_a = data_dir / "skills" / "skill-a"
    ws_skill_a.mkdir(parents=True, exist_ok=True)
    (ws_skill_a / "SKILL.md").write_text(
        "---\nname: skill-a\ndescription: Workspace override skill A\n---\nWorkspace A body",
        encoding="utf-8",
    )

    report = build_agent_inspect_report(str(agent.id), str(session.id))
    assert report.skills_implementation == SkillsImplementation.DEEPAGENTS
    assert "## Skills System" in report.prompts.composite
    assert "## Skills System" in report.prompts.scaffold
    assert "write_todos" in report.prompts.composite
    assert "write_todos" in report.prompts.scaffold

    # Report includes bundled platform skills (artifacts, a2ui_components) plus the test skills
    assert len(report.skills) == 5
    assert any(s.name == "artifacts" and s.origin_layer == "Bundled" for s in report.skills)
    assert any(s.name == "a2ui_components" and s.origin_layer == "Bundled" for s in report.skills)

    # Workspace skill-a is active (mounted skill -> host_path is None)
    active_ws_a = next(s for s in report.skills if s.name == "skill-a" and s.active)
    assert active_ws_a.sandbox_path == "/workspace/skills/skill-a/SKILL.md"
    assert active_ws_a.host_path is None
    assert active_ws_a.content == "Workspace A body"

    # System skill-a is shadowed and includes host_path
    shadowed_a = [s for s in report.skills if s.name == "skill-a" and not s.active]
    assert len(shadowed_a) == 1
    assert shadowed_a[0].sandbox_path == "/skills/system/0/skill-a/SKILL.md"
    assert shadowed_a[0].host_path == str(sys_skill_a / "SKILL.md")
    assert "key: value" in shadowed_a[0].description

    # System skill-b is active and includes host_path
    active_b = [s for s in report.skills if s.name == "skill-b" and s.active]
    assert len(active_b) == 1
    assert active_b[0].sandbox_path == "/skills/system/0/skill-b/SKILL.md"
    assert active_b[0].host_path == str(sys_skill_b / "SKILL.md")

    # When implementations are NONE, skills list is empty and middleware prompt sections are omitted
    session.config.skills_implementation = SkillsImplementation.NONE
    session.config.todo_implementation = TodoImplementation.NONE
    reset_runner_registry()
    report_none = build_agent_inspect_report(str(agent.id), str(session.id))
    assert report_none.skills_implementation == SkillsImplementation.NONE
    assert report_none.skills == []
    assert "## Skills System" not in report_none.prompts.composite
    assert "write_todos" not in report_none.prompts.composite


def test_inspector_and_backend_mounted_project_skills_precedence(tmp_path: Path) -> None:
    """Verify mounted project skills discovery, sandbox sources, and precedence hierarchy."""
    from seamus.config.models import ExternalRepositoryConfig
    from seamus.harness.inspector import extract_session_skills
    from seamus.harness.sandbox import SandboxSettings, SeamusOpenSandboxBackend
    from seamus.persistence import get_external_repo_manager

    store = get_harness_store()
    config = AgentConfig(
        inference=InferenceConfig(api_key="key"),
        model_name="test-model",
        skills_implementation=SkillsImplementation.DEEPAGENTS,
    )
    agent = store.create_agent(config=config, name="repo-skills-agent")
    session = list(agent.sessions.values())[0]

    ws_mgr = get_workspace_manager()
    ext_mgr = get_external_repo_manager()

    data_dir = ws_mgr.get_session_data_dir(agent.id, session.id)
    projects_dir = ext_mgr.get_session_projects_dir(agent.id, session.id)

    # 1. Workspace defines "shared-skill"
    ws_skills_dir = data_dir / "skills" / "shared-skill"
    ws_skills_dir.mkdir(parents=True)
    (ws_skills_dir / "SKILL.md").write_text(
        "---\nname: shared-skill\ndescription: Workspace version\n---\nWorkspace body\n",
        encoding="utf-8",
    )

    # 2. Project Alpha (first in config) defines "shared-skill" and "alpha-skill"
    alpha_dir = projects_dir / "repo-alpha"
    alpha_shared = alpha_dir / "skills" / "shared-skill"
    alpha_shared.mkdir(parents=True)
    (alpha_shared / "SKILL.md").write_text(
        "---\nname: shared-skill\ndescription: Alpha version\n---\nAlpha body\n",
        encoding="utf-8",
    )
    alpha_unique = alpha_dir / ".skills" / "alpha-unique"
    alpha_unique.mkdir(parents=True)
    (alpha_unique / "SKILL.md").write_text(
        "---\nname: alpha-unique\ndescription: Alpha unique\n---\nAlpha unique body\n",
        encoding="utf-8",
    )

    # 3. Project Beta (second in config) defines "shared-skill", "alpha-unique", and "beta-unique"
    beta_dir = projects_dir / "repo-beta"
    beta_shared = beta_dir / "skills" / "shared-skill"
    beta_shared.mkdir(parents=True)
    (beta_shared / "SKILL.md").write_text(
        "---\nname: shared-skill\ndescription: Beta version\n---\nBeta body\n",
        encoding="utf-8",
    )
    beta_colliding = beta_dir / "skills" / "alpha-unique"
    beta_colliding.mkdir(parents=True)
    (beta_colliding / "SKILL.md").write_text(
        "---\nname: alpha-unique\ndescription: Beta overriding attempt\n---\nBeta colliding body\n",
        encoding="utf-8",
    )
    beta_unique = beta_dir / "skills" / "beta-unique"
    beta_unique.mkdir(parents=True)
    (beta_unique / "SKILL.md").write_text(
        "---\nname: beta-unique\ndescription: Beta unique\n---\nBeta unique body\n",
        encoding="utf-8",
    )

    repos = [
        ExternalRepositoryConfig(
            id="alpha", url="https://github.com/org/repo-alpha.git", branch="main"
        ),
        ExternalRepositoryConfig(
            id="beta", url="https://github.com/org/repo-beta.git", branch="main"
        ),
    ]
    session.config.repositories = repos

    # 4. Test extract_session_skills (Inspector discovery order: first-seen wins)
    discovered = extract_session_skills(
        agent.id,
        session.id,
        SkillsImplementation.DEEPAGENTS,
        repositories=repos,
    )

    # shared-skill: Workspace is active, Alpha and Beta are shadowed
    shared_matches = [s for s in discovered if s.name == "shared-skill"]
    assert len(shared_matches) == 3
    assert shared_matches[0].origin_layer == "Session (skills)"
    assert shared_matches[0].active is True
    assert shared_matches[1].origin_layer == "Project repo-alpha"
    assert shared_matches[1].active is False
    assert shared_matches[2].origin_layer == "Project repo-beta"
    assert shared_matches[2].active is False

    # alpha-unique: Project Alpha active, Project Beta shadowed (Alpha > Beta)
    alpha_matches = [s for s in discovered if s.name == "alpha-unique"]
    assert len(alpha_matches) == 2
    assert alpha_matches[0].origin_layer == "Project repo-alpha (.skills)"
    assert alpha_matches[0].active is True
    assert alpha_matches[1].origin_layer == "Project repo-beta"
    assert alpha_matches[1].active is False

    # beta-unique: Project Beta is active
    beta_matches = [s for s in discovered if s.name == "beta-unique"]
    assert len(beta_matches) == 1
    assert beta_matches[0].origin_layer == "Project repo-beta"
    assert beta_matches[0].active is True

    # 5. Test get_skill_sources (DeepAgents order: last-one-wins)
    backend = SeamusOpenSandboxBackend(
        agent_id=agent.id,
        session_id=session.id,
        data_dir=data_dir,
        artifacts_dir=ws_mgr.get_session_artifacts_dir(agent.id, session.id),
        settings=SandboxSettings(workdir="/workspace"),
        skill_directories=[],
        repositories=repos,
    )
    sources = backend.get_skill_sources()
    source_paths = [s[0] for s in sources]

    # Precedence order in DeepAgents (later in list overrides earlier):
    # projects[last] (.skills then skills), projects[0] (.skills then skills), workspace, bundled
    idx_beta_dot = source_paths.index("/projects/repo-beta/.skills")
    idx_beta_plain = source_paths.index("/projects/repo-beta/skills")
    idx_alpha_dot = source_paths.index("/projects/repo-alpha/.skills")
    idx_alpha_plain = source_paths.index("/projects/repo-alpha/skills")
    idx_ws_dot = source_paths.index("/workspace/.skills")
    idx_ws_plain = source_paths.index("/workspace/skills")
    idx_bundled = source_paths.index("/skills/bundled")

    # repo-beta comes before repo-alpha (so repo-alpha wins against repo-beta)
    assert idx_beta_dot < idx_beta_plain < idx_alpha_dot < idx_alpha_plain
    # repo-alpha comes before workspace (so workspace wins against projects)
    assert idx_alpha_plain < idx_ws_dot < idx_ws_plain
    # workspace comes before bundled (so bundled wins against workspace)
    assert idx_ws_plain < idx_bundled
