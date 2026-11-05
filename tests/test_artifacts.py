"""Unit tests for artifact storage, resolution, and questionnaire generation."""

import json
from pathlib import Path

import pytest

from seamus.domain.artifacts import CadenceMode, ExpositionMode
from seamus.harness.artifacts import (
    ADAPTIVE_CARD_SCHEMA,
    ADAPTIVE_CARD_VERSION,
    ArtifactResolver,
    PlanBuilder,
    QuestionItem,
    QuestionnaireBuilder,
    seed_default_artifacts,
)


def test_seed_default_artifacts(tmp_path: Path) -> None:
    seed_default_artifacts(tmp_path)

    # createSurface.json should NOT be created
    surface_file = tmp_path / "createSurface.json"
    assert not surface_file.exists()

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
    card = QuestionnaireBuilder.build_card(questions)
    assert card["$schema"] == ADAPTIVE_CARD_SCHEMA
    assert card["type"] == "AdaptiveCard"
    assert card["version"] == ADAPTIVE_CARD_VERSION

    body = card["body"]
    assert len(body) == 1
    container = body[0]
    assert container["type"] == "Container"
    assert container["id"] == "backgroundColor_container"

    items = container["items"]
    assert items[0]["type"] == "TextBlock"
    assert items[0]["text"] == "What color is the background?"
    assert items[0]["weight"] == "Bolder"

    assert items[1]["type"] == "Input.ChoiceSet"
    assert items[1]["id"] == "backgroundColor"
    assert items[1]["isMultiSelect"] is False
    assert len(items[1]["choices"]) == 3  # white, blue, other

    assert items[2]["type"] == "Input.Text"
    assert items[2]["id"] == "backgroundColorOther"

    actions = card["actions"]
    assert len(actions) == 1
    assert actions[0]["type"] == "Action.Submit"
    assert actions[0]["title"] == "Submit"
    assert actions[0]["data"]["action"] == "submit_questionnaire"


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
    card = QuestionnaireBuilder.build_card(questions)
    body = card["body"]
    assert len(body) == 2
    assert body[0]["id"] == "whatIsTheLayout_container"
    assert body[1]["id"] == "areHeadersBoldAndCapsOrJustBold_container"
    assert body[1]["separator"] is True


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
    card = QuestionnaireBuilder.build_card(questions, title="Survey")
    body = card["body"]

    c1 = body[0]
    picker1 = next(item for item in c1["items"] if item["type"] == "Input.ChoiceSet")
    assert picker1["isMultiSelect"] is True

    c2 = body[1]
    picker2 = next(item for item in c2["items"] if item["type"] == "Input.ChoiceSet")
    assert picker2["isMultiSelect"] is False


def test_plan_builder_lifecycle(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / "artifacts"
    plan_id = "test-plan"
    initial_content = "# Architecture\n\nStep 1: Install packages\nStep 2: Run tests"

    # 1. Create plan
    PlanBuilder.create_plan(artifacts_dir, plan_id, initial_content, title="Migration Plan")
    card_path = artifacts_dir / "plans" / plan_id / "card.json"
    plan_md_path = artifacts_dir / "plans" / plan_id / "plan.md"
    assert card_path.is_file()
    assert plan_md_path.is_file()
    assert plan_md_path.read_text(encoding="utf-8") == initial_content

    content, title = PlanBuilder.read_plan(artifacts_dir, plan_id)
    assert content == initial_content
    assert title == "Migration Plan"

    # Verify structured containers in card
    card_data = json.loads(card_path.read_text(encoding="utf-8"))
    assert card_data["type"] == "AdaptiveCard"
    body = card_data["body"]
    container_ids = [c.get("id") for c in body if isinstance(c, dict)]
    assert "plan_header" in container_ids
    assert "plan_content" in container_ids
    assert "plan_comments" in container_ids
    assert len(card_data["actions"]) == 1
    assert card_data["actions"][0]["data"]["action"] == "proceed_plan"

    # 2. Update plan
    updated_content = initial_content + "\nStep 3: Deploy"
    PlanBuilder.update_plan(artifacts_dir, plan_id, updated_content)
    content, _ = PlanBuilder.read_plan(artifacts_dir, plan_id)
    assert content == updated_content
    assert plan_md_path.read_text(encoding="utf-8") == updated_content

    # 3. Edit plan with substring replacement
    PlanBuilder.edit_plan(artifacts_dir, plan_id, "Step 2: Run tests", "Step 2: Run all tests")
    content, _ = PlanBuilder.read_plan(artifacts_dir, plan_id)
    assert "Step 2: Run all tests" in content
    assert "Step 2: Run all tests" in plan_md_path.read_text(encoding="utf-8")

    # 4. Approve plan
    PlanBuilder.approve_plan(artifacts_dir, plan_id)
    closed_file = artifacts_dir / "plans" / plan_id / "closed.json"
    assert closed_file.is_file()
    approved_card = json.loads(card_path.read_text(encoding="utf-8"))
    assert len(approved_card["actions"]) == 0  # Proceed button stripped


def test_artifact_resolver_hierarchy(tmp_path: Path) -> None:
    seed_default_artifacts(tmp_path)
    resolver = ArtifactResolver(tmp_path)

    # 1. Class level manifest resolves
    resolved_manifest = resolver.resolve_file("questionnaires", "inst-1", "manifest.json")
    assert resolved_manifest == tmp_path / "questionnaires" / "manifest.json"

    # 2. Instance level card resolves
    inst_dir = tmp_path / "questionnaires" / "inst-1"
    inst_dir.mkdir(parents=True, exist_ok=True)
    custom_card = inst_dir / "card.json"
    custom_card.write_text('{"type": "AdaptiveCard", "body": []}')

    resolved_card = resolver.resolve_file("questionnaires", "inst-1", "card.json")
    assert resolved_card == custom_card


def test_artifact_resolver_closed_status(tmp_path: Path) -> None:
    seed_default_artifacts(tmp_path)
    resolver = ArtifactResolver(tmp_path)
    inst_dir = tmp_path / "questionnaires" / "q1"
    inst_dir.mkdir(parents=True, exist_ok=True)

    assert not resolver.is_closed("questionnaires", "q1")

    # Instance level closed.json marks it closed
    inst_closed = inst_dir / "closed.json"
    inst_closed.write_text('{"closed": true}')
    assert resolver.is_closed("questionnaires", "q1")

    art = resolver.load_artifact("questionnaires", "q1")
    assert art.is_closed


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
    (q_dir / "card.json").write_text('{"type": "AdaptiveCard", "body": []}')

    assert resolver.has_open_blocking_artifact()
    artifacts = resolver.list_artifacts()
    assert len(artifacts) == 1
    assert artifacts[0].name == "test-q"
    assert not artifacts[0].is_closed

    # Close artifact
    (q_dir / "closed.json").write_text('{"closed": true}')
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
    with pytest.raises(ValidationError):
        ResilientAskInput.model_validate({"question": "Missing answers"})

    with pytest.raises(ValidationError):
        ResilientAskInput.model_validate(
            {"question": "Only one option", "answers": ["one"], "writein": False}
        )

    ask1 = ResilientAskInput.model_validate(
        {"question": "Two options", "answers": ["one", "two"], "writein": False}
    )
    assert len(ask1.answers) == 2

    with pytest.raises(ValidationError):
        ResilientAskInput.model_validate({"question": "No options", "answers": [], "writein": True})

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

    # 1. Calling read_artifact_submission before any ask call returns pending
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

    # 6. In a subsequent turn, calling does not raise same-turn error
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
        QuestionnaireBuilder.build_card(questions)


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

    res1 = runner.handle_ask("Select framework", ["react", "vue"], id="framework")
    assert res1 == "OK"
    assert len(runner._pending_questions) == 1

    with pytest.raises(ValueError, match="already exists in the current questionnaire"):
        runner.handle_ask("Select testing framework", ["jest", "vitest"], id="framework")
    assert len(runner._pending_questions) == 1

    res2 = runner.handle_ask("Database type?", ["sql", "nosql"])
    assert res2 == "OK"
    with pytest.raises(ValueError, match="already exists in the current questionnaire"):
        runner.handle_ask("Database type?", ["postgres", "mongo"])
