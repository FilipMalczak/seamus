"""Unit tests for A2UI subset artifact storage, builders, dispatch, and resolver."""

import json
from pathlib import Path
from typing import Any

import pytest

from seamus.config.models import (
    AgentConfig,
    InferenceConfig,
    InferenceFormat,
)
from seamus.domain.artifacts import (
    ArtifactManifest,
    ArtifactState,
    ManifestButton,
)
from seamus.harness.artifacts import (
    A2UISurfaceValidationError,
    ArtifactBuilder,
    ArtifactCorruptedError,
    ArtifactResolver,
    FormBuilder,
    PlanBuilder,
    Question,
    QuestionnaireBuilder,
    check_a2ui_surface_warnings,
    dispatch_button_click,
    normalize_a2ui_components,
    seed_default_artifacts,
    validate_a2ui_surface,
)
from seamus.harness.runner import SessionAgentRunner
from seamus.harness.store import HarnessStore


def _make_agent_config() -> AgentConfig:
    return AgentConfig(
        inference=InferenceConfig(
            format=InferenceFormat.OPENAI,
            base_url="https://api.openai.com/v1",
            api_key="test-key",
        ),
        model_name="gpt-4o",
    )


def test_seed_default_artifacts(tmp_path: Path) -> None:
    seed_default_artifacts(tmp_path)
    # createSurface.json or legacy adaptive card files should NOT be created
    assert not (tmp_path / "createSurface.json").exists()
    assert not (tmp_path / "questionnaires" / "card.json").exists()


def test_manifest_button_click_validation() -> None:
    # Positive integer allowed
    b1 = ManifestButton(id="btn1", mode="set", clicks=3)
    assert b1.clicks == 3

    # Star '*' allowed
    b2 = ManifestButton(id="btn2", mode="append", clicks="*")
    assert b2.clicks == "*"

    # 0 or negative integers disallowed in manifest schema
    with pytest.raises(ValueError, match="positive integer"):
        ManifestButton(id="btn3", mode="set", clicks=0)

    with pytest.raises(ValueError, match="positive integer"):
        ManifestButton(id="btn4", mode="set", clicks=-1)

    # 0 or negative integers ARE allowed in ArtifactState (e.g. when quota exhausted)
    st = ArtifactState(clicksLeft={"btn1": 0, "btn2": -1})
    assert st.clicksLeft["btn1"] == 0
    assert st.clicksLeft["btn2"] == -1


def test_artifact_builder_create_artifact(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / "artifacts"
    manifest = ArtifactManifest(
        name="Custom UI",
        exposition="embedded",
        blocking=True,
        commentable=False,
        buttons=[
            ManifestButton(id="btn_ok", clicks=2, unblocking=True),
            ManifestButton(id="btn_log", clicks="*"),
        ],
    )
    components: list[dict[str, Any]] = [
        {"id": "col", "component": "Column", "children": ["btn_ok", "btn_log"]},
        {"id": "btn_ok", "component": "Button", "title": "OK"},
        {"id": "btn_log", "component": "Button", "title": "Log"},
    ]

    art_uuid = ArtifactBuilder.create_artifact(
        artifacts_dir=artifacts_dir,
        family="custom",
        manifest=manifest,
        components=components,
    )

    art_dir = artifacts_dir / "custom" / art_uuid
    assert art_dir.is_dir()
    assert (art_dir / "manifest.json").is_file()
    assert (art_dir / "body.json").is_file()
    assert (art_dir / "state.json").is_file()
    assert not (art_dir / "closed.marker").exists()

    state = json.loads((art_dir / "state.json").read_text(encoding="utf-8"))
    assert state["last_event"] is None
    assert state["clicksLeft"]["btn_ok"] == 2
    assert state["clicksLeft"]["btn_log"] == "*"


def test_inv_art_003_body_manifest_coexistence(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / "artifacts"
    corrupt_dir = artifacts_dir / "custom" / "corrupt-uuid"
    corrupt_dir.mkdir(parents=True, exist_ok=True)

    # manifest exists but body.json is missing
    (corrupt_dir / "manifest.json").write_text(
        json.dumps(
            {
                "name": "Bad",
                "exposition": "embedded",
                "blocking": False,
                "commentable": False,
                "buttons": [],
            }
        ),
        encoding="utf-8",
    )

    resolver = ArtifactResolver(artifacts_dir)
    with pytest.raises(ArtifactCorruptedError, match="manifest.json exists without body.json"):
        resolver.load_artifact("custom", "corrupt-uuid")


def test_questionnaire_builder_lifecycle(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / "artifacts"
    questions = [
        Question(
            body="What is your favorite color?",
            answers=["Red", "Green", "Blue"],
            multiple_choice=False,
        ),
        Question(
            body="Select accessories",
            answers=["Case", "Charger"],
            multiple_choice=True,
        ),
    ]

    uuid = QuestionnaireBuilder.create_questionnaire(
        artifacts_dir=artifacts_dir,
        questions=questions,
        title="Color Survey",
    )

    resolver = ArtifactResolver(artifacts_dir)
    info = resolver.load_artifact("questionnaires", uuid)
    assert info.manifest.name == "Color Survey"
    assert info.manifest.exposition == "embedded"
    assert info.manifest.blocking is True
    assert info.manifest.commentable is False
    assert len(info.manifest.buttons) == 1
    assert info.manifest.buttons[0].id == "submit_btn"
    assert info.manifest.buttons[0].unblocking is True
    assert info.manifest.buttons[0].closing is True
    assert not info.is_closed

    # Body validation
    assert len(info.body) > 0
    choice_sets = [c for c in info.body if c.get("component") == "ChoiceSet"]
    assert len(choice_sets) == 2
    assert choice_sets[0]["isMultiSelect"] is False
    assert choice_sets[1]["isMultiSelect"] is True


def test_form_builder_lifecycle(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / "artifacts"
    questions = [
        Question(
            body="Deployment environment?",
            answers=["Staging", "Production"],
            multiple_choice=False,
        )
    ]

    uuid = FormBuilder.create_form(
        artifacts_dir=artifacts_dir,
        questions=questions,
        title="Deploy Form",
    )

    resolver = ArtifactResolver(artifacts_dir)
    info = resolver.load_artifact("forms", uuid)
    assert info.manifest.name == "Deploy Form"
    assert info.manifest.exposition == "tabbed"
    assert info.manifest.blocking is False
    assert info.manifest.commentable is False
    assert len(info.manifest.buttons) == 1
    assert info.manifest.buttons[0].id == "submit_btn"
    assert info.manifest.buttons[0].unblocking is False
    assert info.manifest.buttons[0].closing is True


def test_plan_builder_lifecycle(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / "artifacts"
    plan_uuid = "plan-xyz"
    content = "# Phase 1\n\nSetup DB\nSetup Auth"

    # 1. Create plan
    PlanBuilder.create_plan(artifacts_dir, plan_uuid, content=content, title="Release Plan")
    plan_dir = artifacts_dir / "plans" / plan_uuid
    assert plan_dir.is_dir()
    assert (plan_dir / "manifest.json").is_file()
    assert (plan_dir / "body.json").is_file()
    assert (plan_dir / "state.json").is_file()
    assert (plan_dir / "plan.md").is_file()
    assert (plan_dir / "plan.md").read_text(encoding="utf-8") == content

    # 2. Read plan
    read_c, read_t = PlanBuilder.read_plan(artifacts_dir, plan_uuid)
    assert read_c == content
    assert read_t == "Release Plan"

    # 3. Update plan
    updated = content + "\nSetup API"
    PlanBuilder.update_plan(artifacts_dir, plan_uuid, updated)
    assert (plan_dir / "plan.md").read_text(encoding="utf-8") == updated

    # 4. Edit plan with substring replacement
    PlanBuilder.edit_plan(artifacts_dir, plan_uuid, "Setup Auth", "Setup OAuth2")
    edited_c, _ = PlanBuilder.read_plan(artifacts_dir, plan_uuid)
    assert "Setup OAuth2" in edited_c
    assert "Setup Auth" not in edited_c

    # 5. Approve plan
    assert not (plan_dir / "closed.marker").exists()
    PlanBuilder.approve_plan(artifacts_dir, plan_uuid)
    assert (plan_dir / "closed.marker").exists()

    # Re-reading via resolver confirms closed
    resolver = ArtifactResolver(artifacts_dir)
    plan_info = resolver.load_artifact("plans", plan_uuid)
    assert plan_info.is_closed is True
    assert plan_info.state.clicksLeft.get("proceed_btn") == "*"


def test_plan_review_button_and_unlimited_clicks(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / "artifacts"
    plan_uuid = "plan-review-test"
    content = "# Architecture\n\n- Component A\n- Component B"

    PlanBuilder.create_plan(artifacts_dir, plan_uuid, content=content, title="Arch Plan")
    plan_dir = artifacts_dir / "plans" / plan_uuid

    # Verify body.json has a valid Button component for review_btn with label Review
    body_data = json.loads((plan_dir / "body.json").read_text(encoding="utf-8"))
    components_by_id = {c["id"]: c for c in body_data}
    assert "review_btn" in components_by_id
    assert components_by_id["review_btn"]["component"] == "Button"
    assert components_by_id["review_btn"]["variant"] == "default"
    assert components_by_id["review_btn"]["child"] == "review_label"
    assert components_by_id["review_label"]["component"] == "Text"
    assert components_by_id["review_label"]["text"] == "Review"

    # Verify manifest.json declares review_btn with clicks="*"
    manifest_data = json.loads((plan_dir / "manifest.json").read_text(encoding="utf-8"))
    btns = {b["id"]: b for b in manifest_data["buttons"]}
    assert "review_btn" in btns
    assert btns["review_btn"]["clicks"] == "*"
    assert btns["review_btn"]["closing"] is False

    # Dispatch multiple review clicks with comments payload
    for i in range(3):
        res = dispatch_button_click(
            artifacts_dir=artifacts_dir,
            family="plans",
            uuid=plan_uuid,
            button_id="review_btn",
            comments=[
                {
                    "location": "p:0",
                    "selectedText": "Component A",
                    "comment": f"Feedback {i + 1}",
                }
            ],
        )
        assert res.button_id == "review_btn"
        assert res.comments is not None
        assert len(res.comments) == 1
        assert res.comments[0]["comment"] == f"Feedback {i + 1}"

    # Verify interactions/review_btn.jsonl has 3 appended records
    int_file = plan_dir / "interactions" / "review_btn.jsonl"
    assert int_file.is_file()
    lines = [line for line in int_file.read_text(encoding="utf-8").strip().splitlines() if line]
    assert len(lines) == 3
    assert json.loads(lines[0])["comments"][0]["comment"] == "Feedback 1"
    assert json.loads(lines[1])["comments"][0]["comment"] == "Feedback 2"
    assert json.loads(lines[2])["comments"][0]["comment"] == "Feedback 3"

    # Verify state.json retains clicks="*" and artifact is not closed
    state_data = json.loads((plan_dir / "state.json").read_text(encoding="utf-8"))
    assert state_data["clicksLeft"]["review_btn"] == "*"
    assert state_data["last_event"]["comments"][0]["comment"] == "Feedback 3"
    assert not (plan_dir / "closed.marker").exists()


def test_dispatch_button_click_quotas_and_jsonl(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / "artifacts"
    manifest = ArtifactManifest(
        name="Counter Test",
        exposition="embedded",
        blocking=False,
        commentable=False,
        buttons=[
            ManifestButton(id="set_btn", clicks=2, unblocking=False, closing=False),
            ManifestButton(id="app_btn", clicks=1, unblocking=True, closing=True),
        ],
    )
    components: list[dict[str, Any]] = [
        {"id": "col", "component": "Column", "children": ["set_btn", "app_btn"]},
        {"id": "set_btn", "component": "Button", "title": "Set"},
        {"id": "app_btn", "component": "Button", "title": "App"},
    ]
    uuid = ArtifactBuilder.create_artifact(
        artifacts_dir=artifacts_dir,
        family="test_family",
        manifest=manifest,
        components=components,
    )

    art_dir = artifacts_dir / "test_family" / uuid

    # 1. Click set_btn first time
    res1 = dispatch_button_click(
        artifacts_dir=artifacts_dir,
        family="test_family",
        uuid=uuid,
        button_id="set_btn",
        data={"val": "first"},
    )
    assert res1.button_id == "set_btn"
    assert res1.data == {"val": "first"}

    # interactions/set_btn.jsonl should have 1 JSONL record
    int_file = art_dir / "interactions" / "set_btn.jsonl"
    assert int_file.is_file()
    lines1 = [line for line in int_file.read_text(encoding="utf-8").strip().splitlines() if line]
    assert len(lines1) == 1
    rec1 = json.loads(lines1[0])
    assert rec1["event"] == "set_btn"
    assert rec1["data"] == {"val": "first"}

    # state.json last_event updated, clicks left decremented to 1
    state1 = json.loads((art_dir / "state.json").read_text(encoding="utf-8"))
    assert state1["last_event"]["data"] == {"val": "first"}
    assert state1["clicksLeft"]["set_btn"] == 1

    # 2. Click set_btn second time (quota reaches 0)
    res2 = dispatch_button_click(
        artifacts_dir=artifacts_dir,
        family="test_family",
        uuid=uuid,
        button_id="set_btn",
        data={"val": "second"},
    )
    assert res2.button_id == "set_btn"
    state2 = json.loads((art_dir / "state.json").read_text(encoding="utf-8"))
    assert state2["last_event"]["data"] == {"val": "second"}
    assert state2["clicksLeft"]["set_btn"] == 0

    lines2 = [line for line in int_file.read_text(encoding="utf-8").strip().splitlines() if line]
    assert len(lines2) == 2
    assert json.loads(lines2[1])["data"] == {"val": "second"}

    # 3. Third click on set_btn fails with ValueError (inactive)
    with pytest.raises(ValueError, match="exhausted its remaining clicks"):
        dispatch_button_click(
            artifacts_dir=artifacts_dir,
            family="test_family",
            uuid=uuid,
            button_id="set_btn",
            data={"val": "third"},
        )

    # 4. Click unlisted button raises ValueError
    with pytest.raises(ValueError, match="not configured in artifact manifest"):
        dispatch_button_click(
            artifacts_dir=artifacts_dir,
            family="test_family",
            uuid=uuid,
            button_id="rogue_btn",
            data={},
        )

    # 5. Click app_btn (closing=True)
    res_app = dispatch_button_click(
        artifacts_dir=artifacts_dir,
        family="test_family",
        uuid=uuid,
        button_id="app_btn",
        data={"note": "done"},
    )
    assert res_app.button_id == "app_btn"
    app_file = art_dir / "interactions" / "app_btn.jsonl"
    assert app_file.is_file()
    assert '"note": "done"' in app_file.read_text(encoding="utf-8")
    assert (art_dir / "closed.marker").exists()


def test_artifact_resolver_list_and_blocking(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / "artifacts"
    resolver = ArtifactResolver(artifacts_dir)

    assert not resolver.has_open_blocking_artifact()
    assert resolver.list_artifacts() == []

    # Create blocking questionnaire
    q_uuid = QuestionnaireBuilder.create_questionnaire(
        artifacts_dir=artifacts_dir,
        questions=[Question(body="Favorite editor?", answers=["vim", "emacs", "vscode"])],
        title="Editor survey",
    )

    assert resolver.has_open_blocking_artifact()
    arts = resolver.list_artifacts()
    assert len(arts) == 1
    assert arts[0].uuid == q_uuid
    assert arts[0].is_closed is False

    # Close the questionnaire
    q_dir = artifacts_dir / "questionnaires" / q_uuid
    (q_dir / "closed.marker").touch()

    assert not resolver.has_open_blocking_artifact()
    assert resolver.list_artifacts()[0].is_closed is True


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
        "diff --git a/artifacts/q/manifest.json b/artifacts/q/manifest.json\n"
        "--- a/artifacts/q/manifest.json\n"
        "+++ b/artifacts/q/manifest.json\n"
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
    assert "diff --git a/artifacts/q/manifest.json" in filtered
    assert "agent/state/checkpoint.json" not in filtered
    assert "skills/custom/SKILL.md" not in filtered


def test_system_prompt_user_inquiry_section() -> None:
    from seamus.harness.prompt import build_scaffold_prompt

    # In chat mode: make_questionnaire, make_artifact, wait_for_click
    prompt_chat = build_scaffold_prompt(mode="chat")
    assert "<user_inquiry>" in prompt_chat
    assert "make_questionnaire" in prompt_chat
    assert "make_artifact" in prompt_chat
    assert "wait_for_click" in prompt_chat
    assert "read_artifact_submission" not in prompt_chat
    assert "Never repeat, duplicate, or re-list questions" in prompt_chat

    # In plan discuss mode: make_form is also present
    prompt_plan = build_scaffold_prompt(mode="plan", phase="discuss")
    assert "<user_inquiry>" in prompt_plan
    assert "make_form" in prompt_plan
    assert "make_questionnaire" in prompt_plan
    assert "make_artifact" in prompt_plan


def test_questionnaire_write_in_and_schema_translation(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / "artifacts"
    questions = [
        Question(
            body="Primary language?",
            answers=["Python", "TypeScript", "Rust"],
            multiple_choice=False,
            write_in=True,
        ),
        Question(
            body="Target platforms?",
            answers=["Linux", "macOS", "Windows"],
            multiple_choice=True,
            write_in=False,
        ),
    ]

    q_uuid = QuestionnaireBuilder.create_questionnaire(
        artifacts_dir=artifacts_dir,
        questions=questions,
        title="Stack Questionnaire",
    )

    art_dir = artifacts_dir / "questionnaires" / q_uuid
    assert (art_dir / "schema.json").is_file()
    assert (art_dir / "body.json").is_file()

    # Check body components: ChoiceSet value bound to path, TextField for write-in
    components = json.loads((art_dir / "body.json").read_text(encoding="utf-8"))
    choice_sets = [c for c in components if c.get("component") == "ChoiceSet"]
    text_fields = [c for c in components if c.get("component") == "TextField"]
    button = next(c for c in components if c.get("component") == "Button")

    assert len(choice_sets) == 2
    assert len(text_fields) == 1
    assert choice_sets[0]["value"] == ""
    # Write-in choice set has "Other" as last choice
    assert choice_sets[0]["choices"][-1]["label"] == "Other"
    assert choice_sets[0]["choices"][-1]["value"] == "other"
    # Write-in text field is labelless and empty string
    assert text_fields[0]["value"] == ""
    assert text_fields[0]["label"] == ""

    # Button action has no dynamic context paths
    btn_event = button.get("action", {}).get("event", {})
    assert "path" not in str(btn_event.get("context", {}))

    # Simulate client submitting raw values via data snapshot
    raw_submission = {
        "q_1_primary_language": ["python"],
        "q_1_primary_language_writein": "With PyPy support",
        "q_2_target_platforms": ["linux", "macos"],
    }

    result = dispatch_button_click(
        artifacts_dir=artifacts_dir,
        family="questionnaires",
        uuid=q_uuid,
        button_id="submit_btn",
        data=raw_submission,
    )

    # data snapshot contains submitted values
    assert result.data["q_1_primary_language"] == ["python"]
    assert result.data["q_1_primary_language_writein"] == "With PyPy support"
    assert result.data["q_2_target_platforms"] == ["linux", "macos"]

    # state.json strictly contains last_event with data snapshot
    state_data = json.loads((art_dir / "state.json").read_text(encoding="utf-8"))
    assert state_data["last_event"]["data"]["q_1_primary_language"] == ["python"]
    assert state_data["last_event"]["data"]["q_2_target_platforms"] == ["linux", "macos"]

    # answers.md generated for questionnaire
    answers_md = art_dir / "answers.md"
    assert answers_md.is_file()
    answers_content = answers_md.read_text(encoding="utf-8")
    assert "# Stack Questionnaire: user answers" in answers_content
    assert "**Primary language?**" in answers_content
    assert "> Python" in answers_content
    assert "> Other: With PyPy support" in answers_content
    assert "**Target platforms?**" in answers_content
    assert "> Linux" in answers_content
    assert "> macOS" in answers_content


def test_validate_a2ui_surface_valid() -> None:
    manifest = ArtifactManifest(
        name="Valid Surface",
        exposition="embedded",
        blocking=False,
        buttons=[ManifestButton(id="btn-ok", mode="set", clicks=1)],
    )
    components: list[dict[str, Any]] = [
        {
            "id": "root",
            "component": "Column",
            "children": ["title", "picker", "btn-ok"],
        },
        {
            "id": "title",
            "component": "Text",
            "text": "Hello world",
            "variant": "body",
        },
        {
            "id": "picker",
            "component": "ChoicePicker",
            "options": [{"label": "A", "value": "a"}, {"label": "B", "value": "b"}],
            "value": ["a"],
        },
        {
            "id": "btn-ok",
            "component": "Button",
            "child": "btn-label",
            "action": {
                "event": {
                    "name": "submit_ok",
                    "context": {"selection": {"path": "/components/picker/value"}},
                }
            },
        },
        {
            "id": "btn-label",
            "component": "Text",
            "text": "Submit",
        },
    ]

    errors = validate_a2ui_surface(components=components, manifest=manifest)
    assert errors == []


def test_validate_a2ui_surface_structural_and_hierarchy_errors() -> None:
    # 1. Non-list components
    assert "must be a list" in validate_a2ui_surface(components="invalid")[0]

    # 2. Empty list
    assert "cannot be empty" in validate_a2ui_surface(components=[])[0]

    # 3. Non-dict element
    assert "not an object/dict" in validate_a2ui_surface(components=["not_a_dict"])[0]

    # 4. Missing ID is auto-assigned and validates cleanly
    assert validate_a2ui_surface(components=[{"component": "Text", "text": "Hello"}]) == []
    mutations: list[str] = []
    norm = normalize_a2ui_components(
        [{"component": "Text", "text": "Hello"}], mutation_log=mutations
    )
    assert any("Auto-assigned id=" in m for m in mutations)
    assert any(c.get("id") == "text_0" for c in norm)

    # 5. Duplicate ID is deduplicated and validates cleanly
    dup_comps = [
        {"id": "comp1", "component": "Text", "text": "A"},
        {"id": "comp1", "component": "Text", "text": "B"},
    ]
    mutations_dup: list[str] = []
    norm_dup = normalize_a2ui_components(dup_comps, mutation_log=mutations_dup)
    assert any("Deduplicated ID" in m for m in mutations_dup)
    assert len({c["id"] for c in norm_dup if isinstance(c, dict) and "id" in c}) == len(norm_dup)
    assert validate_a2ui_surface(components=dup_comps) == []

    # 6. Unknown component type
    bad_type_comps = [{"id": "bad1", "component": "SuperUnknownWidget"}]
    assert any(
        "Unknown or unsupported component type 'SuperUnknownWidget'" in e
        for e in validate_a2ui_surface(components=bad_type_comps)
    )

    # 7. Dangling child in children
    dangling_children = [
        {"id": "root", "component": "Column", "children": ["missing-child-1"]},
    ]
    assert any(
        "references child 'missing-child-1'" in e
        for e in validate_a2ui_surface(components=dangling_children)
    )

    # 8. Dangling child in child
    dangling_child = [
        {"id": "btn", "component": "Button", "child": "missing-label"},
    ]
    manifest = ArtifactManifest(
        name="Test",
        exposition="embedded",
        buttons=[ManifestButton(id="btn", mode="set", clicks=1)],
    )
    assert any(
        "references child 'missing-label'" in e
        for e in validate_a2ui_surface(components=dangling_child, manifest=manifest)
    )

    # 9. Multiple parents
    multi_parents = [
        {"id": "root1", "component": "Column", "children": ["shared"]},
        {"id": "root2", "component": "Column", "children": ["shared"]},
        {"id": "shared", "component": "Text", "text": "I have two parents"},
    ]
    assert any("multiple parents" in e for e in validate_a2ui_surface(components=multi_parents))

    # 10. Direct self-cycle
    self_cycle = [
        {"id": "loop", "component": "Column", "children": ["loop"]},
    ]
    assert any("Cycle detected" in e for e in validate_a2ui_surface(components=self_cycle))

    # 11. Multi-node cycle
    multi_cycle = [
        {"id": "node_a", "component": "Column", "children": ["node_b"]},
        {"id": "node_b", "component": "Column", "children": ["node_a"]},
    ]
    errs = validate_a2ui_surface(components=multi_cycle)
    assert any("Cycle detected" in e for e in errs)
    assert any("No root component found" in e for e in errs)


def test_validate_a2ui_surface_component_properties_and_buttons() -> None:
    manifest = ArtifactManifest(
        name="Button Check",
        exposition="embedded",
        buttons=[ManifestButton(id="btn-allowed", mode="set", clicks=1)],
    )

    # Text missing text
    t_no_text = [{"id": "t1", "component": "Text"}]
    assert any(
        "text: Expected string, received undefined" in e
        for e in validate_a2ui_surface(components=t_no_text)
    )

    # Text variant is normalized to 'body' without errors
    t_bad_var = [{"id": "t2", "component": "Text", "text": "Hi", "variant": "ultra-mega-bold"}]
    assert validate_a2ui_surface(components=t_bad_var) == []
    normalized = normalize_a2ui_components(t_bad_var)
    t2_comp = next(c for c in normalized if c.get("id") == "t2")
    assert t2_comp["variant"] == "body"

    # Image invalid fit enum is rejected with enum error
    img_bad_fit = [
        {"id": "img2", "component": "Image", "url": "https://example.com/a.png", "fit": "ultra-fit"}
    ]
    assert any(
        "fit: Invalid enum value" in e for e in validate_a2ui_surface(components=img_bad_fit)
    )

    # Image missing url
    img_no_url = [{"id": "img1", "component": "Image"}]
    assert any(
        "url: Expected string, received undefined" in e
        for e in validate_a2ui_surface(components=img_no_url)
    )

    # Icon missing name
    icon_no_name = [{"id": "icon1", "component": "Icon"}]
    assert any(
        "name: Expected string, received undefined" in e
        for e in validate_a2ui_surface(components=icon_no_name)
    )

    # Button not in manifest.buttons
    btn_not_in_manifest = [
        {"id": "btn-unregistered", "component": "Button", "child": "lbl"},
        {"id": "lbl", "component": "Text", "text": "Unregistered"},
    ]
    errs = validate_a2ui_surface(components=btn_not_in_manifest, manifest=manifest)
    assert any(
        "Button 'btn_unregistered' is present in components but is not declared in manifest.buttons"
        in e
        for e in errs
    )

    # Component pointer referencing non-existent component
    bad_comp_pointer = [
        {"id": "lbl", "component": "Text", "text": {"path": "/components/ghost_component/value"}},
    ]
    errs_comp_pointer = validate_a2ui_surface(components=bad_comp_pointer, manifest=manifest)
    assert any(
        "references non-existent component 'ghost_component'" in e for e in errs_comp_pointer
    )


def test_make_artifact_rejects_invalid_surface_and_does_not_store() -> None:
    store = HarnessStore()
    config = _make_agent_config()
    agent = store.create_agent(config=config, name="agent-art-val")
    session = store.create_session(agent_identifier=str(agent.id), name="session-art-val")
    runner = SessionAgentRunner(session=session)

    # Provide components with a dangling child reference
    invalid_components: list[dict[str, Any]] = [
        {
            "id": "root",
            "component": "Column",
            "children": ["non-existent-child-id"],
        }
    ]
    manifest = ArtifactManifest(
        name="Invalid Surface Test",
        exposition="embedded",
        buttons=[],
    )

    result = runner.handle_make_artifact(
        family="custom",
        manifest=manifest,
        components=invalid_components,
        uuid="invalid-art-uuid",
    )

    # Check tool response format: errors and explicit "didnt store" notification
    assert result.startswith("Failed to render A2UI surface. Artifact was not stored.")
    assert (
        "Dangling child reference: component 'root' references child 'non-existent-child-id'"
        in result
    )

    # Check filesystem: directory must NOT be created under artifacts
    from seamus.persistence import get_workspace_manager

    art_dir = (
        get_workspace_manager().get_session_artifacts_dir(session.agent_id, session.id)
        / "custom"
        / "invalid-art-uuid"
    )
    assert not art_dir.exists()

    # Check thread events: ARTIFACT_CREATED must NOT be emitted
    thread = session.get_open_thread()
    assert thread is not None
    created_events = [e for e in thread.events if e.get("type") == "ARTIFACT_CREATED"]
    assert len(created_events) == 0


def test_make_artifact_rejects_malformed_manifest_and_does_not_store() -> None:
    store = HarnessStore()
    config = _make_agent_config()
    agent = store.create_agent(config=config, name="agent-art-manifest")
    session = store.create_session(agent_identifier=str(agent.id), name="session-art-manifest")
    runner = SessionAgentRunner(session=session)

    malformed_manifest = {
        "exposition": "invalid_exposition_mode",  # must be 'tabbed' or 'embedded'
    }
    components = [{"id": "t", "component": "Text", "text": "hello"}]

    result = runner.handle_make_artifact(
        family="custom",
        manifest=malformed_manifest,
        components=components,
        uuid="malformed-manifest-uuid",
    )

    assert result.startswith("Failed to render A2UI surface. Artifact was not stored.")
    assert "Invalid manifest" in result

    from seamus.persistence import get_workspace_manager

    art_dir = (
        get_workspace_manager().get_session_artifacts_dir(session.agent_id, session.id)
        / "custom"
        / "malformed-manifest-uuid"
    )
    assert not art_dir.exists()


def test_make_artifact_stores_valid_surface_and_emits_event() -> None:
    store = HarnessStore()
    config = _make_agent_config()
    agent = store.create_agent(config=config, name="agent-art-valid")
    session = store.create_session(agent_identifier=str(agent.id), name="session-art-valid")
    runner = SessionAgentRunner(session=session)

    manifest = ArtifactManifest(
        name="Valid Artifact",
        exposition="embedded",
        buttons=[ManifestButton(id="btn_ok", mode="set", clicks=1)],
    )
    valid_components: list[dict[str, Any]] = [
        {"id": "root", "component": "Column", "children": ["t", "btn_ok"]},
        {"id": "t", "component": "Text", "text": "Valid message"},
        {
            "id": "btn_ok",
            "component": "Button",
            "child": "btn_lbl",
            "action": {"event": {"name": "btn_click", "context": {}}},
        },
        {"id": "btn_lbl", "component": "Text", "text": "Confirm"},
    ]

    result = runner.handle_make_artifact(
        family="custom",
        manifest=manifest,
        components=valid_components,
        uuid="valid-art-uuid",
    )

    # Returns the UUID
    assert result == "valid-art-uuid"

    # Artifact files are stored on disk
    from seamus.persistence import get_workspace_manager

    art_dir = (
        get_workspace_manager().get_session_artifacts_dir(session.agent_id, session.id)
        / "custom"
        / "valid-art-uuid"
    )
    assert art_dir.exists()
    assert (art_dir / "body.json").exists()
    assert (art_dir / "manifest.json").exists()
    assert (art_dir / "state.json").exists()

    # Thread has ARTIFACT_CREATED event
    thread = session.get_open_thread()
    assert thread is not None
    created_events = [e for e in thread.events if e.get("type") == "ARTIFACT_CREATED"]
    assert len(created_events) == 1
    assert created_events[0]["artifact_id"] == "valid-art-uuid"
    assert created_events[0]["title"] == "Valid Artifact"


def test_artifact_builder_create_artifact_with_validate_surface(tmp_path: Path) -> None:
    manifest = ArtifactManifest(
        name="Test",
        exposition="embedded",
        buttons=[],
    )
    invalid_components: list[dict[str, Any]] = [
        {"id": "root", "component": "Column", "children": ["non_existent_id"]},
    ]

    with pytest.raises(A2UISurfaceValidationError) as exc_info:
        ArtifactBuilder.create_artifact(
            artifacts_dir=tmp_path,
            family="custom",
            manifest=manifest,
            components=invalid_components,
            validate_surface=True,
        )
    assert any("references child 'non_existent_id'" in err for err in exc_info.value.errors)


def test_validate_a2ui_surface_adapts_card_with_title_and_body() -> None:
    card_with_title_and_body = [
        {
            "component": "Card",
            "id": "card_buttons",
            "title": "Buttons",
            "body": [
                {"component": "Button", "text": "Primary", "id": "btn_primary"},
            ],
        }
    ]
    # Loosely normalized: Card adapts into child Column, Button gets child label, etc.
    errors = validate_a2ui_surface(card_with_title_and_body)
    assert errors == []


def test_make_artifact_adapts_card_with_title_and_body_and_stores() -> None:
    store = HarnessStore()
    config = _make_agent_config()
    agent = store.create_agent(config=config, name="agent-card-title-body")
    session = store.create_session(agent_identifier=str(agent.id), name="session-card-title-body")
    runner = SessionAgentRunner(session=session)

    card_payload = [
        {
            "component": "Card",
            "id": "card_buttons",
            "title": "Buttons",
            "body": [
                {"component": "Button", "text": "Primary", "id": "btn_primary"},
            ],
        }
    ]
    manifest = ArtifactManifest(
        name="Card Artifact",
        exposition="embedded",
        buttons=[],
    )

    result = runner.handle_make_artifact(
        family="custom",
        manifest=manifest,
        components=card_payload,
        uuid="card-adapted-uuid",
    )

    assert "card-adapted-uuid" in result
    assert "Notice: Automatically normalized component tree:" in result
    assert "Adapted Card 'card_buttons' with title/body into child Column" in result

    from seamus.persistence import get_workspace_manager

    art_dir = (
        get_workspace_manager().get_session_artifacts_dir(session.agent_id, session.id)
        / "custom"
        / "card-adapted-uuid"
    )
    assert art_dir.exists()
    stored_body = json.loads((art_dir / "body.json").read_text(encoding="utf-8"))
    by_id = {c["id"]: c for c in stored_body}
    assert by_id["card_buttons"]["child"] == "card_buttons_col"
    assert by_id["card_buttons_col"]["component"] == "Column"
    assert "card_buttons_title" in by_id["card_buttons_col"]["children"]
    assert "btn_primary" in by_id["card_buttons_col"]["children"]

    thread = session.get_open_thread()
    assert thread is not None
    created_events = [e for e in thread.events if e.get("type") == "ARTIFACT_CREATED"]
    assert len(created_events) == 1
    assert created_events[0]["artifact_id"] == "card-adapted-uuid"


def test_validate_a2ui_surface_normalizes_choiceset_and_textinput() -> None:
    components: list[dict[str, Any]] = [
        {
            "id": "root",
            "component": "Column",
            "children": ["cs", "ti"],
        },
        {
            "id": "cs",
            "component": "ChoiceSet",
            "choices": ["Option 1", "Option 2"],
            "value": "Option 1",
        },
        {
            "id": "ti",
            "component": "TextInput",
            "placeholder": "Your name",
        },
    ]
    errors = validate_a2ui_surface(components)
    assert errors == []


def test_normalize_a2ui_components_synthesizes_root_column_when_missing() -> None:
    raw_components: list[dict[str, Any]] = [
        {"id": "intro", "component": "Text", "text": "Hello"},
        {
            "id": "btn",
            "component": "Button",
            "child": "lbl",
            "action": {"event": {"name": "click", "context": {}}},
        },
        {"id": "lbl", "component": "Text", "text": "Click"},
    ]
    normalized = normalize_a2ui_components(raw_components)
    # Root component synthesized at index 0
    assert normalized[0]["id"] == "root"
    assert normalized[0]["component"] == "Column"
    assert normalized[0]["children"] == ["intro", "btn"]

    # When root is already present, no second root is synthesized
    with_root: list[dict[str, Any]] = [
        {"id": "root", "component": "Row", "children": ["t1"]},
        {"id": "t1", "component": "Text", "text": "Already has root"},
    ]
    normalized_with_root = normalize_a2ui_components(with_root)
    assert len([c for c in normalized_with_root if c["id"] == "root"]) == 1
    assert normalized_with_root[0]["component"] == "Row"


def test_check_a2ui_surface_warnings_missing_root_multiple_roots() -> None:
    raw_components: list[dict[str, Any]] = [
        {"id": "intro", "component": "Text", "text": "Hello"},
        {
            "id": "btn",
            "component": "Button",
            "child": "lbl",
            "action": {"event": {"name": "click", "context": {}}},
        },
        {"id": "lbl", "component": "Text", "text": "Click"},
    ]
    warnings = check_a2ui_surface_warnings(raw_components)
    assert len(warnings) == 1
    assert "No component with id='root' was provided" in warnings[0]
    assert "multiple disconnected top-level components (intro, btn)" in warnings[0]


def test_check_a2ui_surface_warnings_missing_root_single_root() -> None:
    raw_components: list[dict[str, Any]] = [
        {"id": "main_col", "component": "Column", "children": ["lbl"]},
        {"id": "lbl", "component": "Text", "text": "Inside"},
    ]
    warnings = check_a2ui_surface_warnings(raw_components)
    assert len(warnings) == 1
    assert (
        "Top-level component 'main_col' was wrapped in an auto-synthesized root 'Column'"
        in warnings[0]
    )


def test_check_a2ui_surface_warnings_orphaned_components() -> None:
    raw_components: list[dict[str, Any]] = [
        {"id": "root", "component": "Column", "children": ["c1"]},
        {"id": "c1", "component": "Text", "text": "Connected"},
        {"id": "c2", "component": "Text", "text": "Orphaned"},
    ]
    warnings = check_a2ui_surface_warnings(raw_components)
    assert len(warnings) == 1
    assert "Orphaned component(s) ['c2'] are not reachable from 'root'" in warnings[0]


def test_make_artifact_auto_synthesizes_root_and_returns_warning() -> None:
    store = HarnessStore()
    config = _make_agent_config()
    agent = store.create_agent(config=config, name="agent-warning-showcase")
    session = store.create_session(agent_identifier=str(agent.id), name="session-warning-showcase")
    runner = SessionAgentRunner(session=session)

    # Component tree missing root with multiple disconnected widgets
    components: list[dict[str, Any]] = [
        {"id": "intro", "component": "Text", "text": "Intro text"},
        {
            "id": "ok-btn",
            "component": "Button",
            "child": "ok-lbl",
            "action": {"event": {"name": "ok", "context": {}}},
        },
        {"id": "ok-lbl", "component": "Text", "text": "OK"},
    ]
    manifest = ArtifactManifest(
        name="Showcase Without Root",
        exposition="embedded",
        buttons=[ManifestButton(id="ok-btn", mode="set", clicks=1)],
    )

    result = runner.handle_make_artifact(
        family="custom",
        manifest=manifest,
        components=components,
        uuid="auto-root-uuid",
    )

    # Artifact is stored and created event is emitted
    assert "auto-root-uuid" in result
    assert "Warning: Incomplete A2UI component tree:" in result
    assert "No component with id='root' was provided" in result

    from seamus.persistence import get_workspace_manager

    art_dir = (
        get_workspace_manager().get_session_artifacts_dir(session.agent_id, session.id)
        / "custom"
        / "auto-root-uuid"
    )
    assert art_dir.exists()
    body_data = json.loads((art_dir / "body.json").read_text(encoding="utf-8"))
    # Stored body has synthesized root Column
    assert body_data[0]["id"] == "root"
    assert body_data[0]["component"] == "Column"
    assert body_data[0]["children"] == ["intro", "ok_btn"]

    thread = session.get_open_thread()
    assert thread is not None
    created_events = [e for e in thread.events if e.get("type") == "ARTIFACT_CREATED"]
    assert len(created_events) == 1
    assert created_events[0]["artifact_id"] == "auto-root-uuid"


def test_normalize_a2ui_components_missing_id_auto_assigned() -> None:
    raw = [
        {"component": "Text", "text": "Paragraph 1"},
        {"component": "Text", "text": "Paragraph 2"},
    ]
    mutations: list[str] = []
    norm = normalize_a2ui_components(raw, mutation_log=mutations)
    assert len(norm) == 3  # synthesized root + 2 texts
    assert any("Auto-assigned id='text_0'" in m for m in mutations)
    assert any("Auto-assigned id='text_1'" in m for m in mutations)
    assert any(c.get("id") == "text_0" for c in norm)
    assert any(c.get("id") == "text_1" for c in norm)


def test_normalize_a2ui_components_type_aliases_and_casing() -> None:
    raw = [
        {"id": "t1", "type": "Text", "text": "Using type alias"},
        {"id": "t2", "component_type": "text", "text": "Using component_type alias"},
        {"id": "t3", "componentType": "heading", "text": "Heading alias"},
        {"id": "btn1", "type": "button", "label": "Click me"},
    ]
    mutations: list[str] = []
    norm = normalize_a2ui_components(raw, mutation_log=mutations)
    by_id = {c["id"]: c for c in norm}

    assert by_id["t1"]["component"] == "Text"
    assert by_id["t2"]["component"] == "Text"
    assert by_id["t3"]["component"] == "Text"
    assert by_id["t3"]["variant"] == "body"
    assert by_id["t3"]["text"] == "## Heading alias"
    assert by_id["btn1"]["component"] == "Button"

    assert any("Renamed 'type' ('Text') to 'component'" in m for m in mutations)
    assert any("Renamed 'component_type' ('text') to 'component'" in m for m in mutations)
    assert any("Renamed 'componentType' ('heading') to 'component'" in m for m in mutations)


def test_normalize_a2ui_components_property_inference() -> None:
    raw = [
        {"id": "inferred_text", "text": "Inferred from text property"},
        {"id": "inferred_choice", "options": [{"label": "A", "value": "a"}]},
        {"id": "inferred_col", "children": ["inferred_text"]},
    ]
    mutations: list[str] = []
    norm = normalize_a2ui_components(raw, mutation_log=mutations)
    by_id = {c["id"]: c for c in norm}

    assert by_id["inferred_text"]["component"] == "Text"
    assert by_id["inferred_choice"]["component"] == "ChoicePicker"
    assert by_id["inferred_col"]["component"] == "Column"
    assert any("Inferred component type 'Text'" in m for m in mutations)


def test_normalize_a2ui_components_button_child_and_card_adaptation() -> None:
    raw = [
        {"id": "btn1", "component": "Button", "label": "Save Progress"},
        {"id": "card1", "component": "Card", "title": "Summary", "body": "Card description"},
    ]
    mutations: list[str] = []
    norm = normalize_a2ui_components(raw, mutation_log=mutations)
    by_id = {c["id"]: c for c in norm}

    # Button child was synthesized
    assert "child" in by_id["btn1"]
    child_id = by_id["btn1"]["child"]
    assert child_id in by_id
    assert by_id[child_id]["component"] == "Text"
    assert by_id[child_id]["text"] == "Save Progress"

    # Card child was synthesized as a Column enclosing title & body
    assert "child" in by_id["card1"]
    card_child_id = by_id["card1"]["child"]
    assert card_child_id in by_id
    assert by_id[card_child_id]["component"] == "Column"
    card_children = by_id[card_child_id]["children"]
    assert len(card_children) == 2
    assert by_id[card_children[0]]["text"] == "Summary"
    assert by_id[card_children[1]]["text"] == "Card description"


def test_auto_declare_manifest_buttons() -> None:
    manifest = ArtifactManifest(
        name="Auto Button Decl",
        exposition="embedded",
        buttons=[],
    )
    components = [
        {"id": "btn-auto", "component": "Button", "child": "lbl"},
        {"id": "lbl", "component": "Text", "text": "Auto Declared"},
    ]
    mutations: list[str] = []
    from seamus.harness.artifacts import auto_declare_manifest_buttons

    auto_declare_manifest_buttons(manifest, components, mutation_log=mutations)
    assert any(btn.id == "btn-auto" for btn in manifest.buttons)
    assert any("Auto-declared button 'btn-auto'" in m for m in mutations)


def test_handle_make_artifact_mutation_log_feedback() -> None:
    store = HarnessStore()
    config = _make_agent_config()
    agent = store.create_agent(config=config, name="agent-art-mut")
    session = store.create_session(agent_identifier=str(agent.id), name="session-art-mut")
    runner = SessionAgentRunner(session=session)

    # Agent emits raw components without id on first element, and uses 'type' alias
    raw_components = [
        {"type": "Text", "text": "Intro text"},
        {"id": "submit-btn", "component": "Button", "label": "Submit"},
    ]
    manifest = {
        "name": "Loose Artifact",
        "exposition": "embedded",
        "buttons": [],  # Button not declared
    }

    result = runner.handle_make_artifact(
        family="custom",
        manifest=manifest,
        components=raw_components,
        uuid="mutated-uuid",
    )

    assert "mutated-uuid" in result
    assert "Notice: Automatically normalized component tree:" in result
    assert "Auto-assigned id='text_0'" in result
    assert "Renamed 'type' ('Text') to 'component'" in result
    assert "Normalized component id 'submit-btn' to valid UAX #31 identifier 'submit_btn'" in result
    assert "Synthesized child Text 'submit_btn_label' for Button 'submit_btn'" in result
    assert "Auto-declared button 'submit_btn' in manifest.buttons" in result
    assert "Auto-synthesized root 'Column' container" in result


def test_uax31_identifier_normalization_and_validation() -> None:
    # 1. Hyphenated and special-char IDs normalized to valid UAX #31
    raw = [
        {"id": "card-header", "component": "Text", "text": "Header"},
        {"id": "action.btn", "component": "Button", "child": "action-lbl"},
        {"id": "action-lbl", "component": "Text", "text": "Go"},
    ]
    mutations: list[str] = []
    norm = normalize_a2ui_components(raw, mutation_log=mutations)
    norm_ids = [c["id"] for c in norm]
    assert "card_header" in norm_ids
    assert "action_btn" in norm_ids
    assert "action_lbl" in norm_ids
    btn_comp = next(c for c in norm if c["id"] == "action_btn")
    assert btn_comp["child"] == "action_lbl"
    for c in norm:
        assert c["id"].isidentifier()

    # 2. validate_a2ui_surface accepts normalized identifiers
    errors = validate_a2ui_surface(components=norm)
    assert errors == []


def test_normalize_drops_dynamic_context_preserves_static_context() -> None:
    raw = [
        {
            "id": "btn_submit",
            "component": "Button",
            "title": "Submit",
            "action": {
                "event": {
                    "name": "submit_event",
                    "context": {
                        "approved": True,
                        "dynamic_field": {"path": "/inputs/some_field"},
                        "target_role": "admin",
                    },
                }
            },
        }
    ]
    mutations: list[str] = []
    norm = normalize_a2ui_components(raw, mutation_log=mutations)
    btn = next(c for c in norm if c["id"] == "btn_submit")
    ctx = btn["action"]["event"]["context"]
    assert "approved" in ctx and ctx["approved"] is True
    assert "target_role" in ctx and ctx["target_role"] == "admin"
    assert "dynamic_field" not in ctx
    assert any(
        "Dropped dynamic context pointer '{path: ...}' for key 'dynamic_field'" in m
        for m in mutations
    )


def test_form_answers_markdown_generation(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / "artifacts"
    fields = [
        Question(body="Role", answers=["Developer", "Designer", "Manager"]),
        Question(body="Subscribe to newsletter?", answers=["yes", "no"], multiple_choice=False),
    ]
    form_uuid = FormBuilder.create_form(
        artifacts_dir=artifacts_dir,
        fields=fields,
        title="Account Setup",
    )
    art_dir = artifacts_dir / "forms" / form_uuid
    assert (art_dir / "schema.json").is_file()

    # Dispatch submit with data snapshot and static context
    click_res = dispatch_button_click(
        artifacts_dir=artifacts_dir,
        family="forms",
        uuid=form_uuid,
        button_id="submit_btn",
        data={"f_1_role": ["Developer"], "f_2_subscribe_to_newsletter": ["yes"]},
        context={"approved": True},
        timestamp="2026-11-11T12:00:00+01:00",
    )
    assert click_res.button_id == "submit_btn"
    assert click_res.context == {"approved": True}
    assert click_res.data == {"f_1_role": ["Developer"], "f_2_subscribe_to_newsletter": ["yes"]}

    answers_md = art_dir / "answers.md"
    assert answers_md.is_file()
    text = answers_md.read_text(encoding="utf-8")
    assert "# Account Setup: user answers" in text
    assert "`submitted: 2026-11-11 12:00:00 UTC+01:00`" in text
    assert "**Role**" in text
    assert "> Developer" in text
    assert "**Subscribe to newsletter?**" in text
    assert "> yes" in text
    assert "## Context" in text
    assert '"approved": true' in text


def test_read_artifact_submission_tool_absent() -> None:
    from seamus.harness.inspector import build_agent_inspect_report
    from seamus.harness.store import get_harness_store

    store = get_harness_store()
    config = _make_agent_config()
    agent = store.create_agent(config=config, name="agent-tools-test")
    session = store.create_session(agent_identifier=str(agent.id), name="session-tools-test")
    report = build_agent_inspect_report(str(agent.id), str(session.id))
    tool_names = [t.name for t in report.tools]
    assert "read_artifact_submission" not in tool_names


def test_questionnaire_answers_md_choice_id_and_other_writein(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / "artifacts"
    q = Question(
        body="Which database to use?",
        answers=["PostgreSQL", "SQLite"],
        multiple_choice=False,
        write_in=True,
    )
    q_uuid = QuestionnaireBuilder.create_questionnaire(
        artifacts_dir=artifacts_dir,
        questions=[q],
        title="DB Choice",
    )
    art_dir = artifacts_dir / "questionnaires" / q_uuid
    schema = json.loads((art_dir / "schema.json").read_text(encoding="utf-8"))
    q_info = schema["questions"][0]
    choice_id = q_info["choice_id"]
    writein_id = q_info["writein_id"]

    # Client sends data keyed by payload component IDs (choice_id and writein_id)
    submission_data = {
        choice_id: "other",
        writein_id: "DuckDB",
        "empty_unmapped": "",
        "empty_list_unmapped": [],
        "extra_note": "Production ready",
    }

    dispatch_button_click(
        artifacts_dir=artifacts_dir,
        family="questionnaires",
        uuid=q_uuid,
        button_id="submit_btn",
        data=submission_data,
        timestamp="2026-11-11T10:00:00Z",
    )

    answers_md = art_dir / "answers.md"
    assert answers_md.is_file()
    content = answers_md.read_text(encoding="utf-8")
    assert "**Which database to use?**" in content
    assert "> Other: DuckDB" in content
    assert "> Other\n" not in content  # Replaced, not duplicated
    assert "**extra_note**" in content
    assert "> Production ready" in content
    assert "empty_unmapped" not in content
    assert "empty_list_unmapped" not in content
