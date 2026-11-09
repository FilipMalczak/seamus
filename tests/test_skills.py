"""Tests for the native LM-XML skills system and load/unload skill tools."""

from pathlib import Path
from uuid import uuid4

import lmxml

from seamus.config.models import AgentConfig, SkillsImplementation
from seamus.config.settings import SystemSettings
from seamus.domain.entities import Thread
from seamus.domain.modes import ModeName
from seamus.harness.prompt import (
    ActiveSkillPromptItem,
    AvailableSkillPromptItem,
    SkillsPromptDocument,
    SystemPromptDocument,
    build_default_identity,
    build_engineering_discipline,
    build_operating_environment,
    build_operational_mode_section,
    build_tool_usage,
)
from seamus.harness.skills import (
    DiscoveredSkill,
    SeamusSkillsMiddleware,
    discover_session_skills,
    parse_skill_markdown,
)
from seamus.harness.store import get_harness_store
from seamus.persistence.workspace import get_workspace_manager


def test_parse_skill_markdown_resilient_frontmatter() -> None:
    """Verify parse_skill_markdown handles unquoted colons, braces, and allowed_tools."""
    # Case 1: unquoted colons and braces
    text1 = """---
name: bevy-assets
description: Assets management for Bevy: handles gltf, png {nested: true}
allowed_tools:
  - make_artifact
  - ask
---
# Bevy Assets Guide
Step 1: Load assets
"""
    name, desc, body, tools = parse_skill_markdown(text1, "fallback")
    assert name == "bevy-assets"
    assert desc == "Assets management for Bevy: handles gltf, png {nested: true}"
    assert body == "# Bevy Assets Guide\nStep 1: Load assets"
    assert tools == ["make_artifact", "ask"]

    # Case 2: inline list format [tool1, tool2]
    text2 = """---
name: inline-tools
description: Inline list format
allowed_tools: [tool_x, tool_y]
---
Body content
"""
    name, desc, body, tools = parse_skill_markdown(text2, "fallback")
    assert name == "inline-tools"
    assert desc == "Inline list format"
    assert tools == ["tool_x", "tool_y"]

    # Case 3: folded multiline description
    text3 = """---
name: multiline-desc
description: >
  This is line one.
  This is line two: with colon.
---
Body text
"""
    name, desc, body, tools = parse_skill_markdown(text3, "fallback")
    assert name == "multiline-desc"
    assert "This is line one." in desc
    assert "with colon." in desc
    assert tools == []

    # Case 4: missing frontmatter
    text4 = "# Just markdown without frontmatter"
    name, desc, body, tools = parse_skill_markdown(text4, "default-name")
    assert name == "default-name"
    assert desc == ""
    assert body == "# Just markdown without frontmatter"
    assert tools == []


def test_discover_session_skills_precedence_and_shadowing(tmp_path: Path) -> None:
    """Verify implementation-agnostic discovery precedence (INV-035) and shadowing."""
    ws_mgr = get_workspace_manager()
    agent_id = uuid4()
    session_id = uuid4()
    data_dir = ws_mgr.get_session_data_dir(agent_id, session_id)
    data_dir.mkdir(parents=True, exist_ok=True)

    # 1. System skill directory
    sys_dir = tmp_path / "sys_skills"
    sys_skill_a = sys_dir / "skill-a"
    sys_skill_a.mkdir(parents=True)
    (sys_skill_a / "SKILL.md").write_text(
        "---\nname: skill-a\ndescription: System A\n---\n# System A"
    )

    sys_skill_b = sys_dir / "skill-b"
    sys_skill_b.mkdir(parents=True)
    (sys_skill_b / "SKILL.md").write_text(
        "---\nname: skill-b\ndescription: System B\nallowed_tools: [tool_b]\n---\n# System B"
    )

    # 2. Session workspace skill overriding skill-a
    ws_skill_a = data_dir / "skills" / "skill-a"
    ws_skill_a.mkdir(parents=True)
    (ws_skill_a / "SKILL.md").write_text(
        "---\nname: skill-a\ndescription: Session A\n---\n# Session A"
    )

    from seamus.config.settings import SystemSettingsStore, reset_system_settings_store

    reset_system_settings_store(
        SystemSettingsStore(initial_settings=SystemSettings(skill_directories=[str(sys_dir)]))
    )

    try:
        # Active skill names: skill-a is loaded
        skills = discover_session_skills(
            agent_id=agent_id,
            session_id=session_id,
            skills_implementation=SkillsImplementation.SEAMUS,
            active_skill_names=["skill-a"],
        )

        # Should find bundled skills (artifacts, a2ui_components) plus
        # workspace skill-a, system skill-b, and shadowed system skill-a
        skill_a_matches = [s for s in skills if s.name == "skill-a"]
        assert len(skill_a_matches) == 2
        # First match is the session workspace skill (active and loaded)
        assert skill_a_matches[0].origin_layer == "Session (skills)"
        assert skill_a_matches[0].active is True
        assert skill_a_matches[0].loaded is True
        assert skill_a_matches[0].description == "Session A"

        # Second match is the shadowed system skill (not active, not loaded)
        assert skill_a_matches[1].origin_layer.startswith("System")
        assert skill_a_matches[1].active is False
        assert skill_a_matches[1].loaded is False

        # skill-b is from system, active but not loaded
        skill_b = next(s for s in skills if s.name == "skill-b")
        assert skill_b.active is True
        assert skill_b.loaded is False
        assert skill_b.allowed_tools == ["tool_b"]

        # When skills_implementation is NONE, discovery returns empty list
        none_skills = discover_session_skills(
            agent_id=agent_id,
            session_id=session_id,
            skills_implementation=SkillsImplementation.NONE,
        )
        assert none_skills == []

    finally:
        reset_system_settings_store(None)


def test_seamus_skills_middleware_load_and_unload() -> None:
    """Verify SeamusSkillsMiddleware tool execution and active_skills state management."""
    thread = Thread(mode=ModeName.CHAT.value)
    assert thread.active_skills == []

    mock_skills = [
        DiscoveredSkill(
            name="artifacts",
            description="Artifacts guide",
            origin_layer="Bundled",
            sandbox_path="/skills/bundled/artifacts/SKILL.md",
            instructions="# Artifacts",
            allowed_tools=["make_artifact"],
            active=True,
            loaded=False,
        ),
        DiscoveredSkill(
            name="shadowed-skill",
            description="Shadowed",
            origin_layer="System",
            sandbox_path="/skills/system/0/shadowed/SKILL.md",
            instructions="# Shadowed",
            active=False,
            loaded=False,
        ),
    ]

    changed_notifications: list[list[str]] = []
    middleware = SeamusSkillsMiddleware(
        get_thread=lambda: thread,
        discovered_skills_provider=lambda: mock_skills,
        on_skills_changed=lambda skills: changed_notifications.append(skills),
    )

    # 1. Load an unknown skill
    err_msg = middleware.handle_load_skill("non-existent")
    assert "Error: Skill 'non-existent' not found or shadowed" in err_msg
    assert "artifacts" in err_msg
    assert thread.active_skills == []

    # 2. Load a shadowed skill
    err_msg2 = middleware.handle_load_skill("shadowed-skill")
    assert "Error: Skill 'shadowed-skill' not found or shadowed" in err_msg2

    # 3. Load valid skill "artifacts"
    success_msg = middleware.handle_load_skill("artifacts")
    assert "Skill 'artifacts' loaded successfully" in success_msg
    assert "make_artifact" in success_msg
    assert thread.active_skills == ["artifacts"]
    assert changed_notifications == [["artifacts"]]

    # 4. Load already loaded skill
    already_msg = middleware.handle_load_skill("artifacts")
    assert "already loaded" in already_msg
    assert thread.active_skills == ["artifacts"]

    # 5. Unload skill
    unload_msg = middleware.handle_unload_skill("artifacts")
    assert "unloaded successfully" in unload_msg
    assert thread.active_skills == []
    assert changed_notifications[-1] == []

    # 6. Unload skill that is not loaded
    unload_not_loaded = middleware.handle_unload_skill("artifacts")
    assert "not currently loaded" in unload_not_loaded


def test_lmxml_skills_prompt_serialization_no_attributes() -> None:
    """Verify LM-XML serialization renders pure child tags without XML attributes."""
    avail = [AvailableSkillPromptItem(name="artifacts", description="Artifacts guide")]
    active = [ActiveSkillPromptItem(name="artifacts", instructions="# Instructions")]
    skills_doc = SkillsPromptDocument(
        available_skills=avail,
        active_skills=active,
    )

    doc = SystemPromptDocument(
        identity=build_default_identity(),
        operating_environment=build_operating_environment("/workspace"),
        operational_mode=build_operational_mode_section(mode=ModeName.CHAT.value),
        engineering_discipline=build_engineering_discipline(),
        tool_usage=build_tool_usage(),
        skills=skills_doc,
    )

    xml_output = lmxml.dumps(doc.model_dump(mode="json", exclude_none=True))

    # Assert pure element tags without attributes
    assert "<skills>" in xml_output
    assert "<available_skills>" in xml_output
    assert "<name>artifacts</name>" in xml_output
    assert "<description>Artifacts guide</description>" in xml_output
    assert "<active_skills>" in xml_output
    assert "<instructions># Instructions</instructions>" in xml_output
    assert "<guidelines>" in xml_output
    # Ensure no <skill name="artifacts"> attributes
    assert '<skill name="' not in xml_output


def test_runner_skills_prompt_and_tool_gating(tmp_path: Path) -> None:
    """Verify runner dynamically updates effective system prompt and gates skill tools."""
    store = get_harness_store()

    from seamus.config.models import InferenceConfig

    config = AgentConfig(
        model_name="openai/gpt-4o-mini",
        system_prompt="Custom prompt",
        inference=InferenceConfig(api_key="sk-test-key"),
        skills_implementation=SkillsImplementation.SEAMUS,
    )
    agent = store.create_agent(config=config, name="skills-runner-agent")
    session = store.create_session(str(agent.id), name="skills-session")
    thread = session.get_open_thread()

    from seamus.harness.runner import get_runner_registry

    registry = get_runner_registry()
    runner = registry.get_runner(session, agent)

    # 1. Before loading, available skills are in effective prompt, active_skills tag is omitted
    prompt_initial = runner.build_effective_system_prompt()
    assert "<skills>" in prompt_initial
    assert "<available_skills>" in prompt_initial
    assert "artifacts" in prompt_initial
    assert "<active_skills>" not in prompt_initial

    # 2. Simulate loading skill "artifacts" into thread.active_skills
    thread.active_skills.append("artifacts")

    # 3. Prompt should now include <active_skills> with full instructions
    prompt_loaded = runner.build_effective_system_prompt()
    assert "<active_skills>" in prompt_loaded
    assert "Seamus Renderable Artifacts Guide" in prompt_loaded

    # 4. Unload skill
    thread.active_skills.remove("artifacts")
    prompt_unloaded = runner.build_effective_system_prompt()
    assert "<active_skills>" not in prompt_unloaded
