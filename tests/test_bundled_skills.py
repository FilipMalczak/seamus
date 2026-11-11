"""Unit tests for bundled platform skills integration and precedence."""

from pathlib import Path
from uuid import uuid4

from seamus.harness.sandbox import (
    BUNDLED_SKILLS_DIR,
    SandboxSettings,
    SeamusOpenSandboxBackend,
)


def test_bundled_skills_directory_exists() -> None:
    assert BUNDLED_SKILLS_DIR.is_dir()
    artifact_skill = BUNDLED_SKILLS_DIR / "artifacts" / "SKILL.md"
    assert artifact_skill.is_file()
    content = artifact_skill.read_text(encoding="utf-8")
    assert "name: artifacts" in content
    assert "A2UI" in content

    a2ui_skill = BUNDLED_SKILLS_DIR / "a2ui_components" / "SKILL.md"
    assert a2ui_skill.is_file()
    a2ui_content = a2ui_skill.read_text(encoding="utf-8")
    assert "name: a2ui_components" in a2ui_content


def test_sandbox_backend_mounts_bundled_skill_and_artifacts(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    artifacts_dir = tmp_path / "artifacts"
    data_dir.mkdir(parents=True)
    artifacts_dir.mkdir(parents=True)

    backend = SeamusOpenSandboxBackend(
        agent_id=uuid4(),
        session_id=uuid4(),
        data_dir=data_dir,
        artifacts_dir=artifacts_dir,
        settings=SandboxSettings(use_server_proxy=False),
        skill_directories=["/tmp/nonexistent-skill"],
    )

    art_vol = backend.build_artifact_volume()
    assert art_vol.name == "artifacts"
    assert art_vol.mount_path == "/artifacts"
    assert art_vol.read_only is True

    bundled_vol = backend.build_bundled_skill_volume()
    assert bundled_vol is not None
    assert bundled_vol.name == "skills-bundled"
    assert bundled_vol.mount_path == "/skills/bundled"
    assert bundled_vol.read_only is True
    assert bundled_vol.host is not None
    assert bundled_vol.pvc is None


def test_sandbox_backend_mounts_bundled_skill_via_workspace_volume(tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspaces"
    data_dir = workspace_root / "agent-1" / "session-1" / "data"
    artifacts_dir = workspace_root / "agent-1" / "session-1" / "artifacts"
    data_dir.mkdir(parents=True)
    artifacts_dir.mkdir(parents=True)

    backend = SeamusOpenSandboxBackend(
        agent_id=uuid4(),
        session_id=uuid4(),
        data_dir=data_dir,
        artifacts_dir=artifacts_dir,
        workspace_root=workspace_root,
        settings=SandboxSettings(
            use_server_proxy=False,
            workspace_volume="seamus-workspaces",
        ),
        skill_directories=[],
    )

    bundled_vol = backend.build_bundled_skill_volume()
    assert bundled_vol is not None
    assert bundled_vol.name == "skills-bundled"
    assert bundled_vol.mount_path == "/skills/bundled"
    assert bundled_vol.read_only is True
    assert bundled_vol.pvc is not None
    assert bundled_vol.pvc.claim_name == "seamus-workspaces"
    assert bundled_vol.sub_path == "bundled_skills"
    assert bundled_vol.host is None

    # Check that skills files were synced to workspace_root / "bundled_skills"
    synced_artifacts = workspace_root / "bundled_skills" / "artifacts" / "SKILL.md"
    assert synced_artifacts.is_file()
    assert "A2UI" in synced_artifacts.read_text(encoding="utf-8")

    synced_a2ui = workspace_root / "bundled_skills" / "a2ui_components" / "SKILL.md"
    assert synced_a2ui.is_file()


def test_bundled_skills_precedence_in_skill_sources(tmp_path: Path) -> None:
    backend = SeamusOpenSandboxBackend(
        agent_id=uuid4(),
        session_id=uuid4(),
        data_dir=tmp_path / "data",
        artifacts_dir=tmp_path / "artifacts",
        settings=SandboxSettings(workdir="/workspace"),
        skill_directories=[],
    )

    sources = backend.get_skill_sources()
    # The last source wins in DeepAgents ("last one wins")
    assert len(sources) >= 3
    # First: session (.skills)
    assert sources[-3][0] == "/workspace/.skills"
    # Second: session (skills)
    assert sources[-2][0] == "/workspace/skills"
    # Final/Highest priority: bundled platform skills
    assert sources[-1][0] == "/skills/bundled"
    assert sources[-1][1] == "Bundled"


def test_bundled_skills_and_tools_in_inspector() -> None:
    from seamus.config.models import AgentConfig, InferenceConfig, SkillsImplementation
    from seamus.harness.inspector import (
        build_agent_inspect_report,
        extract_session_skills,
        get_default_tools_inspect_info,
    )
    from seamus.harness.store import get_harness_store

    store = get_harness_store()
    agent_name = f"test-bundled-{uuid4().hex[:6]}"
    cfg = AgentConfig(
        model_name="dummy",
        system_prompt="test",
        inference=InferenceConfig(api_key="dummy"),
        skills_implementation=SkillsImplementation.DEEPAGENTS,
    )
    agent = store.create_agent(config=cfg, name=agent_name)
    session = list(agent.sessions.values())[0]

    # Verify extract_session_skills includes bundled skills
    discovered = extract_session_skills(agent.id, session.id, cfg.skills_implementation)
    names = [s.name for s in discovered]
    assert "artifacts" in names
    artifact_skill = next(s for s in discovered if s.name == "artifacts")
    assert artifact_skill.origin_layer == "Bundled"
    assert artifact_skill.sandbox_path == "/skills/bundled/artifacts/SKILL.md"

    # Verify default tools inspect info includes make_questionnaire and wait_for_click
    default_tools = get_default_tools_inspect_info()
    tool_names = [t.name for t in default_tools]
    assert "make_questionnaire" in tool_names
    assert "wait_for_click" in tool_names
    assert "ask" not in tool_names
    assert "read_artifact_submission" not in tool_names

    # Verify report includes skills and prompt mentions
    report = build_agent_inspect_report(str(agent.id), str(session.id))
    report_skill_names = [s.name for s in (report.skills or [])]
    assert "artifacts" in report_skill_names

    report_tool_names = [t.name for t in report.tools]
    assert "ask" not in report_tool_names
    assert "make_questionnaire" in report_tool_names
    assert "read_artifact_submission" not in report_tool_names

    # Verify prompt mentions
    assert "artifacts" in report.prompts.composite
    assert "make_questionnaire" in report.prompts.composite
