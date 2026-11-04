"""Unit tests for artifact storage, resolution, and questionnaire generation."""

import json
from pathlib import Path

import pytest

from seamus.domain.artifacts import CadenceMode, ExpositionMode
from seamus.harness.artifacts import (
    BASIC_CATALOG_ID,
    STANDARD_SURFACE_ID,
    ArtifactResolver,
    QuestionItem,
    QuestionnaireBuilder,
    seed_default_artifacts,
)


def test_seed_default_artifacts(tmp_path: Path) -> None:
    seed_default_artifacts(tmp_path)

    surface_file = tmp_path / "createSurface.json"
    assert surface_file.is_file()
    surface_data = json.loads(surface_file.read_text())
    assert surface_data["version"] == "v0.9"
    assert surface_data["createSurface"]["surfaceId"] == STANDARD_SURFACE_ID
    assert surface_data["createSurface"]["catalogId"] == BASIC_CATALOG_ID

    manifest_file = tmp_path / "questionnaires" / "manifest.json"
    assert manifest_file.is_file()
    manifest_data = json.loads(manifest_file.read_text())
    assert manifest_data["exposition"] == ExpositionMode.EMBEDDED
    assert manifest_data["cadence"] == CadenceMode.BLOCKING


def test_questionnaire_builder_single_question() -> None:
    questions = [
        QuestionItem(
            question="What color is the background?",
            answers=["white", "blue"],
            writein=True,
            id="backgroundColor",
        )
    ]
    res = QuestionnaireBuilder.build_update_components(questions)
    assert res["version"] == "v0.9"
    components = res["updateComponents"]["components"]
    ids = [c["id"] for c in components]

    assert "root" in ids
    assert "main" in ids
    assert "title" not in ids
    assert "subtitle" not in ids
    assert "backgroundColor_card" in ids
    assert "backgroundColor_options" in ids
    assert "backgroundColor_other" in ids
    assert "submit_button" in ids

    # Check ChoicePicker options (no duplicated question label)
    options_comp = next(c for c in components if c["id"] == "backgroundColor_options")
    assert options_comp["component"] == "ChoicePicker"
    assert "label" not in options_comp
    assert len(options_comp["options"]) == 3  # white, blue, other
    assert options_comp["value"] == {"path": "/answers/backgroundColor"}

    # Check Submit Button
    btn = next(c for c in components if c["id"] == "submit_button")
    assert btn["action"]["event"]["name"] == "submit_questionnaire"
    assert "backgroundColor" in btn["action"]["event"]["context"]
    assert "backgroundColorOther" in btn["action"]["event"]["context"]


def test_questionnaire_builder_multiple_questions_auto_ids() -> None:
    questions = [
        QuestionItem(
            question="What is the layout?",
            answers=["grid", "list"],
            writein=False,
        ),
        QuestionItem(
            question="Are headers bold and caps, or just bold?",
            answers=["bold+CAPS", "just bold"],
            writein=False,
        ),
    ]
    res = QuestionnaireBuilder.build_update_components(questions)
    components = res["updateComponents"]["components"]
    # Check no dividers exist between questions
    assert not any(c["component"] == "Divider" for c in components)
    main_comp = next(c for c in components if c["id"] == "main")
    assert main_comp["children"] == [
        "whatIsTheLayout_card",
        "areHeadersBoldAndCapsOrJustBold_card",
        "submit_button",
    ]

    btn = next(c for c in components if c["id"] == "submit_button")
    assert len(btn["action"]["event"]["context"]) == 2


def test_artifact_resolver_hierarchy(tmp_path: Path) -> None:
    seed_default_artifacts(tmp_path)
    resolver = ArtifactResolver(tmp_path)

    # 1. Root level createSurface resolves
    resolved_surf = resolver.resolve_file("questionnaires", "inst-1", "createSurface.json")
    assert resolved_surf == tmp_path / "createSurface.json"

    # 2. Class level manifest resolves
    resolved_manifest = resolver.resolve_file("questionnaires", "inst-1", "manifest.json")
    assert resolved_manifest == tmp_path / "questionnaires" / "manifest.json"

    # 3. Instance level override
    inst_dir = tmp_path / "questionnaires" / "inst-1"
    inst_dir.mkdir(parents=True, exist_ok=True)
    custom_comp = inst_dir / "updateComponents.json"
    custom_comp.write_text('{"custom": true}')

    resolved_comp = resolver.resolve_file("questionnaires", "inst-1", "updateComponents.json")
    assert resolved_comp == custom_comp


def test_artifact_resolver_closed_status(tmp_path: Path) -> None:
    seed_default_artifacts(tmp_path)
    resolver = ArtifactResolver(tmp_path)
    inst_dir = tmp_path / "questionnaires" / "q1"
    inst_dir.mkdir(parents=True, exist_ok=True)

    assert not resolver.is_closed("questionnaires", "q1")

    # Upward traversal should NOT mark instance closed
    class_delete = tmp_path / "questionnaires" / "deleteSurface.json"
    class_delete.write_text('{"deleteSurface": {"surfaceId": "surface"}}')
    assert not resolver.is_closed("questionnaires", "q1")

    # Instance level deleteSurface marks it closed
    inst_delete = inst_dir / "deleteSurface.json"
    inst_delete.write_text('{"deleteSurface": {"surfaceId": "surface"}}')
    assert resolver.is_closed("questionnaires", "q1")

    art = resolver.load_artifact("questionnaires", "q1")
    assert art.is_closed
    assert art.delete_surface is not None
    assert art.delete_surface["deleteSurface"]["surfaceId"] == "surface"


def test_artifact_resolver_instance_manifest_validation(tmp_path: Path) -> None:
    seed_default_artifacts(tmp_path)
    resolver = ArtifactResolver(tmp_path)
    inst_dir = tmp_path / "questionnaires" / "q2"
    inst_dir.mkdir(parents=True, exist_ok=True)

    # Mismatched instance manifest raises error for questionnaires
    (inst_dir / "manifest.json").write_text('{"exposition": "tabbed", "cadence": "nonblocking"}')
    with pytest.raises(ValueError, match="does not match class-level manifest"):
        resolver.load_manifest("questionnaires", "q2")

    # Unsupported artifact family raises error
    with pytest.raises(ValueError, match="Unsupported artifact kind"):
        resolver.load_manifest("magic_reports", "rep1")


def test_artifact_resolver_list_and_blocking(tmp_path: Path) -> None:
    seed_default_artifacts(tmp_path)
    resolver = ArtifactResolver(tmp_path)

    q_dir = tmp_path / "questionnaires" / "test-q"
    q_dir.mkdir(parents=True, exist_ok=True)
    (q_dir / "updateComponents.json").write_text('{"updateComponents": {"components": []}}')

    assert resolver.has_open_blocking_artifact()
    artifacts = resolver.list_artifacts()
    assert len(artifacts) == 1
    assert artifacts[0].name == "test-q"
    assert not artifacts[0].is_closed

    # Close artifact
    (q_dir / "deleteSurface.json").write_text('{"deleteSurface": {"surfaceId": "surface"}}')
    assert not resolver.has_open_blocking_artifact()
    assert resolver.list_artifacts()[0].is_closed


def test_question_answers_cardinality_validation() -> None:
    from pydantic import ValidationError

    from seamus.harness.runner import ResilientAskInput

    # QuestionItem validation
    with pytest.raises(ValueError, match="requires at least 2 choices"):
        QuestionItem(question="Choose color", answers=["red"], writein=False)

    with pytest.raises(ValueError, match="requires at least 1 choice"):
        QuestionItem(question="Choose color", answers=[], writein=True)

    # Valid QuestionItems
    q1 = QuestionItem(question="Choose color", answers=["red", "blue"], writein=False)
    assert len(q1.answers) == 2

    q2 = QuestionItem(question="Choose color", answers=["red"], writein=True)
    assert len(q2.answers) == 1

    # ResilientAskInput validation
    # Missing answers field raises ValidationError
    with pytest.raises(ValidationError):
        ResilientAskInput.model_validate({"question": "Missing answers"})

    # writein=False with 1 choice raises ValidationError
    with pytest.raises(ValidationError):
        ResilientAskInput.model_validate(
            {"question": "Only one option", "answers": ["one"], "writein": False}
        )

    # writein=False with 2 choices is valid
    ask1 = ResilientAskInput.model_validate(
        {"question": "Two options", "answers": ["one", "two"], "writein": False}
    )
    assert len(ask1.answers) == 2

    # writein=True with 0 choices raises ValidationError
    with pytest.raises(ValidationError):
        ResilientAskInput.model_validate({"question": "No options", "answers": [], "writein": True})

    # writein=True with 1 choice is valid
    ask2 = ResilientAskInput.model_validate(
        {"question": "One option with writein", "answers": ["one"], "writein": True}
    )
    assert len(ask2.answers) == 1

    # multiple=True validation
    q_multi = QuestionItem(question="Choose features", answers=["auth"], multiple=True)
    assert q_multi.multiple is True
    assert len(q_multi.answers) == 1

    with pytest.raises(ValueError, match="requires at least 1 choice"):
        QuestionItem(question="Choose features", answers=[], multiple=True)

    # ResilientAskInput with multiple and aliases
    ask_multi = ResilientAskInput.model_validate(
        {"question": "Pick many", "answers": ["a"], "multiple": True}
    )
    assert ask_multi.multiple is True

    ask_alias1 = ResilientAskInput.model_validate(
        {"question": "Pick many", "answers": ["a"], "multi_select": True}
    )
    assert ask_alias1.multiple is True

    ask_alias2 = ResilientAskInput.model_validate(
        {"question": "Pick many", "answers": ["a"], "multiselect": True}
    )
    assert ask_alias2.multiple is True


def test_questionnaire_builder_formatting_and_multi_select() -> None:
    questions = [
        QuestionItem(
            question="Select features",
            answers=["auth", "logging", "metrics"],
            multiple=True,
            id="features",
        ),
        QuestionItem(
            question="Primary database",
            answers=["postgres", "sqlite"],
            multiple=False,
            id="db",
        ),
    ]
    res = QuestionnaireBuilder.build_update_components(questions, title="Survey")
    components = res["updateComponents"]["components"]

    # Header title and subtitle are omitted from component tree
    assert not any(c["id"] in ("title", "subtitle") for c in components)

    # Question text components have no '###' or numbering prefix
    q1_text = next(c for c in components if c["id"] == "features_question")
    assert q1_text["text"] == "Select features"
    assert not q1_text["text"].startswith("#")

    q2_text = next(c for c in components if c["id"] == "db_question")
    assert q2_text["text"] == "Primary database"
    assert not q2_text["text"].startswith("#")

    # Multi-select ChoicePicker variant is multipleSelection
    q1_picker = next(c for c in components if c["id"] == "features_options")
    assert q1_picker["variant"] == "multipleSelection"

    # Single-select ChoicePicker variant is mutuallyExclusive
    q2_picker = next(c for c in components if c["id"] == "db_options")
    assert q2_picker["variant"] == "mutuallyExclusive"


def test_filter_sync_pr_diff_keeps_data_and_artifacts() -> None:
    from seamus.persistence.workspace import filter_sync_pr_diff

    raw_diff = (
        "diff --git a/data/results.csv b/data/results.csv\n"
        "--- a/data/results.csv\n"
        "+++ b/data/results.csv\n"
        "@@ -0,0 +1 @@\n"
        "+value1,value2\n"
        "diff --git a/agent/state/checkpoint.json b/agent/state/checkpoint.json\n"
        "--- a/agent/state/checkpoint.json\n"
        "+++ b/agent/state/checkpoint.json\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
        "diff --git a/artifacts/q1/manifest.json b/artifacts/q1/manifest.json\n"
        "--- a/artifacts/q1/manifest.json\n"
        "+++ b/artifacts/q1/manifest.json\n"
        "@@ -0,0 +1,2 @@\n"
        "+{\n"
        "+}\n"
        "diff --git a/skills/custom/SKILL.md b/skills/custom/SKILL.md\n"
        "--- a/skills/custom/SKILL.md\n"
        "+++ b/skills/custom/SKILL.md\n"
        "@@ -0,0 +1 @@\n"
        "+# Skill\n"
    )

    filtered = filter_sync_pr_diff(raw_diff)
    assert "diff --git a/data/results.csv b/data/results.csv" in filtered
    assert "diff --git a/artifacts/q1/manifest.json" in filtered
    assert "agent/state/checkpoint.json" not in filtered
    assert "skills/custom/SKILL.md" not in filtered


def test_system_prompt_user_inquiry_section() -> None:
    from seamus.harness.prompt import build_scaffold_prompt

    prompt = build_scaffold_prompt()
    assert "<user_inquiry>" in prompt
    assert "ask" in prompt
    assert "Never repeat, duplicate, or re-list questions" in prompt


def test_read_artifact_submission_fails_in_same_turn_as_ask() -> None:
    from seamus.config.models import AgentConfig, InferenceConfig
    from seamus.domain.entities import Agent
    from seamus.harness.runner import SessionAgentRunner
    from tests.test_runner import FakeAgent

    config = AgentConfig(
        inference=InferenceConfig(api_key="mock-key"),
        model_name="mock-model",
    )
    agent = Agent(config=config, name="test-agent")
    session = agent.create_session(name="test-session")
    runner = SessionAgentRunner(session=session, agent=FakeAgent())

    # 1. Calling read_artifact_submission before any ask call returns pending, does not raise
    res = json.loads(runner.handle_read_artifact_submission("arbitrary-id"))
    assert res.get("status") == "pending"

    # 2. Call ask in current turn
    ask_res = runner.handle_ask("What color?", ["red", "blue"], id="color_q")
    assert ask_res == "OK"
    assert runner._current_questionnaire_id is not None
    current_id = runner._current_questionnaire_id

    # 3. Calling read_artifact_submission with the questionnaire UUID in same turn fails
    with pytest.raises(ValueError, match="Cannot read artifact submission"):
        runner.handle_read_artifact_submission(current_id)

    # 4. Calling with the question id alias in same turn also fails
    with pytest.raises(ValueError, match="Cannot read artifact submission"):
        runner.handle_read_artifact_submission("color_q")

    # 5. Calling with empty string in same turn also fails
    with pytest.raises(ValueError, match="Cannot read artifact submission"):
        runner.handle_read_artifact_submission("")

    # 6. In a subsequent turn (after turn state reset), calling does not raise same-turn error
    runner._pending_questions = []
    runner._current_questionnaire_id = None
    runner._turn_created_artifact_ids.clear()

    res_subsequent = json.loads(runner.handle_read_artifact_submission(current_id))
    assert res_subsequent.get("status") == "pending"


def test_questionnaire_builder_duplicate_ids_fails() -> None:
    questions = [
        QuestionItem(question="Pick layout", answers=["grid", "list"], id="layout"),
        QuestionItem(question="Pick another layout", answers=["cards", "table"], id="layout"),
    ]
    with pytest.raises(ValueError, match="Duplicate question id 'layout'"):
        QuestionnaireBuilder.build_update_components(questions)


def test_runner_ask_duplicate_id_fails() -> None:
    from seamus.config.models import AgentConfig, InferenceConfig
    from seamus.domain.entities import Agent
    from seamus.harness.runner import SessionAgentRunner
    from tests.test_runner import FakeAgent

    config = AgentConfig(
        inference=InferenceConfig(api_key="mock-key"),
        model_name="mock-model",
    )
    agent = Agent(config=config, name="test-agent-duplicate-id")
    session = agent.create_session(name="test-session-duplicate-id")
    runner = SessionAgentRunner(session=session, agent=FakeAgent())

    # 1. First call with id succeeds
    res1 = runner.handle_ask("Select framework", ["react", "vue"], id="framework")
    assert res1 == "OK"
    assert len(runner._pending_questions) == 1

    # 2. Second call with same id fails at ask
    with pytest.raises(ValueError, match="already exists in the current questionnaire"):
        runner.handle_ask("Select testing framework", ["jest", "vitest"], id="framework")
    assert len(runner._pending_questions) == 1

    # 3. Duplicate auto-generated IDs also fail at ask
    res2 = runner.handle_ask("Database type?", ["sql", "nosql"])
    assert res2 == "OK"
    with pytest.raises(ValueError, match="already exists in the current questionnaire"):
        runner.handle_ask("Database type?", ["postgres", "mongo"])
