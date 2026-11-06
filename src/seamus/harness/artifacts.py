"""Artifact storage, resolution, atomic builders, and click dispatch for A2UI artifacts."""

import json
import logging
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from seamus.domain.artifacts import (
    ArtifactInfo,
    ArtifactManifest,
    ArtifactState,
    ClickResult,
    ManifestButton,
)

logger = logging.getLogger(__name__)

SUPPORTED_ARTIFACT_KINDS = {"questionnaires", "questionaires", "forms", "plans", "custom"}


def seed_default_artifacts(artifacts_dir: Path) -> None:
    """Seed default artifact family directories under /artifacts/."""
    for kind in ("questionnaires", "forms", "plans"):
        (artifacts_dir / kind).mkdir(parents=True, exist_ok=True)


class ArtifactCorruptedError(Exception):
    """Raised when an artifact has a manifest but is missing body.json (INV-ART-003)."""


def _to_snake_id(s: str) -> str:
    """Convert text into a safe lowercase alphanumeric identifier."""
    clean = re.sub(r"[^a-zA-Z0-9\s_]", "", s).strip().lower()
    words = clean.replace("_", " ").split()
    if not words:
        return f"id_{uuid4().hex[:6]}"
    return "_".join(words)


def _to_option_value(opt: str) -> str:
    """Normalize option label to lowercase snake_case value."""
    clean = re.sub(r"[^a-zA-Z0-9\s_+]", "", opt)
    val = clean.strip().lower().replace("+", "_").replace(" ", "_")
    return val or "opt"


class Question(BaseModel):
    """Question item definition for atomic questionnaire and form builders."""

    body: str = Field(description="Question prompt or inquiry body")
    answers: list[str] = Field(description="List of available answer options")
    multiple_choice: bool = Field(default=False, description="Allow selecting multiple answers")


# Backward compatibility alias for QuestionItem
class QuestionItem(BaseModel):
    """Legacy question item alias."""

    question: str
    answers: list[str]
    multiple: bool = False
    writein: bool = False
    id: str = Field(default="")

    def to_question(self) -> Question:
        ans = list(self.answers)
        if self.writein and "Other" not in ans:
            ans.append("Other")
        return Question(body=self.question, answers=ans, multiple_choice=self.multiple)


class ArtifactBuilder:
    """Core atomic generator tool creating /artifacts/<family>/<uuid>/."""

    @staticmethod
    def create_artifact(
        artifacts_dir: Path,
        family: str,
        manifest: ArtifactManifest | dict[str, Any],
        components: list[dict[str, Any]],
        uuid: str | None = None,
    ) -> str:
        """Create a new artifact instance directory and write body, manifest, and state."""
        instance_uuid = uuid or str(uuid4())
        inst_dir = artifacts_dir / family / instance_uuid
        inst_dir.mkdir(parents=True, exist_ok=True)

        if isinstance(manifest, dict):
            manifest_obj = ArtifactManifest.model_validate(manifest)
        else:
            manifest_obj = manifest

        # 1. Write body.json first to satisfy INV-ART-003 co-existence requirement
        body_file = inst_dir / "body.json"
        body_file.write_text(json.dumps(components, indent=2), encoding="utf-8")

        # 2. Write manifest.json
        manifest_file = inst_dir / "manifest.json"
        manifest_file.write_text(
            manifest_obj.model_dump_json(indent=2),
            encoding="utf-8",
        )

        # 3. Initialize state.json derived from manifest buttons
        clicks_left: dict[str, int | Literal["*"]] = {}
        for btn in manifest_obj.buttons:
            clicks_left[btn.id] = btn.clicks

        initial_state = ArtifactState(dataModel={}, clicksLeft=clicks_left)
        state_file = inst_dir / "state.json"
        state_file.write_text(
            initial_state.model_dump_json(indent=2),
            encoding="utf-8",
        )

        return instance_uuid


class QuestionnaireBuilder:
    """Compiles a batch of questions into an atomic embedded blocking questionnaire."""

    @classmethod
    def build_card(
        cls,
        questions: Sequence[Question | QuestionItem],
        title: str = "Questionnaire",
    ) -> dict[str, Any]:
        """Transitional bridge returning components card dict for legacy callers."""
        components = cls._build_components(questions, title)
        return {"components": components}

    @classmethod
    def _build_components(
        cls,
        questions: Sequence[Question | QuestionItem],
        title: str = "Questionnaire",
    ) -> list[dict[str, Any]]:
        components: list[dict[str, Any]] = [
            {
                "id": "root",
                "component": "Column",
                "children": ["title_text"],
            },
            {
                "id": "title_text",
                "component": "Text",
                "text": title,
                "variant": "h2",
            },
        ]

        root_children = ["title_text"]
        submit_context: dict[str, Any] = {}

        for idx, item in enumerate(questions, start=1):
            q = item.to_question() if isinstance(item, QuestionItem) else item
            q_id = f"q_{idx}_{_to_snake_id(q.body)[:24]}"
            q_text_id = f"{q_id}_text"
            q_choice_id = f"{q_id}_choices"

            components.append(
                {
                    "id": q_text_id,
                    "component": "Text",
                    "text": q.body,
                    "variant": "bold",
                }
            )

            choices = [
                {"id": f"{q_id}_opt_{i}", "label": ans, "value": _to_option_value(ans)}
                for i, ans in enumerate(q.answers, start=1)
            ]

            components.append(
                {
                    "id": q_choice_id,
                    "component": "ChoiceSet",
                    "isMultiSelect": q.multiple_choice,
                    "choices": choices,
                    "value": [] if q.multiple_choice else "",
                }
            )

            root_children.extend([q_text_id, q_choice_id])
            submit_context[q_id] = {"path": f"/components/{q_choice_id}/value"}

        submit_btn_id = "submit-btn"
        submit_label_id = "submit-label"
        root_children.append(submit_btn_id)

        components.append(
            {
                "id": submit_btn_id,
                "component": "Button",
                "child": submit_label_id,
                "variant": "primary",
                "action": {
                    "event": {
                        "name": "submit_questionnaire",
                        "context": submit_context,
                    }
                },
            }
        )
        components.append(
            {
                "id": submit_label_id,
                "component": "Text",
                "text": "Submit",
            }
        )

        components[0]["children"] = root_children
        return components

    @classmethod
    def create_questionnaire(
        cls,
        artifacts_dir: Path,
        questions: Sequence[Question | QuestionItem],
        title: str = "Questionnaire",
        uuid: str | None = None,
        blocking: bool = True,
        exposition: Literal["tabbed", "embedded"] = "embedded",
    ) -> str:
        """Create an atomic questionnaire artifact instance."""
        components = cls._build_components(questions, title)
        manifest = ArtifactManifest(
            name=title,
            exposition=exposition,
            blocking=blocking,
            commentable=False,
            buttons=[
                ManifestButton(
                    id="submit-btn",
                    mode="set",
                    clicks=1,
                    unblocking=True,
                    closing=True,
                )
            ],
        )

        return ArtifactBuilder.create_artifact(
            artifacts_dir=artifacts_dir,
            family="questionnaires",
            manifest=manifest,
            components=components,
            uuid=uuid,
        )


class FormBuilder:
    """Compiles a batch of questions into an atomic tabbed non-blocking form."""

    @classmethod
    def create_form(
        cls,
        artifacts_dir: Path,
        fields: Sequence[Question | QuestionItem] | None = None,
        title: str = "Form",
        uuid: str | None = None,
        blocking: bool = False,
        exposition: Literal["tabbed", "embedded"] = "tabbed",
        *,
        questions: Sequence[Question | QuestionItem] | None = None,
    ) -> str:
        """Create an atomic tabbed form artifact instance."""
        items = fields if fields is not None else (questions or [])
        components: list[dict[str, Any]] = [
            {
                "id": "root",
                "component": "Column",
                "children": ["title_text"],
            },
            {
                "id": "title_text",
                "component": "Text",
                "text": title,
                "variant": "h2",
            },
        ]

        root_children = ["title_text"]
        submit_context: dict[str, Any] = {}

        for idx, item in enumerate(items, start=1):
            q = item.to_question() if isinstance(item, QuestionItem) else item
            q_id = f"f_{idx}_{_to_snake_id(q.body)[:24]}"
            q_text_id = f"{q_id}_text"
            q_choice_id = f"{q_id}_choices"

            components.append(
                {
                    "id": q_text_id,
                    "component": "Text",
                    "text": q.body,
                    "variant": "bold",
                }
            )

            choices = [
                {"id": f"{q_id}_opt_{i}", "label": ans, "value": _to_option_value(ans)}
                for i, ans in enumerate(q.answers, start=1)
            ]

            components.append(
                {
                    "id": q_choice_id,
                    "component": "ChoiceSet",
                    "isMultiSelect": q.multiple_choice,
                    "choices": choices,
                    "value": [] if q.multiple_choice else "",
                }
            )

            root_children.extend([q_text_id, q_choice_id])
            submit_context[q_id] = {"path": f"/components/{q_choice_id}/value"}

        submit_btn_id = "submit-btn"
        submit_label_id = "submit-label"
        root_children.append(submit_btn_id)

        components.append(
            {
                "id": submit_btn_id,
                "component": "Button",
                "child": submit_label_id,
                "variant": "primary",
                "action": {
                    "event": {
                        "name": "submit_form",
                        "context": submit_context,
                    }
                },
            }
        )
        components.append(
            {
                "id": submit_label_id,
                "component": "Text",
                "text": "Submit",
            }
        )

        components[0]["children"] = root_children

        manifest = ArtifactManifest(
            name=title,
            exposition=exposition,
            blocking=blocking,
            commentable=False,
            buttons=[
                ManifestButton(
                    id=submit_btn_id,
                    mode="set",
                    clicks=1,
                    unblocking=False,
                    closing=True,
                )
            ],
        )

        return ArtifactBuilder.create_artifact(
            artifacts_dir=artifacts_dir,
            family="forms",
            manifest=manifest,
            components=components,
            uuid=uuid,
        )


class PlanBuilder:
    """Compiles and manages session Plan artifacts in A2UI format with inline commenting."""

    @classmethod
    def create_plan(
        cls,
        artifacts_dir: Path,
        plan_id: str,
        content: str,
        title: str = "Plan",
    ) -> Path:
        """Create a new plan artifact instance directory."""
        clean_title = title.strip() or "Plan"
        inst_dir = artifacts_dir / "plans" / plan_id
        inst_dir.mkdir(parents=True, exist_ok=True)

        components: list[dict[str, Any]] = [
            {
                "id": "root",
                "component": "Column",
                "children": ["plan_header", "plan_content", "review_actions", "plan_actions"],
            },
            {
                "id": "plan_header",
                "component": "Text",
                "text": clean_title,
                "variant": "h1",
            },
            {
                "id": "plan_content",
                "component": "Text",
                "text": content,
            },
            {
                "id": "review_actions",
                "component": "Row",
                "children": ["review-btn"],
            },
            {
                "id": "review-btn",
                "component": "Review",
                "child": "review-label",
                "variant": "secondary",
                "action": {
                    "comments": "push",
                },
            },
            {
                "id": "review-label",
                "component": "Text",
                "text": "Submit Review Comments",
            },
            {
                "id": "plan_actions",
                "component": "Row",
                "children": ["proceed-btn"],
            },
            {
                "id": "proceed-btn",
                "component": "Button",
                "child": "proceed-label",
                "variant": "primary",
                "action": {
                    "event": {
                        "name": "proceed_plan",
                        "context": {
                            "approved": True,
                        },
                    }
                },
            },
            {
                "id": "proceed-label",
                "component": "Text",
                "text": "Proceed to Execution",
            },
        ]

        manifest = ArtifactManifest(
            name=clean_title,
            exposition="tabbed",
            blocking=False,
            commentable=True,
            buttons=[
                ManifestButton(
                    id="proceed-btn",
                    mode="set",
                    clicks=1,
                    unblocking=True,
                    closing=True,
                ),
                ManifestButton(
                    id="review-btn",
                    mode="append",
                    clicks="*",
                    unblocking=False,
                    closing=False,
                ),
            ],
        )

        ArtifactBuilder.create_artifact(
            artifacts_dir=artifacts_dir,
            family="plans",
            manifest=manifest,
            components=components,
            uuid=plan_id,
        )

        # Write canonical plan.md
        (inst_dir / "plan.md").write_text(content, encoding="utf-8")
        return inst_dir

    @classmethod
    def read_plan(cls, artifacts_dir: Path, plan_id: str) -> tuple[str, str]:
        """Return (content, title) of an existing plan artifact."""
        inst_dir = artifacts_dir / "plans" / plan_id
        if not inst_dir.is_dir():
            msg = f"Plan artifact '{plan_id}' does not exist."
            raise ValueError(msg)

        title = "Plan"
        manifest_file = inst_dir / "manifest.json"
        if manifest_file.is_file():
            try:
                manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
                if isinstance(manifest_data.get("name"), str) and manifest_data["name"].strip():
                    title = manifest_data["name"].strip()
                elif isinstance(manifest_data.get("title"), str) and manifest_data["title"].strip():
                    title = manifest_data["title"].strip()
            except Exception:
                pass

        plan_md_file = inst_dir / "plan.md"
        if plan_md_file.is_file():
            try:
                return plan_md_file.read_text(encoding="utf-8"), title
            except Exception:
                pass

        body_file = inst_dir / "body.json"
        if body_file.is_file():
            try:
                body = json.loads(body_file.read_text(encoding="utf-8"))
                for comp in body:
                    if comp.get("id") == "plan_content" and "text" in comp:
                        return str(comp["text"]), title
            except Exception:
                pass

        return "", title

    @classmethod
    def update_plan(cls, artifacts_dir: Path, plan_id: str, content: str) -> Path:
        """Overwrite the Markdown content of an existing plan artifact."""
        _, title = cls.read_plan(artifacts_dir, plan_id)
        return cls.create_plan(artifacts_dir, plan_id, content, title=title)

    @classmethod
    def edit_plan(
        cls,
        artifacts_dir: Path,
        plan_id: str,
        old_string: str,
        new_string: str,
    ) -> Path:
        """Perform exact string replacement on an existing plan artifact."""
        content, title = cls.read_plan(artifacts_dir, plan_id)
        if old_string not in content:
            msg = f"String '{old_string}' not found in active plan."
            raise ValueError(msg)
        if content.count(old_string) > 1:
            msg = (
                f"String '{old_string}' occurs multiple times in active plan. "
                "Please provide unique context."
            )
            raise ValueError(msg)
        new_content = content.replace(old_string, new_string, 1)
        return cls.create_plan(artifacts_dir, plan_id, new_content, title=title)

    @classmethod
    def approve_plan(cls, artifacts_dir: Path, plan_id: str) -> Path:
        """Mark the plan as approved and close it via closed.marker."""
        inst_dir = artifacts_dir / "plans" / plan_id
        inst_dir.mkdir(parents=True, exist_ok=True)
        (inst_dir / "closed.marker").touch(exist_ok=True)
        state_file = inst_dir / "state.json"
        if state_file.is_file():
            try:
                state_data = json.loads(state_file.read_text(encoding="utf-8"))
                clicks = state_data.get("clicksLeft", {})
                clicks["proceed-btn"] = 0
                state_data["clicksLeft"] = clicks
                state_file.write_text(json.dumps(state_data, indent=2), encoding="utf-8")
            except Exception:
                pass
        return inst_dir

    @classmethod
    def close_plan(cls, artifacts_dir: Path, plan_id: str) -> bool:
        """Write closed.marker to close/discard a plan artifact."""
        inst_dir = artifacts_dir / "plans" / plan_id
        if not inst_dir.is_dir():
            return False
        marker = inst_dir / "closed.marker"
        if marker.exists():
            return False
        marker.touch(exist_ok=True)
        return True


def dispatch_button_click(
    artifacts_dir: Path,
    family: str,
    uuid: str,
    button_id: str,
    context: dict[str, Any],
) -> ClickResult:
    """Execute button click logic, update interactions and state, and check closure."""
    inst_dir = artifacts_dir / family / uuid
    if not inst_dir.is_dir():
        msg = f"Artifact '{family}/{uuid}' not found."
        raise ValueError(msg)

    manifest_file = inst_dir / "manifest.json"
    if not manifest_file.is_file():
        msg = f"Artifact '{family}/{uuid}' is missing manifest.json."
        raise ValueError(msg)

    manifest = ArtifactManifest.model_validate_json(manifest_file.read_text(encoding="utf-8"))

    # 1. Whitelist validation
    btn_config: ManifestButton | None = None
    for b in manifest.buttons:
        if b.id == button_id:
            btn_config = b
            break

    if btn_config is None:
        logger.warning(
            "Button '%s' clicked on artifact '%s/%s' is not listed in manifest.buttons. Dropping.",
            button_id,
            family,
            uuid,
        )
        msg = f"Button '{button_id}' is not configured in artifact manifest."
        raise ValueError(msg)

    # 2. State loading & quota validation
    state_file = inst_dir / "state.json"
    clicks_left: dict[str, int | Literal["*"]] = {}
    data_model: dict[str, Any] = {}
    if state_file.is_file():
        try:
            raw_state = json.loads(state_file.read_text(encoding="utf-8"))
            clicks_left = raw_state.get("clicksLeft", {})
            data_model = raw_state.get("dataModel", {})
        except Exception:
            pass

    current_clicks = clicks_left.get(button_id, btn_config.clicks)
    if isinstance(current_clicks, int) and current_clicks <= 0:
        logger.warning(
            "Button '%s' clicked on artifact '%s/%s' has exhausted its quota (%s). Dropping.",
            button_id,
            family,
            uuid,
            current_clicks,
        )
        msg = f"Button '{button_id}' has exhausted its remaining clicks."
        raise ValueError(msg)

    # 3. Persist interaction payload
    interactions_dir = inst_dir / "interactions"
    interactions_dir.mkdir(parents=True, exist_ok=True)
    interaction_file = interactions_dir / f"{button_id}.json"

    if btn_config.mode == "append":
        with interaction_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(context) + "\n")
    else:
        interaction_file.write_text(json.dumps(context, indent=2), encoding="utf-8")

    # 4. Decrement quota if integer
    if isinstance(current_clicks, int):
        clicks_left[button_id] = current_clicks - 1
    else:
        clicks_left[button_id] = current_clicks

    # 5. Accumulate into dataModel
    data_model.update(context)

    # 6. Save updated state.json
    new_state = ArtifactState(dataModel=data_model, clicksLeft=clicks_left)
    state_file.write_text(new_state.model_dump_json(indent=2), encoding="utf-8")

    # 7. Check closing
    if btn_config.closing:
        (inst_dir / "closed.marker").touch(exist_ok=True)

    mtime = interaction_file.stat().st_mtime
    return ClickResult(
        artifact_id=uuid,
        button_id=button_id,
        context=context,
        timestamp=mtime,
    )


class ArtifactResolver:
    """Direct-instance artifact loader and catalog validator."""

    def __init__(self, artifacts_dir: Path) -> None:
        self.artifacts_dir = artifacts_dir

    def is_closed(self, family: str, uuid: str) -> bool:
        """Check if artifact is closed via closed.marker."""
        inst_dir = self.artifacts_dir / family / uuid
        if (inst_dir / "closed.marker").exists():
            return True
        # Backward compatibility for legacy tests
        if (inst_dir / "closed.json").is_file():
            return True
        return False

    def load_artifact(self, family: str, uuid: str) -> ArtifactInfo:
        """Load artifact manifest, body, state, and closed status."""
        inst_dir = self.artifacts_dir / family / uuid
        if not inst_dir.is_dir():
            msg = f"Artifact instance directory '{family}/{uuid}' not found."
            raise ValueError(msg)

        manifest_file = inst_dir / "manifest.json"
        body_file = inst_dir / "body.json"

        # INV-ART-003: body.json must exist if manifest.json exists
        if manifest_file.is_file() and not body_file.is_file():
            msg = (
                f"Artifact '{family}/{uuid}' is corrupted: manifest.json exists without body.json."
            )
            raise ArtifactCorruptedError(msg)

        if not manifest_file.is_file():
            msg = f"Artifact '{family}/{uuid}' is missing manifest.json."
            raise ValueError(msg)

        manifest = ArtifactManifest.model_validate_json(manifest_file.read_text(encoding="utf-8"))

        body: list[dict[str, Any]] = []
        if body_file.is_file():
            try:
                body = json.loads(body_file.read_text(encoding="utf-8"))
            except Exception:
                body = []

        state_file = inst_dir / "state.json"
        state = ArtifactState()
        if state_file.is_file():
            try:
                state = ArtifactState.model_validate_json(state_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        else:
            # Initialize state from manifest if not written yet
            clicks_left: dict[str, int | Literal["*"]] = {b.id: b.clicks for b in manifest.buttons}
            state = ArtifactState(dataModel={}, clicksLeft=clicks_left)

        is_closed = self.is_closed(family, uuid)
        title = manifest.name

        return ArtifactInfo(
            family=family,
            uuid=uuid,
            title=title,
            manifest=manifest,
            body=body,
            state=state,
            is_closed=is_closed,
        )

    def resolve_artifact(self, uuid: str) -> ArtifactInfo | None:
        """Find and load an artifact across any supported family by UUID."""
        if not self.artifacts_dir.is_dir():
            return None
        for family in SUPPORTED_ARTIFACT_KINDS:
            inst_dir = self.artifacts_dir / family / uuid
            if inst_dir.is_dir():
                try:
                    return self.load_artifact(family, uuid)
                except Exception:
                    logger.exception("Failed to load resolved artifact %s/%s", family, uuid)
        return None

    def load_manifest(self, family: str, uuid: str) -> ArtifactManifest:
        """Load the manifest of an artifact instance."""
        inst_dir = self.artifacts_dir / family / uuid
        manifest_file = inst_dir / "manifest.json"
        if not manifest_file.is_file():
            msg = f"Artifact '{family}/{uuid}' manifest not found."
            raise ValueError(msg)
        return ArtifactManifest.model_validate_json(manifest_file.read_text(encoding="utf-8"))

    def resolve_file(self, family: str, uuid: str, filename: str) -> Path | None:
        """Resolve a specific file within an artifact instance directory."""
        path = self.artifacts_dir / family / uuid / filename
        if path.exists():
            return path
        return None

    def list_artifacts(self) -> list[ArtifactInfo]:
        """Discover all artifact instances in the artifacts directory."""
        if not self.artifacts_dir.is_dir():
            return []

        results: list[ArtifactInfo] = []
        for family_dir in self.artifacts_dir.iterdir():
            if not family_dir.is_dir() or family_dir.name.startswith((".", "_")):
                continue
            family = family_dir.name
            if family not in SUPPORTED_ARTIFACT_KINDS:
                continue
            for instance_dir in family_dir.iterdir():
                if not instance_dir.is_dir() or instance_dir.name.startswith((".", "_")):
                    continue
                uuid = instance_dir.name
                try:
                    results.append(self.load_artifact(family, uuid))
                except Exception:
                    logger.exception("Failed to load artifact %s/%s", family, uuid)

        return results

    def has_open_blocking_artifact(self) -> bool:
        """Return True if any artifact is currently open and has blocking=True."""
        for art in self.list_artifacts():
            if not art.is_closed and art.manifest.blocking:
                return True
        return False
