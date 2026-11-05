"""Artifact storage, resolution, and questionnaire/form/plan generation with Adaptive Cards."""

import json
import logging
import re
from pathlib import Path
from typing import Any, Self
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

from seamus.domain.artifacts import (
    ArtifactInfo,
    ArtifactManifest,
    CadenceMode,
    ExpositionMode,
)

logger = logging.getLogger(__name__)

ADAPTIVE_CARD_SCHEMA = "http://adaptivecards.io/schemas/adaptive-card.json"
ADAPTIVE_CARD_VERSION = "1.5"

DEFAULT_QUESTIONNAIRE_MANIFEST: dict[str, Any] = {
    "exposition": "embedded",
    "cadence": "blocking",
}

DEFAULT_FORM_MANIFEST: dict[str, Any] = {
    "exposition": "tabbed",
    "cadence": "nonblocking",
}

DEFAULT_PLAN_MANIFEST: dict[str, Any] = {
    "exposition": "tabbed",
    "cadence": "nonblocking",
}

SUPPORTED_ARTIFACT_KINDS = {"questionnaires", "questionaires", "forms", "plans"}


def seed_default_artifacts(artifacts_dir: Path) -> None:
    """Seed default class-level artifact files in the artifacts directory."""
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    class_defaults: dict[str, dict[str, Any]] = {
        "questionnaires": DEFAULT_QUESTIONNAIRE_MANIFEST,
        "forms": DEFAULT_FORM_MANIFEST,
        "plans": DEFAULT_PLAN_MANIFEST,
    }
    for kind_name, default_manifest in class_defaults.items():
        kind_dir = artifacts_dir / kind_name
        kind_dir.mkdir(parents=True, exist_ok=True)
        class_manifest = kind_dir / "manifest.json"
        if not class_manifest.exists():
            class_manifest.write_text(
                json.dumps(default_manifest, indent=2),
                encoding="utf-8",
            )


def _to_camel_case(s: str) -> str:
    """Convert text into a camelCase identifier slug."""
    clean = re.sub(r"[^a-zA-Z0-9\s_]", "", s)
    words = clean.replace("_", " ").split()
    if not words:
        return f"q_{uuid4().hex[:6]}"
    first = words[0].lower()
    rest = "".join(w.capitalize() for w in words[1:])
    result = first + rest
    if result[0].isdigit():
        result = "q" + result
    return result


def _to_option_value(opt: str) -> str:
    """Normalize option label to lowercase snake_case value."""
    clean = re.sub(r"[^a-zA-Z0-9\s_+]", "", opt)
    val = clean.strip().lower().replace("+", "_").replace(" ", "_")
    return val or "opt"


class QuestionItem(BaseModel):
    """Question item definition for the questionnaire builder."""

    question: str
    answers: list[str]
    multiple: bool = False
    writein: bool = False
    id: str = Field(default="")

    @model_validator(mode="after")
    def _validate_answers_cardinality(self) -> Self:
        min_answers = 1 if (self.writein or self.multiple) else 2
        if len(self.answers) < min_answers:
            if self.multiple:
                msg = (
                    f"Question '{self.question}' with multiple=True requires at least 1 choice in "
                    f"'answers' (got {len(self.answers)})."
                )
            elif self.writein:
                msg = (
                    f"Question '{self.question}' with writein=True requires at least 1 choice in "
                    f"'answers' (got {len(self.answers)})."
                )
            else:
                msg = (
                    f"Question '{self.question}' with writein=False requires at least 2 choices in "
                    f"'answers' (got {len(self.answers)})."
                )
            raise ValueError(msg)
        return self

    def model_post_init(self, __context: Any) -> None:
        if not self.id or not self.id.strip():
            self.id = _to_camel_case(self.question)
        else:
            self.id = self.id.strip()


class QuestionnaireBuilder:
    """Compiles a batch of questions into a Microsoft Adaptive Card (schema v1.5)."""

    @staticmethod
    def build_card(
        questions: list[QuestionItem],
        title: str = "Questionnaire",
        subtitle: str = "Please provide your answers below.",
    ) -> dict[str, Any]:
        """Construct Microsoft Adaptive Card JSON payload for the questionnaire."""
        body: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        for idx, q in enumerate(questions, start=1):
            q_id = q.id or f"q{idx}"
            if q_id in seen_ids:
                raise ValueError(
                    f"Duplicate question id '{q_id}' in questionnaire. Question IDs must be unique."
                )
            seen_ids.add(q_id)

            container_items: list[dict[str, Any]] = [
                {
                    "type": "TextBlock",
                    "text": q.question,
                    "weight": "Bolder",
                    "size": "Medium",
                    "wrap": True,
                }
            ]

            choices = [{"title": ans, "value": _to_option_value(ans)} for ans in q.answers]
            if q.writein and not any(opt["value"] == "other" for opt in choices):
                choices.append({"title": "Other", "value": "other"})

            container_items.append(
                {
                    "type": "Input.ChoiceSet",
                    "id": q_id,
                    "isMultiSelect": q.multiple,
                    "style": "expanded",
                    "choices": choices,
                }
            )

            if q.writein:
                container_items.append(
                    {
                        "type": "Input.Text",
                        "id": f"{q_id}Other",
                        "placeholder": "If other, specify details",
                    }
                )

            body.append(
                {
                    "type": "Container",
                    "id": f"{q_id}_container",
                    "style": "emphasis",
                    "items": container_items,
                    "separator": idx > 1,
                }
            )

        actions = [
            {
                "type": "Action.Submit",
                "title": "Submit",
                "style": "positive",
                "data": {
                    "action": "submit_questionnaire",
                },
            }
        ]

        return {
            "$schema": ADAPTIVE_CARD_SCHEMA,
            "type": "AdaptiveCard",
            "version": ADAPTIVE_CARD_VERSION,
            "body": body,
            "actions": actions,
        }

    @classmethod
    def save_questionnaire(
        cls,
        artifacts_dir: Path,
        questions: list[QuestionItem],
        kind: str = "questionnaires",
        name: str | None = None,
        title: str | None = None,
    ) -> str:
        """Create a new questionnaire or form artifact instance and return its name."""
        seed_default_artifacts(artifacts_dir)
        inst_name = name or str(uuid4())
        inst_dir = artifacts_dir / kind / inst_name
        inst_dir.mkdir(parents=True, exist_ok=True)

        card_payload = cls.build_card(questions, title=title or "Questionnaire")
        card_path = inst_dir / "card.json"
        card_path.write_text(json.dumps(card_payload, indent=2), encoding="utf-8")

        if title or kind in {"forms", "plans"}:
            manifest = ArtifactManifest(
                exposition=(
                    ExpositionMode.TABBED if kind in {"forms", "plans"} else ExpositionMode.EMBEDDED
                ),
                cadence=(
                    CadenceMode.NONBLOCKING if kind in {"forms", "plans"} else CadenceMode.BLOCKING
                ),
                title=title or ("Form" if kind == "forms" else "Questionnaire"),
            )
            manifest_path = inst_dir / "manifest.json"
            manifest_path.write_text(
                manifest.model_dump_json(indent=2, exclude_none=True),
                encoding="utf-8",
            )

        return inst_name


class PlanBuilder:
    """Compiles and manages a Markdown Plan artifact as a Microsoft Adaptive Card (schema v1.5)."""

    @staticmethod
    def build_card(
        content: str,
        title: str = "Plan",
        *,
        include_proceed: bool = True,
        comments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Construct Microsoft Adaptive Card JSON payload for a Markdown plan."""
        body: list[dict[str, Any]] = [
            {
                "type": "Container",
                "id": "plan_header",
                "items": [
                    {
                        "type": "ColumnSet",
                        "columns": [
                            {
                                "type": "Column",
                                "width": "stretch",
                                "items": [
                                    {
                                        "type": "TextBlock",
                                        "text": title,
                                        "weight": "Bolder",
                                        "size": "Large",
                                        "wrap": True,
                                    }
                                ],
                            },
                            {
                                "type": "Column",
                                "width": "auto",
                                "items": [
                                    {
                                        "type": "TextBlock",
                                        "text": (
                                            "Ready to Execute"
                                            if not include_proceed
                                            else "Draft Plan"
                                        ),
                                        "isSubtle": True,
                                        "weight": "Bolder",
                                        "size": "Small",
                                    }
                                ],
                            },
                        ],
                    }
                ],
                "separator": False,
            },
            {
                "type": "Container",
                "id": "plan_content",
                "items": [
                    {
                        "type": "TextBlock",
                        "text": content,
                        "wrap": True,
                    }
                ],
                "separator": True,
            },
            {
                "type": "Container",
                "id": "plan_comments",
                "items": comments or [],
                "separator": True,
            },
        ]

        actions: list[dict[str, Any]] = []
        if include_proceed:
            actions.append(
                {
                    "type": "Action.Submit",
                    "title": "Proceed to Execution",
                    "style": "positive",
                    "data": {
                        "action": "proceed_plan",
                        "approved": True,
                    },
                }
            )

        return {
            "$schema": ADAPTIVE_CARD_SCHEMA,
            "type": "AdaptiveCard",
            "version": ADAPTIVE_CARD_VERSION,
            "body": body,
            "actions": actions,
        }

    @classmethod
    def create_plan(
        cls,
        artifacts_dir: Path,
        plan_id: str,
        content: str,
        title: str = "Plan",
    ) -> Path:
        """Create a new plan artifact instance directory and write manifest and card."""
        seed_default_artifacts(artifacts_dir)
        clean_title = title.strip() or "Plan"
        inst_dir = artifacts_dir / "plans" / plan_id
        inst_dir.mkdir(parents=True, exist_ok=True)

        manifest_payload = {
            "exposition": ExpositionMode.TABBED.value,
            "cadence": CadenceMode.NONBLOCKING.value,
            "title": clean_title,
        }
        (inst_dir / "manifest.json").write_text(
            json.dumps(manifest_payload, indent=2),
            encoding="utf-8",
        )

        card_payload = cls.build_card(content, title=clean_title, include_proceed=True)
        (inst_dir / "card.json").write_text(
            json.dumps(card_payload, indent=2),
            encoding="utf-8",
        )
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
                if isinstance(manifest_data.get("title"), str) and manifest_data["title"].strip():
                    title = manifest_data["title"].strip()
            except Exception:
                pass

        card_file = inst_dir / "card.json"
        if card_file.is_file():
            try:
                card = json.loads(card_file.read_text(encoding="utf-8"))
                for item in card.get("body", []):
                    if item.get("id") == "plan_content":
                        for sub_item in item.get("items", []):
                            if sub_item.get("type") == "TextBlock":
                                return str(sub_item.get("text", "")), title
                    elif item.get("type") == "TextBlock":
                        return str(item.get("text", "")), title
            except Exception:
                pass

        return "", title

    @classmethod
    def update_plan(cls, artifacts_dir: Path, plan_id: str, content: str) -> Path:
        """Overwrite the Markdown content of an existing plan artifact."""
        _, title = cls.read_plan(artifacts_dir, plan_id)
        inst_dir = artifacts_dir / "plans" / plan_id
        card_payload = cls.build_card(content, title=title, include_proceed=True)
        (inst_dir / "card.json").write_text(
            json.dumps(card_payload, indent=2),
            encoding="utf-8",
        )
        return inst_dir

    @classmethod
    def edit_plan(
        cls,
        artifacts_dir: Path,
        plan_id: str,
        old_string: str,
        new_string: str,
    ) -> Path:
        """Perform an exact string replacement on the active plan's Markdown content."""
        if not old_string:
            raise ValueError("old_string must be non-empty.")
        content, _ = cls.read_plan(artifacts_dir, plan_id)
        occurrences = content.count(old_string)
        if occurrences == 0:
            raise ValueError("old_string not found in active plan content.")
        if occurrences > 1:
            raise ValueError(
                f"old_string appears {occurrences} times in active plan content; "
                "include more surrounding context so it matches uniquely."
            )
        updated_content = content.replace(old_string, new_string, 1)
        return cls.update_plan(artifacts_dir, plan_id, updated_content)

    @classmethod
    def approve_plan(cls, artifacts_dir: Path, plan_id: str) -> Path:
        """Mark the plan as approved for Execute phase and strip the Proceed button."""
        content, title = cls.read_plan(artifacts_dir, plan_id)
        inst_dir = artifacts_dir / "plans" / plan_id
        card_payload = cls.build_card(content, title=title, include_proceed=False)
        (inst_dir / "card.json").write_text(
            json.dumps(card_payload, indent=2),
            encoding="utf-8",
        )
        closed_marker = {"closed": True, "approved": True}
        (inst_dir / "closed.json").write_text(
            json.dumps(closed_marker, indent=2),
            encoding="utf-8",
        )
        return inst_dir

    @classmethod
    def close_plan(cls, artifacts_dir: Path, plan_id: str) -> bool:
        """Write closed.json to close/discard a plan artifact."""
        inst_dir = artifacts_dir / "plans" / plan_id
        if not inst_dir.is_dir():
            return False
        closed_file = inst_dir / "closed.json"
        if closed_file.is_file():
            return False
        closed_marker = {"closed": True}
        closed_file.write_text(json.dumps(closed_marker, indent=2), encoding="utf-8")
        return True


def save_submission(artifacts_dir: Path, kind: str, name: str, data: dict[str, Any]) -> None:
    """Save user submission payload and write closed.json marker."""
    inst_dir = artifacts_dir / kind / name
    inst_dir.mkdir(parents=True, exist_ok=True)
    (inst_dir / "submission.json").write_text(
        json.dumps(data, indent=2),
        encoding="utf-8",
    )
    closed_marker = {"closed": True}
    (inst_dir / "closed.json").write_text(
        json.dumps(closed_marker, indent=2),
        encoding="utf-8",
    )


class ArtifactResolver:
    """Resolves and loads artifact files across the 3-tier directory hierarchy."""

    def __init__(self, artifacts_dir: Path) -> None:
        self.artifacts_dir = artifacts_dir

    def resolve_file(self, kind: str, name: str, filename: str) -> Path | None:
        """Find the first existing file traversing: instance -> class -> root."""
        # 1. Instance level: /artifacts/<kind>/<name>/<filename>
        instance_path = self.artifacts_dir / kind / name / filename
        if instance_path.is_file():
            return instance_path

        # 2. Class level: /artifacts/<kind>/<filename>
        class_path = self.artifacts_dir / kind / filename
        if class_path.is_file():
            return class_path

        # 3. Root level: /artifacts/<filename>
        root_path = self.artifacts_dir / filename
        if root_path.is_file():
            return root_path

        return None

    def is_closed(self, kind: str, name: str) -> bool:
        """Check if artifact is closed via closed.json or submission.json at instance level."""
        inst_dir = self.artifacts_dir / kind / name
        closed_file = inst_dir / "closed.json"
        if closed_file.is_file():
            return True
        submission_file = inst_dir / "submission.json"
        if submission_file.is_file():
            return True
        legacy_delete = inst_dir / "deleteSurface.json"
        if legacy_delete.is_file():
            return True
        return False

    def load_manifest(self, kind: str, name: str) -> ArtifactManifest:
        """Load and validate manifest.json following class validation rules."""
        if kind not in SUPPORTED_ARTIFACT_KINDS:
            msg = (
                f"Unsupported artifact kind: '{kind}'. "
                "Supported kinds are questionnaires, forms, and plans."
            )
            raise ValueError(msg)

        default_manifest = (
            ArtifactManifest(exposition=ExpositionMode.TABBED, cadence=CadenceMode.NONBLOCKING)
            if kind in {"forms", "plans"}
            else ArtifactManifest(exposition=ExpositionMode.EMBEDDED, cadence=CadenceMode.BLOCKING)
        )

        # Check class manifest
        class_manifest_path = self.artifacts_dir / kind / "manifest.json"
        class_manifest = (
            ArtifactManifest.model_validate_json(class_manifest_path.read_text(encoding="utf-8"))
            if class_manifest_path.is_file()
            else default_manifest
        )

        # Check instance manifest if customized
        instance_manifest_path = self.artifacts_dir / kind / name / "manifest.json"
        if instance_manifest_path.is_file():
            instance_manifest = ArtifactManifest.model_validate_json(
                instance_manifest_path.read_text(encoding="utf-8")
            )
            if kind in {"questionnaires", "questionaires"}:
                if instance_manifest != class_manifest:
                    msg = (
                        f"Instance manifest at {instance_manifest_path} ({instance_manifest}) "
                        f"does not match class-level manifest ({class_manifest})."
                    )
                    raise ValueError(msg)
            else:
                if instance_manifest.exposition != class_manifest.exposition:
                    msg = (
                        f"Instance manifest exposition at {instance_manifest_path} "
                        f"({instance_manifest.exposition}) does not match class-level "
                        f"exposition ({class_manifest.exposition})."
                    )
                    raise ValueError(msg)
            return instance_manifest

        return class_manifest

    def load_artifact(self, kind: str, name: str) -> ArtifactInfo:
        """Load artifact manifest, card specification, submission data, and closed status."""
        manifest = self.load_manifest(kind, name)
        is_closed = self.is_closed(kind, name)

        card_path = self.resolve_file(kind, name, "card.json")
        card: dict[str, Any] = {}
        if card_path and card_path.is_file():
            try:
                card = json.loads(card_path.read_text(encoding="utf-8"))
            except Exception:
                card = {}

        data_path = self.resolve_file(kind, name, "submission.json")
        data: dict[str, Any] | None = None
        if data_path and data_path.is_file():
            try:
                data = json.loads(data_path.read_text(encoding="utf-8"))
            except Exception:
                data = None
        else:
            legacy_data_path = self.resolve_file(kind, name, "updateDataModel.json")
            if legacy_data_path and legacy_data_path.is_file():
                try:
                    loaded = json.loads(legacy_data_path.read_text(encoding="utf-8"))
                    data = loaded.get("updateDataModel", {}).get("value", loaded)
                except Exception:
                    data = None

        resolved_title = manifest.title
        if resolved_title is None and isinstance(data, dict):
            if isinstance(data.get("title"), str) and data["title"].strip():
                resolved_title = data["title"].strip()
        if resolved_title is None:
            if kind == "plans":
                resolved_title = "Plan"
            elif kind == "forms":
                resolved_title = "Form"

        return ArtifactInfo(
            kind=kind,
            name=name,
            title=resolved_title,
            manifest=manifest,
            is_closed=is_closed,
            card=card,
            data=data,
        )

    def list_artifacts(self) -> list[ArtifactInfo]:
        """Discover all artifact instances in the artifacts directory."""
        if not self.artifacts_dir.is_dir():
            return []

        results: list[ArtifactInfo] = []
        for kind_dir in self.artifacts_dir.iterdir():
            if not kind_dir.is_dir() or kind_dir.name.startswith((".", "_")):
                continue
            kind = kind_dir.name
            if kind not in SUPPORTED_ARTIFACT_KINDS:
                continue
            for instance_dir in kind_dir.iterdir():
                if not instance_dir.is_dir() or instance_dir.name.startswith((".", "_")):
                    continue
                name = instance_dir.name
                try:
                    results.append(self.load_artifact(kind, name))
                except Exception:
                    logger.exception("Failed to load artifact %s/%s", kind, name)

        return results

    def has_open_blocking_artifact(self) -> bool:
        """Return True if any artifact is currently open and has cadence=blocking."""
        for art in self.list_artifacts():
            if not art.is_closed and art.manifest.cadence == CadenceMode.BLOCKING:
                return True
        return False
