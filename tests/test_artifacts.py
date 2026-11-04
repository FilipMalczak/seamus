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
    assert "title" in ids
    assert "backgroundColor_card" in ids
    assert "backgroundColor_options" in ids
    assert "backgroundColor_other" in ids
    assert "submit_button" in ids

    # Check ChoicePicker options
    options_comp = next(c for c in components if c["id"] == "backgroundColor_options")
    assert options_comp["component"] == "ChoicePicker"
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
    # Check dividers exist between questions
    divider = next((c for c in components if c["component"] == "Divider"), None)
    assert divider is not None

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
