"""Artifact storage, hierarchical resolution, and specialized questionnaire generation."""

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

SUPPORTED_ARTIFACT_KINDS = {"questionnaires", "questionaires"}


def seed_default_artifacts(artifacts_dir: Path) -> None:
    """Seed default root and class-level artifact files in the artifacts directory."""
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    root_surface = artifacts_dir / "createSurface.json"
    if not root_surface.exists():
        root_surface.write_text(json.dumps(DEFAULT_CREATE_SURFACE, indent=2), encoding="utf-8")

    questionnaires_dir = artifacts_dir / "questionnaires"
    questionnaires_dir.mkdir(parents=True, exist_ok=True)
    class_manifest = questionnaires_dir / "manifest.json"
    if not class_manifest.exists():
        class_manifest.write_text(
            json.dumps(DEFAULT_QUESTIONNAIRE_MANIFEST, indent=2), encoding="utf-8"
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
    writein: bool = False
    id: str = Field(default="")

    @model_validator(mode="after")
    def _validate_answers_cardinality(self) -> Self:
        min_answers = 1 if self.writein else 2
        if len(self.answers) < min_answers:
            if self.writein:
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
        if not self.id:
            self.id = _to_camel_case(self.question)


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

        main_children: list[str] = ["title", "subtitle"]

        components.append(
            {
                "id": "title",
                "component": "Text",
                "text": f"# {title}",
                "variant": "h2",
            }
        )
        components.append(
            {
                "id": "subtitle",
                "component": "Text",
                "text": subtitle,
                "variant": "body",
            }
        )

        submit_context: dict[str, Any] = {}

        for idx, q in enumerate(questions, start=1):
            q_id = q.id or f"q{idx}"
            card_id = f"{q_id}_card"
            content_id = f"{q_id}_content"
            question_id = f"{q_id}_question"
            options_id = f"{q_id}_options"
            other_id = f"{q_id}_other"
            divider_id = f"divider_{idx}"

            main_children.append(card_id)
            if idx < len(questions):
                main_children.append(divider_id)
                components.append(
                    {
                        "id": divider_id,
                        "component": "Divider",
                        "axis": "horizontal",
                    }
                )

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
                    "text": f"### {idx}. {q.question}",
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
                    "label": q.question,
                    "variant": "mutuallyExclusive",
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
            msg = f"Unsupported artifact kind: '{kind}'. Only questionnaires are supported."
            raise ValueError(msg)

        # Check class manifest
        class_manifest_path = self.artifacts_dir / kind / "manifest.json"
        class_manifest = (
            ArtifactManifest.model_validate_json(class_manifest_path.read_text(encoding="utf-8"))
            if class_manifest_path.is_file()
            else ArtifactManifest(exposition=ExpositionMode.EMBEDDED, cadence=CadenceMode.BLOCKING)
        )

        # Check instance manifest if customized
        instance_manifest_path = self.artifacts_dir / kind / name / "manifest.json"
        if instance_manifest_path.is_file():
            instance_manifest = ArtifactManifest.model_validate_json(
                instance_manifest_path.read_text(encoding="utf-8")
            )
            # Questionnaire customization must match class-level manifest
            if instance_manifest != class_manifest:
                msg = (
                    f"Instance manifest at {instance_manifest_path} ({instance_manifest}) "
                    f"does not match class-level manifest ({class_manifest})."
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

        return ArtifactInfo(
            kind=kind,
            name=name,
            manifest=manifest,
            is_closed=is_closed,
            surface=surface,
            components=components,
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
