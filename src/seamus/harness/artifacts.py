"""Artifact storage, hierarchical resolution, and specialized questionnaire/form/plan generation."""

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

STANDARD_SURFACE_ID = "surface"
BASIC_CATALOG_ID = "https://a2ui.org/specification/v0_9/catalogs/basic/catalog.json"

DEFAULT_CREATE_SURFACE: dict[str, Any] = {
    "version": "v0.9",
    "createSurface": {
        "surfaceId": STANDARD_SURFACE_ID,
        "catalogId": BASIC_CATALOG_ID,
        "sendDataModel": True,
    },
}

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
    """Seed default root and class-level artifact files in the artifacts directory."""
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    root_surface = artifacts_dir / "createSurface.json"
    if not root_surface.exists():
        root_surface.write_text(json.dumps(DEFAULT_CREATE_SURFACE, indent=2), encoding="utf-8")

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
    """Compiles a batch of questions into an A2UI v0.9 updateComponents structure."""

    @staticmethod
    def build_update_components(
        questions: list[QuestionItem],
        title: str = "Questionnaire",
        subtitle: str = "Please provide your answers below.",
        surface_id: str = STANDARD_SURFACE_ID,
    ) -> dict[str, Any]:
        """Construct A2UI v0.9 updateComponents payload for the questionnaire."""
        components: list[dict[str, Any]] = [
            {
                "id": "root",
                "component": "Card",
                "child": "main",
            }
        ]

        main_children: list[str] = []
        submit_context: dict[str, Any] = {}
        seen_ids: set[str] = set()

        for idx, q in enumerate(questions, start=1):
            q_id = q.id or f"q{idx}"
            if q_id in seen_ids:
                raise ValueError(
                    f"Duplicate question id '{q_id}' in questionnaire. Question IDs must be unique."
                )
            seen_ids.add(q_id)
            card_id = f"{q_id}_card"
            content_id = f"{q_id}_content"
            question_id = f"{q_id}_question"
            options_id = f"{q_id}_options"
            other_id = f"{q_id}_other"

            main_children.append(card_id)

            card_children = [question_id, options_id]
            if q.writein:
                card_children.append(other_id)

            components.append(
                {
                    "id": card_id,
                    "component": "Card",
                    "child": content_id,
                }
            )
            components.append(
                {
                    "id": content_id,
                    "component": "Column",
                    "children": card_children,
                    "align": "stretch",
                }
            )
            components.append(
                {
                    "id": question_id,
                    "component": "Text",
                    "text": q.question,
                    "variant": "h3",
                }
            )

            options: list[dict[str, str]] = [
                {"label": ans, "value": _to_option_value(ans)} for ans in q.answers
            ]
            if q.writein and not any(opt["value"] == "other" for opt in options):
                options.append({"label": "Other", "value": "other"})

            components.append(
                {
                    "id": options_id,
                    "component": "ChoicePicker",
                    "variant": "multipleSelection" if q.multiple else "mutuallyExclusive",
                    "displayStyle": "chips",
                    "options": options,
                    "value": {"path": f"/answers/{q_id}"},
                }
            )
            submit_context[q_id] = {"path": f"/answers/{q_id}"}

            if q.writein:
                components.append(
                    {
                        "id": other_id,
                        "component": "TextField",
                        "label": "If other, specify details",
                        "value": {"path": f"/answers/{q_id}Other"},
                        "variant": "shortText",
                    }
                )
                submit_context[f"{q_id}Other"] = {"path": f"/answers/{q_id}Other"}

        main_children.append("submit_button")
        components.append(
            {
                "id": "submit_label",
                "component": "Text",
                "text": "Submit",
            }
        )
        components.append(
            {
                "id": "submit_button",
                "component": "Button",
                "child": "submit_label",
                "variant": "primary",
                "action": {
                    "event": {
                        "name": "submit_questionnaire",
                        "context": submit_context,
                    }
                },
            }
        )

        components.insert(
            1,
            {
                "id": "main",
                "component": "Column",
                "children": main_children,
                "align": "stretch",
            },
        )

        return {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": surface_id,
                "components": components,
            },
        }


class PlanBuilder:
    """Compiles and manages a Markdown Plan artifact as an A2UI v0.9 surface."""

    @staticmethod
    def build_update_components(
        content: str,
        *,
        include_proceed: bool = True,
        surface_id: str = STANDARD_SURFACE_ID,
    ) -> dict[str, Any]:
        """Construct A2UI v0.9 updateComponents payload for a Markdown plan."""
        main_children = ["plan_markdown"]
        if include_proceed:
            main_children.append("proceed_button")

        components: list[dict[str, Any]] = [
            {
                "id": "root",
                "component": "Card",
                "child": "main",
            },
            {
                "id": "main",
                "component": "Column",
                "children": main_children,
                "align": "stretch",
            },
            {
                "id": "plan_markdown",
                "component": "Text",
                "text": content,
                "variant": "body",
            },
        ]

        if include_proceed:
            components.extend(
                [
                    {
                        "id": "proceed_label",
                        "component": "Text",
                        "text": "Proceed",
                    },
                    {
                        "id": "proceed_button",
                        "component": "Button",
                        "child": "proceed_label",
                        "variant": "primary",
                        "action": {
                            "event": {
                                "name": "proceed_plan",
                                "context": {"approved": True},
                            }
                        },
                    },
                ]
            )

        return {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": surface_id,
                "components": components,
            },
        }

    @staticmethod
    def build_update_data_model(
        content: str,
        title: str = "Plan",
        *,
        approved: bool = False,
        surface_id: str = STANDARD_SURFACE_ID,
    ) -> dict[str, Any]:
        """Construct A2UI v0.9 updateDataModel payload for a plan."""
        return {
            "version": "v0.9",
            "updateDataModel": {
                "surfaceId": surface_id,
                "path": "/plan",
                "value": {
                    "title": title,
                    "content": content,
                    "approved": approved,
                },
            },
        }

    @classmethod
    def create_plan(
        cls,
        artifacts_dir: Path,
        plan_id: str,
        content: str,
        title: str = "Plan",
    ) -> Path:
        """Create a new plan artifact instance directory and write manifest and data."""
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
        (inst_dir / "updateDataModel.json").write_text(
            json.dumps(cls.build_update_data_model(content, clean_title, approved=False), indent=2),
            encoding="utf-8",
        )
        (inst_dir / "updateComponents.json").write_text(
            json.dumps(cls.build_update_components(content, include_proceed=True), indent=2),
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

        data_file = inst_dir / "updateDataModel.json"
        if data_file.is_file():
            data_payload = json.loads(data_file.read_text(encoding="utf-8"))
            val = data_payload.get("updateDataModel", {}).get("value", {})
            if isinstance(val, dict):
                if isinstance(val.get("title"), str) and val["title"].strip():
                    title = val["title"].strip()
                if isinstance(val.get("content"), str):
                    return val["content"], title

        comp_file = inst_dir / "updateComponents.json"
        if comp_file.is_file():
            comp_payload = json.loads(comp_file.read_text(encoding="utf-8"))
            comps = comp_payload.get("updateComponents", {}).get("components", [])
            for comp in comps:
                if isinstance(comp, dict) and comp.get("id") == "plan_markdown":
                    return str(comp.get("text", "")), title

        return "", title

    @classmethod
    def update_plan(cls, artifacts_dir: Path, plan_id: str, content: str) -> Path:
        """Overwrite the Markdown content of an existing plan artifact."""
        _, title = cls.read_plan(artifacts_dir, plan_id)
        inst_dir = artifacts_dir / "plans" / plan_id
        (inst_dir / "updateDataModel.json").write_text(
            json.dumps(cls.build_update_data_model(content, title, approved=False), indent=2),
            encoding="utf-8",
        )
        (inst_dir / "updateComponents.json").write_text(
            json.dumps(cls.build_update_components(content, include_proceed=True), indent=2),
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
        (inst_dir / "updateDataModel.json").write_text(
            json.dumps(cls.build_update_data_model(content, title, approved=True), indent=2),
            encoding="utf-8",
        )
        (inst_dir / "updateComponents.json").write_text(
            json.dumps(cls.build_update_components(content, include_proceed=False), indent=2),
            encoding="utf-8",
        )
        return inst_dir

    @classmethod
    def close_plan(cls, artifacts_dir: Path, plan_id: str) -> bool:
        """Write deleteSurface.json to close/discard a plan artifact."""
        inst_dir = artifacts_dir / "plans" / plan_id
        if not inst_dir.is_dir():
            return False
        delete_file = inst_dir / "deleteSurface.json"
        if delete_file.is_file():
            return False
        delete_payload = {
            "version": "v0.9",
            "deleteSurface": {"surfaceId": STANDARD_SURFACE_ID},
        }
        delete_file.write_text(json.dumps(delete_payload, indent=2), encoding="utf-8")
        return True


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
        """Check if artifact is closed via deleteSurface.json strictly at the instance level."""
        instance_delete = self.artifacts_dir / kind / name / "deleteSurface.json"
        if not instance_delete.is_file():
            return False
        try:
            data = json.loads(instance_delete.read_text(encoding="utf-8"))
            return "deleteSurface" in data
        except Exception:
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
        """Load all 4 components (manifest, surface, components, data) and closed status."""
        manifest = self.load_manifest(kind, name)
        is_closed = self.is_closed(kind, name)

        surface_path = self.resolve_file(kind, name, "createSurface.json")
        surface: dict[str, Any] = (
            json.loads(surface_path.read_text(encoding="utf-8"))
            if surface_path
            else DEFAULT_CREATE_SURFACE
        )

        comp_path = self.resolve_file(kind, name, "updateComponents.json")
        components: dict[str, Any] | None = (
            json.loads(comp_path.read_text(encoding="utf-8")) if comp_path else None
        )

        data_path = self.resolve_file(kind, name, "updateDataModel.json")
        data: dict[str, Any] | None = (
            json.loads(data_path.read_text(encoding="utf-8")) if data_path else None
        )

        del_path = self.resolve_file(kind, name, "deleteSurface.json")
        delete_surface: dict[str, Any] | None = None
        if del_path and del_path.is_file():
            try:
                delete_surface = json.loads(del_path.read_text(encoding="utf-8"))
            except Exception:
                delete_surface = None
        elif is_closed:
            delete_surface = {
                "version": "v0.9",
                "deleteSurface": {"surfaceId": STANDARD_SURFACE_ID},
            }

        resolved_title = manifest.title
        if resolved_title is None and isinstance(data, dict):
            val = data.get("updateDataModel", {}).get("value", {})
            if isinstance(val, dict) and isinstance(val.get("title"), str) and val["title"].strip():
                resolved_title = val["title"].strip()
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
            surface=surface,
            components=components,
            data=data,
            delete_surface=delete_surface,
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
