"""Artifact storage, resolution, atomic builders, and click dispatch for A2UI artifacts."""

import json
import logging
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import AliasChoices, BaseModel, Field

from seamus.domain.artifacts import (
    ArtifactInfo,
    ArtifactManifest,
    ArtifactState,
    ClickResult,
    ManifestButton,
)

logger = logging.getLogger(__name__)

SUPPORTED_ARTIFACT_KINDS = {"questionnaires", "questionaires", "forms", "plans", "custom"}

BASIC_CATALOG_COMPONENT_TYPES = {
    "Text",
    "Image",
    "Icon",
    "Video",
    "AudioPlayer",
    "Row",
    "Column",
    "List",
    "Card",
    "Tabs",
    "Modal",
    "Divider",
    "Button",
    "TextField",
    "CheckBox",
    "ChoicePicker",
    "Slider",
    "DateTimeInput",
}

A2UI_ENVELOPE_KEYS: set[str] = {
    "id",
    "component",
    "catalogId",
    "weight",
    "accessibility",
    "metadata",
}

A2UI_COMPONENT_SPECS: dict[str, dict[str, Any]] = {
    "Text": {
        "required": {"text": "string"},
        "allowed": {"text", "variant"},
        "enums": {
            "variant": {"h1", "h2", "h3", "h4", "h5", "caption", "body"},
        },
    },
    "Image": {
        "required": {"url": "string"},
        "allowed": {"url", "description", "fit", "variant"},
        "enums": {
            "fit": {"contain", "cover", "fill", "none", "scaleDown"},
            "variant": {
                "icon",
                "avatar",
                "smallFeature",
                "mediumFeature",
                "largeFeature",
                "header",
            },
        },
    },
    "Icon": {
        "required": {"name": "string"},
        "allowed": {"name"},
    },
    "Video": {
        "required": {"url": "string"},
        "allowed": {"url"},
    },
    "AudioPlayer": {
        "required": {"url": "string"},
        "allowed": {"url", "description"},
    },
    "Row": {
        "required": {"children": "array"},
        "allowed": {"children", "justify", "align"},
        "enums": {
            "justify": {"start", "center", "end", "spaceBetween", "spaceAround", "spaceEvenly"},
            "align": {"start", "center", "end", "stretch", "baseline"},
        },
    },
    "Column": {
        "required": {"children": "array"},
        "allowed": {"children", "justify", "align"},
        "enums": {
            "justify": {"start", "center", "end", "spaceBetween", "spaceAround", "spaceEvenly"},
            "align": {"start", "center", "end", "stretch", "baseline"},
        },
    },
    "List": {
        "required": {"children": "array"},
        "allowed": {"children", "direction", "align"},
        "enums": {
            "direction": {"horizontal", "vertical"},
            "align": {"start", "center", "end", "stretch"},
        },
    },
    "Card": {
        "required": {"child": "string"},
        "allowed": {"child"},
    },
    "Tabs": {
        "required": {"tabs": "array"},
        "allowed": {"tabs"},
    },
    "Modal": {
        "required": {"trigger": "string", "content": "string"},
        "allowed": {"trigger", "content"},
    },
    "Divider": {
        "required": {},
        "allowed": {"axis"},
        "enums": {
            "axis": {"horizontal", "vertical"},
        },
    },
    "Button": {
        "required": {"child": "string", "action": "object"},
        "allowed": {"child", "action", "variant", "checks"},
        "enums": {
            "variant": {"default", "primary", "borderless"},
        },
    },
    "TextField": {
        "required": {"label": "string"},
        "allowed": {"label", "value", "variant", "validationRegexp", "checks"},
        "enums": {
            "variant": {"shortText", "longText", "number", "obscured"},
        },
    },
    "CheckBox": {
        "required": {"label": "string", "value": "boolean"},
        "allowed": {"label", "value", "checks"},
    },
    "ChoicePicker": {
        "required": {"options": "array", "value": "array"},
        "allowed": {"options", "value", "label", "variant", "displayStyle", "filterable", "checks"},
        "enums": {
            "variant": {"multipleSelection", "mutuallyExclusive"},
        },
    },
    "Slider": {
        "required": {"max": "number", "value": "number"},
        "allowed": {"min", "max", "value", "step", "label", "checks"},
    },
    "DateTimeInput": {
        "required": {"value": "string"},
        "allowed": {"value", "enableDate", "enableTime", "min", "max", "label", "checks"},
    },
}

NORMALIZABLE_COMPONENT_TYPES = {
    "ChoiceSet",  # normalizes to ChoicePicker
    "TextInput",  # normalizes to TextField
}

SUPPORTED_COMPONENT_TYPES = BASIC_CATALOG_COMPONENT_TYPES | NORMALIZABLE_COMPONENT_TYPES

RELAXED_PATH_PATTERN = re.compile(
    r"^(?:(?:/(?:[^~/]|~[01])*)*|(?:[^~/]|~[01])+(?:/(?:[^~/]|~[01])*)*)$"
)


def normalize_a2ui_components(components: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize components into standard A2UI basicCatalog specifications.

    Seamlessly adapts legacy or custom shapes (like ChoiceSet -> ChoicePicker,
    TextInput -> TextField, Text variant 'bold' -> Markdown body), matching
    the front-end A2UIArtifactRenderer normalizeComponents behavior.
    """
    normalized: list[dict[str, Any]] = []
    for comp in components:
        if not isinstance(comp, dict):
            normalized.append(comp)
            continue

        c = dict(comp)
        # Flatten legacy v0.8 nested component wrapping if present
        comp_field = c.get("component")
        if isinstance(comp_field, dict) and len(comp_field) == 1:
            type_name = next(iter(comp_field.keys()))
            props = comp_field[type_name]
            if isinstance(props, dict):
                c = {"id": c.get("id"), "component": type_name, **props}
        elif comp_field is None:
            for supported in SUPPORTED_COMPONENT_TYPES:
                if supported in c and isinstance(c[supported], dict):
                    props = c.pop(supported)
                    c["component"] = supported
                    c.update(props)
                    break

        c_type = c.get("component")

        if c_type == "Text":
            variant = c.get("variant")
            text = c.get("text")
            if variant == "bold":
                variant = "body"
                if isinstance(text, str) and not text.startswith("**"):
                    text = f"**{text}**"
            elif variant not in {"h1", "h2", "h3", "h4", "h5", "caption", "body"}:
                variant = "body"
            c["variant"] = variant
            if text is not None:
                c["text"] = text
            normalized.append(c)
            continue

        if c_type in {"ChoiceSet", "ChoicePicker"}:
            is_multi = bool(c.get("isMultiSelect") or c.get("variant") == "multipleSelection")
            raw_opts = c.get("choices") or c.get("options") or []
            options: list[dict[str, str]] = []
            if isinstance(raw_opts, list):
                for opt in raw_opts:
                    if isinstance(opt, dict):
                        lbl = (
                            opt.get("label")
                            or opt.get("text")
                            or opt.get("value")
                            or opt.get("id")
                            or ""
                        )
                        val = opt.get("value") or opt.get("id") or ""
                        options.append({"label": str(lbl), "value": str(val)})
                    else:
                        options.append({"label": str(opt), "value": str(opt)})
            val = c.get("value")
            if isinstance(val, dict) and "path" in val:
                norm_val: Any = val
            elif isinstance(val, list):
                norm_val = [str(x) for x in val]
            elif val not in (None, ""):
                norm_val = [str(val)]
            else:
                norm_val = []

            res = {k: v for k, v in c.items() if k not in {"choices", "isMultiSelect"}}
            res["component"] = "ChoicePicker"
            res["variant"] = "multipleSelection" if is_multi else "mutuallyExclusive"
            res["options"] = options
            res["value"] = norm_val
            normalized.append(res)
            continue

        if c_type in {"TextInput", "TextField"}:
            val = c.get("value")
            if not (isinstance(val, dict) and "path" in val) and val is None:
                val = ""
            label = c.get("label") or c.get("placeholder") or ""
            res = {k: v for k, v in c.items() if k not in {"placeholder"}}
            res["component"] = "TextField"
            res["label"] = label
            res["value"] = val
            normalized.append(res)
            continue

        if c_type == "Button":
            variant = c.get("variant")
            if variant and variant not in {"default", "primary", "borderless"}:
                c["variant"] = "default"
            if not c.get("action"):
                c["action"] = {
                    "event": {
                        "name": str(c.get("id", "button_click")),
                        "context": {},
                    }
                }
            normalized.append(c)
            continue

        normalized.append(c)
    return normalized


def seed_default_artifacts(artifacts_dir: Path) -> None:
    """Seed default artifact family directories under /artifacts/."""
    for kind in ("questionnaires", "forms", "plans"):
        (artifacts_dir / kind).mkdir(parents=True, exist_ok=True)


class ArtifactCorruptedError(Exception):
    """Raised when an artifact has a manifest but is missing body.json (INV-ART-003)."""


class A2UISurfaceValidationError(Exception):
    """Raised when an A2UI surface fails pre-render validation."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


def _extract_component_type_and_props(comp: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Extract component type name and properties dict from component definition."""
    comp_field = comp.get("component")
    if isinstance(comp_field, str):
        return comp_field, comp
    if isinstance(comp_field, dict) and len(comp_field) == 1:
        type_name = next(iter(comp_field.keys()))
        props = comp_field[type_name]
        return type_name, props if isinstance(props, dict) else {}
    for supported in SUPPORTED_COMPONENT_TYPES:
        if supported in comp and isinstance(comp[supported], dict):
            return supported, comp[supported]
    return "", comp


def validate_a2ui_surface(
    components: Any,
    manifest: ArtifactManifest | dict[str, Any] | None = None,
    initial_data: dict[str, Any] | None = None,
) -> list[str]:
    """Validate that the components and manifest form a valid, renderable A2UI surface.

    Returns a list of human-readable error descriptions matching @a2ui/web_core
    validation diagnostics. An empty list signifies a valid surface that can be
    successfully rendered by A2UI.
    """
    errors: list[str] = []

    if not isinstance(components, list):
        errors.append(
            f"components must be a list of component objects, got {type(components).__name__}."
        )
        return errors

    if len(components) == 0:
        errors.append("components list cannot be empty.")
        return errors

    seen_ids: set[str] = set()

    # 1. Structural check: each component must be a dict with a valid ID
    for idx, comp in enumerate(components):
        if not isinstance(comp, dict):
            errors.append(
                f"Component at index {idx} is not an object/dict (got {type(comp).__name__})."
            )
            continue

        c_id = comp.get("id")
        if not c_id or not isinstance(c_id, str):
            errors.append(f"Component at index {idx} is missing a non-empty string 'id'.")
            continue

        if c_id in seen_ids:
            errors.append(f"Duplicate component id '{c_id}' found at index {idx}.")
            continue

        seen_ids.add(c_id)

    if len(seen_ids) != len(components):
        # Already reported dict/id errors
        return errors

    # 2. Normalize components (ChoiceSet -> ChoicePicker, TextInput -> TextField,
    # bold -> body, etc.)
    normalized = normalize_a2ui_components(components)
    components_by_id = {c["id"]: c for c in normalized if isinstance(c, dict) and "id" in c}

    # 3. Schema validation for each component (required properties, allowed envelope,
    # unrecognized keys)
    for c_id, comp in components_by_id.items():
        c_type, _ = _extract_component_type_and_props(comp)
        if not c_type:
            errors.append(f"Component '{c_id}' is missing a valid 'component' type.")
            continue
        if c_type not in BASIC_CATALOG_COMPONENT_TYPES:
            errors.append(
                f"Unknown or unsupported component type '{c_type}' for component '{c_id}'."
            )
            continue

        spec = A2UI_COMPONENT_SPECS.get(c_type, {})
        issues: list[str] = []

        # 3a. Required properties check
        required_fields: dict[str, str] = spec.get("required", {})
        for req_field, exp_type in required_fields.items():
            if req_field not in comp or comp[req_field] is None:
                issues.append(f"{req_field}: Expected {exp_type}, received undefined")
            else:
                val = comp[req_field]
                if exp_type == "string" and not isinstance(val, (str, dict)):
                    issues.append(
                        f"{req_field}: Expected string, received "
                        f"{'array' if isinstance(val, list) else type(val).__name__}"
                    )
                elif exp_type == "array" and not isinstance(val, list):
                    issues.append(
                        f"{req_field}: Expected array, received "
                        f"{'object' if isinstance(val, dict) else type(val).__name__}"
                    )
                elif exp_type == "object" and not isinstance(val, dict):
                    issues.append(
                        f"{req_field}: Expected object, received "
                        f"{'array' if isinstance(val, list) else type(val).__name__}"
                    )
                elif exp_type == "number" and (
                    not isinstance(val, (int, float, dict)) or isinstance(val, bool)
                ):
                    issues.append(f"{req_field}: Expected number, received {type(val).__name__}")
                elif exp_type == "boolean" and not isinstance(val, (bool, dict)):
                    issues.append(f"{req_field}: Expected boolean, received {type(val).__name__}")

        # 3b. Enum values check
        enums: dict[str, set[str]] = spec.get("enums", {})
        for enum_field, allowed_opts in enums.items():
            if enum_field in comp and comp[enum_field] is not None:
                val = comp[enum_field]
                if isinstance(val, str) and val not in allowed_opts:
                    opts_str = " | ".join(sorted(allowed_opts))
                    issues.append(
                        f"{enum_field}: Invalid enum value. Expected {opts_str}, received '{val}'"
                    )

        # 3c. Unrecognized keys check
        allowed_keys = A2UI_ENVELOPE_KEYS | spec.get("allowed", set())
        unrec = [k for k in comp.keys() if k not in allowed_keys]
        if unrec:
            unrec_formatted = ", ".join(f"'{k}'" for k in unrec)
            issues.append(f"root: Unrecognized key(s) in object: {unrec_formatted}")

        if issues:
            errors.append(
                f"Validation failed for component '{c_type}' ({c_id}): {', '.join(issues)}"
            )

    # 4. Extract child references and parent relationships
    adj: dict[str, list[str]] = {cid: [] for cid in seen_ids}
    parent_map: dict[str, list[str]] = {cid: [] for cid in seen_ids}

    for c_id, comp in components_by_id.items():
        c_type, props = _extract_component_type_and_props(comp)
        child_refs: list[str] = []

        if "children" in props:
            children_val = props["children"]
            if isinstance(children_val, list):
                for child_idx, item in enumerate(children_val):
                    if isinstance(item, str):
                        child_refs.append(item)
                    elif isinstance(item, dict) and "componentId" in item:
                        child_refs.append(str(item["componentId"]))
                    else:
                        errors.append(
                            f"Component '{c_id}' children[{child_idx}] is not a valid child "
                            "reference string."
                        )

        if "child" in props:
            child_val = props["child"]
            if isinstance(child_val, str):
                child_refs.append(child_val)
            elif isinstance(child_val, dict) and "componentId" in child_val:
                child_refs.append(str(child_val["componentId"]))

        if c_type == "Tabs" and "tabs" in props:
            tabs_val = props["tabs"]
            if isinstance(tabs_val, list):
                for tab_idx, tab_item in enumerate(tabs_val):
                    if isinstance(tab_item, dict) and "child" in tab_item:
                        tab_child = tab_item["child"]
                        if isinstance(tab_child, str):
                            child_refs.append(tab_child)
                        else:
                            errors.append(
                                f"Component '{c_id}' tabs[{tab_idx}].child must be a string "
                                "component ID."
                            )

        if c_type == "Modal":
            if "content" in props and isinstance(props["content"], str):
                child_refs.append(props["content"])
            if "trigger" in props and isinstance(props["trigger"], str):
                child_refs.append(props["trigger"])

        for ch in child_refs:
            if ch not in seen_ids:
                errors.append(
                    f"Dangling child reference: component '{c_id}' references child '{ch}', "
                    "which does not exist in components."
                )
            else:
                adj[c_id].append(ch)
                parent_map[ch].append(c_id)

    # 5. Check for multiple parents
    for c_id, parents in parent_map.items():
        if len(parents) > 1:
            errors.append(
                f"Component '{c_id}' has multiple parents: {parents}. "
                "In A2UI, each child component must have at most one parent."
            )

    # 6. Cycle detection in component hierarchy
    color: dict[str, int] = {cid: 0 for cid in seen_ids}

    def dfs_cycle(node: str, path: list[str]) -> bool:
        color[node] = 1
        path.append(node)
        for neighbor in adj.get(node, []):
            if neighbor not in color:
                continue
            if color[neighbor] == 1:
                cycle_idx = path.index(neighbor)
                cycle_path = path[cycle_idx:] + [neighbor]
                errors.append(f"Cycle detected in component hierarchy: {' -> '.join(cycle_path)}.")
                return True
            elif color[neighbor] == 0:
                if dfs_cycle(neighbor, path):
                    return True
        path.pop()
        color[node] = 2
        return False

    for node in seen_ids:
        if color[node] == 0:
            dfs_cycle(node, [])

    # 7. Root existence check
    roots = [cid for cid, parents in parent_map.items() if not parents]
    if len(seen_ids) > 0 and len(roots) == 0:
        errors.append(
            "Invalid component hierarchy: No root component found "
            "(all components are children of other components, forming a closed cycle)."
        )

    # 8. Manifest button alignment
    if manifest is not None:
        manifest_button_ids: set[str] = set()
        if isinstance(manifest, ArtifactManifest):
            manifest_button_ids = {btn.id for btn in manifest.buttons}
        elif isinstance(manifest, dict):
            btns = manifest.get("buttons") or []
            if isinstance(btns, list):
                manifest_button_ids = {
                    str(b["id"])
                    for b in btns
                    if isinstance(b, dict) and "id" in b and b["id"] is not None
                }
        for c_id in seen_ids:
            c_comp = components_by_id.get(c_id, {})
            c_type, _ = _extract_component_type_and_props(c_comp)
            if c_type == "Button":
                if c_id not in manifest_button_ids:
                    errors.append(
                        f"Button '{c_id}' is present in components but is not declared "
                        "in manifest.buttons."
                    )

    # 9. Data model and action context pointer checks
    def check_pointers(val: Any, current_path: str = "") -> None:
        if isinstance(val, dict):
            if "path" in val and isinstance(val["path"], str):
                p = val["path"]
                if not RELAXED_PATH_PATTERN.match(p):
                    errors.append(
                        f"Invalid JSON Pointer path syntax '{p}' at {current_path or 'root'}."
                    )
                elif p.startswith("/components/"):
                    parts = p.strip("/").split("/")
                    if len(parts) >= 2:
                        target_id = parts[1]
                        if target_id not in seen_ids:
                            errors.append(
                                f"Action context pointer '{p}' references non-existent "
                                f"component '{target_id}'."
                            )
            for k, v in val.items():
                check_pointers(v, f"{current_path}.{k}" if current_path else k)
        elif isinstance(val, list):
            for i, item in enumerate(val):
                check_pointers(item, f"{current_path}[{i}]")

    for comp in components_by_id.values():
        check_pointers(comp)

    return errors


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
    write_in: bool = Field(
        default=False,
        validation_alias=AliasChoices("write_in", "writein"),
        description="Allow a freeform write-in text response",
    )

    model_config = {"populate_by_name": True}


# Backward compatibility alias for QuestionItem
class QuestionItem(BaseModel):
    """Legacy question item alias."""

    question: str
    answers: list[str]
    multiple: bool = False
    writein: bool = False
    id: str = Field(default="")

    def to_question(self) -> Question:
        return Question(
            body=self.question,
            answers=list(self.answers),
            multiple_choice=self.multiple,
            write_in=self.writein,
        )


class ArtifactBuilder:
    """Core atomic generator tool creating /artifacts/<family>/<uuid>/."""

    @staticmethod
    def create_artifact(
        artifacts_dir: Path,
        family: str,
        manifest: ArtifactManifest | dict[str, Any],
        components: list[dict[str, Any]],
        uuid: str | None = None,
        initial_data: dict[str, Any] | None = None,
        validate_surface: bool = False,
    ) -> str:
        """Create a new artifact instance directory and write body, manifest, and state."""
        if validate_surface:
            errors = validate_a2ui_surface(components, manifest, initial_data)
            if errors:
                raise A2UISurfaceValidationError(errors)

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

        initial_state = ArtifactState(dataModel=initial_data or {}, clicksLeft=clicks_left)
        state_file = inst_dir / "state.json"
        state_file.write_text(
            initial_state.model_dump_json(indent=2),
            encoding="utf-8",
        )

        return instance_uuid


class QuestionnaireBuilder:
    """Compiles a batch of questions into an atomic embedded blocking questionnaire."""

    @classmethod
    def _build_components_and_schema(
        cls,
        questions: Sequence[Question | QuestionItem],
        title: str = "Questionnaire",
        prefix: str = "q",
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
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
        schema_questions: list[dict[str, Any]] = []

        for idx, item in enumerate(questions, start=1):
            q = item.to_question() if isinstance(item, QuestionItem) else item
            q_id = f"{prefix}_{idx}_{_to_snake_id(q.body)[:24]}"
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

            options_map = {_to_option_value(ans): ans for ans in q.answers}
            writein_id = None
            if q.write_in:
                writein_id = f"{q_id}_writein"
                if "other" not in options_map:
                    choices.append({"id": f"{q_id}_opt_other", "label": "Other", "value": "other"})
                    options_map["other"] = "Other"

                components.append(
                    {
                        "id": q_choice_id,
                        "component": "ChoiceSet",
                        "isMultiSelect": q.multiple_choice,
                        "choices": choices,
                        "value": {"path": f"/{q_id}"},
                    }
                )
                components.append(
                    {
                        "id": writein_id,
                        "component": "TextField",
                        "label": "",
                        "placeholder": "Specify other...",
                        "value": {"path": f"/{writein_id}"},
                    }
                )
                root_children.extend([q_text_id, q_choice_id, writein_id])
                submit_context[q_id] = {"path": f"/{q_id}"}
                submit_context[writein_id] = {"path": f"/{writein_id}"}
            else:
                components.append(
                    {
                        "id": q_choice_id,
                        "component": "ChoiceSet",
                        "isMultiSelect": q.multiple_choice,
                        "choices": choices,
                        "value": {"path": f"/{q_id}"},
                    }
                )
                root_children.extend([q_text_id, q_choice_id])
                submit_context[q_id] = {"path": f"/{q_id}"}

            schema_questions.append(
                {
                    "id": q_id,
                    "body": q.body,
                    "multiple_choice": q.multiple_choice,
                    "write_in": q.write_in,
                    "writein_id": writein_id,
                    "options": options_map,
                }
            )

        submit_btn_id = "submit-btn"
        submit_label_id = "submit-label"
        root_children.append(submit_btn_id)

        action_name = "submit_questionnaire" if prefix == "q" else "submit_form"
        components.append(
            {
                "id": submit_btn_id,
                "component": "Button",
                "child": submit_label_id,
                "variant": "primary",
                "action": {
                    "event": {
                        "name": action_name,
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
        return components, schema_questions

    @classmethod
    def build_card(
        cls,
        questions: Sequence[Question | QuestionItem],
        title: str = "Questionnaire",
    ) -> dict[str, Any]:
        """Transitional bridge returning components card dict for legacy callers."""
        components, _ = cls._build_components_and_schema(questions, title, prefix="q")
        return {"components": components}

    @classmethod
    def _build_components(
        cls,
        questions: Sequence[Question | QuestionItem],
        title: str = "Questionnaire",
    ) -> list[dict[str, Any]]:
        components, _ = cls._build_components_and_schema(questions, title, prefix="q")
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
        components, schema_questions = cls._build_components_and_schema(
            questions, title, prefix="q"
        )
        manifest = ArtifactManifest(
            name=title,
            exposition=exposition,
            blocking=blocking,
            commentable=False,
            buttons=[
                ManifestButton(
                    id="submit-btn",
                    mode="set",
                    clicks="*",
                    unblocking=True,
                    closing=True,
                )
            ],
        )

        inst_uuid = ArtifactBuilder.create_artifact(
            artifacts_dir=artifacts_dir,
            family="questionnaires",
            manifest=manifest,
            components=components,
            uuid=uuid,
            initial_data={
                q_info["id"]: [] if q_info["multiple_choice"] else "" for q_info in schema_questions
            },
        )

        # Persist schema.json for translating IDs back to question text and option labels
        schema_file = artifacts_dir / "questionnaires" / inst_uuid / "schema.json"
        schema_file.write_text(
            json.dumps({"family": "questionnaires", "questions": schema_questions}, indent=2),
            encoding="utf-8",
        )

        return inst_uuid


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
        components, schema_questions = QuestionnaireBuilder._build_components_and_schema(
            items, title, prefix="f"
        )

        submit_btn_id = "submit-btn"
        manifest = ArtifactManifest(
            name=title,
            exposition=exposition,
            blocking=blocking,
            commentable=False,
            buttons=[
                ManifestButton(
                    id=submit_btn_id,
                    mode="set",
                    clicks="*",
                    unblocking=False,
                    closing=True,
                )
            ],
        )

        inst_uuid = ArtifactBuilder.create_artifact(
            artifacts_dir=artifacts_dir,
            family="forms",
            manifest=manifest,
            components=components,
            uuid=uuid,
            initial_data={
                q_info["id"]: [] if q_info["multiple_choice"] else "" for q_info in schema_questions
            },
        )

        # Persist schema.json for translating IDs back to field text and option labels
        schema_file = artifacts_dir / "forms" / inst_uuid / "schema.json"
        schema_file.write_text(
            json.dumps({"family": "forms", "questions": schema_questions}, indent=2),
            encoding="utf-8",
        )

        return inst_uuid


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
                "children": ["plan_header", "plan_content", "plan_actions"],
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
                "id": "plan_actions",
                "component": "Row",
                "children": ["review-btn", "proceed-btn"],
            },
            {
                "id": "review-btn",
                "component": "Button",
                "child": "review-label",
                "variant": "default",
                "action": {
                    "event": {
                        "name": "review_plan",
                        "context": {},
                    }
                },
            },
            {
                "id": "review-label",
                "component": "Text",
                "text": "Review",
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
                    id="review-btn",
                    mode="append",
                    clicks="*",
                    unblocking=False,
                    closing=False,
                ),
                ManifestButton(
                    id="proceed-btn",
                    mode="set",
                    clicks="*",
                    unblocking=True,
                    closing=True,
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

    # 3. Translate context if schema.json exists
    raw_context = dict(context)
    translated_context = dict(context)

    schema_file = inst_dir / "schema.json"
    if schema_file.is_file():
        try:
            schema_data = json.loads(schema_file.read_text(encoding="utf-8"))
            translated_context = {}
            questions_list = schema_data.get("questions", [])
            for q_info in questions_list:
                q_id = q_info.get("id")
                q_body = q_info.get("body") or q_id
                options_map = q_info.get("options", {})
                writein_id = q_info.get("writein_id")

                is_multi = q_info.get("multiple_choice", False)
                raw_choice = context.get(q_id)
                choice_translated = None
                if isinstance(raw_choice, list):
                    choice_translated = [options_map.get(v, v) for v in raw_choice if v]
                    if not is_multi:
                        choice_translated = choice_translated[0] if choice_translated else None
                        raw_context[q_id] = raw_choice[0] if raw_choice else ""
                elif raw_choice is not None and str(raw_choice).strip():
                    raw_str = str(raw_choice)
                    choice_translated = options_map.get(raw_str, raw_str)
                    raw_context[q_id] = raw_str

                writein_val = context.get(writein_id) if writein_id else None
                if writein_val is not None:
                    writein_val = str(writein_val).strip()

                if writein_val:
                    if choice_translated:
                        translated_context[q_body] = {
                            "selection": choice_translated,
                            "write_in": writein_val,
                        }
                    else:
                        translated_context[q_body] = {"write_in": writein_val}
                elif choice_translated is not None:
                    translated_context[q_body] = choice_translated

            # Include any remaining keys not mapped to questions
            all_known = {
                k
                for q_info in questions_list
                for k in (q_info.get("id"), q_info.get("writein_id"))
                if k
            }
            for k, v in context.items():
                if k not in all_known:
                    translated_context[k] = v
        except Exception:
            logger.exception("Failed to translate click context using schema.json")
            translated_context = dict(context)

    # 4. Persist interaction payload
    interactions_dir = inst_dir / "interactions"
    interactions_dir.mkdir(parents=True, exist_ok=True)
    interaction_file = interactions_dir / f"{button_id}.json"

    saved_payload = {
        **translated_context,
    }

    if btn_config.mode == "append":
        with interaction_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(saved_payload) + "\n")
    else:
        interaction_file.write_text(json.dumps(saved_payload, indent=2), encoding="utf-8")

    # 5. Decrement quota if integer
    if isinstance(current_clicks, int):
        clicks_left[button_id] = current_clicks - 1
    else:
        clicks_left[button_id] = current_clicks

    # 6. Accumulate into dataModel (component paths only, avoiding duplicate text keys)
    data_model.update(raw_context)

    # 7. Save updated state.json
    new_state = ArtifactState(dataModel=data_model, clicksLeft=clicks_left)
    state_file.write_text(new_state.model_dump_json(indent=2), encoding="utf-8")

    # 8. Check closing
    if btn_config.closing:
        (inst_dir / "closed.marker").touch(exist_ok=True)

    mtime = interaction_file.stat().st_mtime
    return ClickResult(
        artifact_id=uuid,
        button_id=button_id,
        context=translated_context,
        raw_context=raw_context,
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
