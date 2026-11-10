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
            "variant": {"caption", "body"},
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
        "allowed": {"min", "max", "value", "steps", "label", "checks"},
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

CANONICAL_COMPONENT_MAP: dict[str, str] = {
    "text": "Text",
    "heading": "Text",
    "header": "Text",
    "paragraph": "Text",
    "label": "Text",
    "button": "Button",
    "btn": "Button",
    "column": "Column",
    "col": "Column",
    "row": "Row",
    "card": "Card",
    "divider": "Divider",
    "separator": "Divider",
    "image": "Image",
    "img": "Image",
    "tabs": "Tabs",
    "modal": "Modal",
    "dialog": "Modal",
    "choicepicker": "ChoicePicker",
    "choiceset": "ChoicePicker",
    "select": "ChoicePicker",
    "dropdown": "ChoicePicker",
    "radio": "ChoicePicker",
    "radiogroup": "ChoicePicker",
    "textfield": "TextField",
    "textinput": "TextField",
    "input": "TextField",
    "checkbox": "CheckBox",
    "slider": "Slider",
    "datetimeinput": "DateTimeInput",
    "dateinput": "DateTimeInput",
}

COMPONENT_TYPE_ALIAS_KEYS = ("type", "component_type", "componentType", "widget", "kind")

RELAXED_PATH_PATTERN = re.compile(
    r"^(?:(?:/(?:[^~/]|~[01])*)*|(?:[^~/]|~[01])+(?:/(?:[^~/]|~[01])*)*)$"
)


def _to_valid_uax31_identifier(name: str) -> str:
    """Normalize a string into a valid UAX #31 / Python identifier."""
    if not name:
        return "comp"
    # Replace hyphens and common separators with underscores
    clean = re.sub(r"[-\s\.]+", "_", name.strip())
    # Strip any characters that are not valid in identifiers
    clean = "".join(c if (c.isalnum() or c == "_") else "_" for c in clean)
    # Ensure it starts with a letter or underscore (XID_Start / _)
    if clean and clean[0].isdigit():
        clean = f"_{clean}"
    # Collapse consecutive underscores
    clean = re.sub(r"_+", "_", clean)
    if not clean or not clean.isidentifier():
        clean = f"comp_{clean}" if clean else "comp"
    return clean


def auto_declare_manifest_buttons(
    manifest: ArtifactManifest | dict[str, Any] | None,
    components: list[dict[str, Any]],
    mutation_log: list[str] | None = None,
) -> None:
    """Ensure any Button present in components is declared in manifest.buttons, normalizing IDs."""
    if manifest is None:
        return

    # Normalize existing manifest button IDs to valid UAX #31 identifiers
    if isinstance(manifest, ArtifactManifest):
        for btn in manifest.buttons:
            if not btn.id.isidentifier():
                old_id = btn.id
                btn.id = _to_valid_uax31_identifier(btn.id)
                if mutation_log is not None:
                    mutation_log.append(f"Normalized manifest button id '{old_id}' to '{btn.id}'.")
    elif isinstance(manifest, dict):
        btns = manifest.get("buttons") or []
        if isinstance(btns, list):
            for b in btns:
                if isinstance(b, dict) and "id" in b and isinstance(b["id"], str):
                    if not b["id"].isidentifier():
                        old_id = b["id"]
                        b["id"] = _to_valid_uax31_identifier(b["id"])
                        if mutation_log is not None:
                            mutation_log.append(
                                f"Normalized manifest button id '{old_id}' to '{b['id']}'."
                            )

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

    for comp in components:
        if not isinstance(comp, dict):
            continue
        c_type, _ = _extract_component_type_and_props(comp)
        if c_type == "Button":
            b_id = comp.get("id")
            if isinstance(b_id, str) and b_id not in manifest_button_ids:
                manifest_button_ids.add(b_id)
                if isinstance(manifest, ArtifactManifest):
                    manifest.buttons.append(ManifestButton(id=b_id, mode="set", clicks=1))
                elif isinstance(manifest, dict):
                    if "buttons" not in manifest or not isinstance(manifest["buttons"], list):
                        manifest["buttons"] = []
                    manifest["buttons"].append({"id": b_id, "mode": "set", "clicks": 1})
                if mutation_log is not None:
                    mutation_log.append(f"Auto-declared button '{b_id}' in manifest.buttons.")


def normalize_a2ui_components(
    components: Any,
    mutation_log: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Normalize components into standard A2UI basicCatalog specifications.

    Loosely parses input (handling JSON strings, wrapper dicts, missing IDs,
    type aliases, button label shortcuts, and card adaptations), matching
    the front-end A2UIArtifactRenderer normalizeComponents behavior.
    """

    def record_mutation(msg: str) -> None:
        if mutation_log is not None:
            mutation_log.append(msg)

    raw_list: Any = components
    if isinstance(raw_list, str):
        try:
            raw_list = json.loads(raw_list)
            record_mutation("Parsed component list from JSON string.")
        except Exception:
            return []

    if isinstance(raw_list, dict):
        if "components" in raw_list and isinstance(raw_list["components"], list):
            raw_list = raw_list["components"]
            record_mutation("Extracted component list from dictionary 'components' key.")
        elif "body" in raw_list and isinstance(raw_list["body"], list):
            raw_list = raw_list["body"]
            record_mutation("Extracted component list from dictionary 'body' key.")
        elif "surface" in raw_list and isinstance(raw_list["surface"], dict):
            surf_comps = raw_list["surface"].get("components")
            if isinstance(surf_comps, list):
                raw_list = surf_comps
                record_mutation("Extracted component list from 'surface.components'.")
            else:
                raw_list = [raw_list]
        else:
            raw_list = [raw_list]

    if not isinstance(raw_list, list):
        return []

    existing_ids: set[str] = set()
    for item in raw_list:
        if isinstance(item, dict):
            c_id = item.get("id")
            if isinstance(c_id, str) and c_id.strip():
                existing_ids.add(c_id.strip())

    normalized: list[dict[str, Any]] = []
    extra_components: list[dict[str, Any]] = []
    seen_ids_in_pass: set[str] = set()
    id_remap: dict[str, str] = {}

    for idx, comp in enumerate(raw_list):
        if not isinstance(comp, dict):
            normalized.append(comp)
            continue

        c = dict(comp)

        # 1. Component type alias resolution ("type", "component_type", "componentType", etc.)
        comp_field = c.get("component")
        if not comp_field or not isinstance(comp_field, str):
            for alias_key in COMPONENT_TYPE_ALIAS_KEYS:
                if alias_key in c and isinstance(c[alias_key], str) and c[alias_key].strip():
                    alias_val = c.pop(alias_key)
                    c["component"] = alias_val.strip()
                    record_mutation(
                        f"Renamed '{alias_key}' ('{alias_val}') to 'component' "
                        f"on component at index {idx}."
                    )
                    break

        # Flatten legacy v0.8 nested component wrapping if present (e.g. {"Text": {"text": ...}})
        comp_field = c.get("component")
        if isinstance(comp_field, dict) and len(comp_field) == 1:
            type_name = next(iter(comp_field.keys()))
            props = comp_field[type_name]
            if isinstance(props, dict):
                c = {"id": c.get("id"), "component": type_name, **props}
                record_mutation(
                    f"Flattened nested '{type_name}' definition into component at index {idx}."
                )
        elif comp_field is None:
            for supported in SUPPORTED_COMPONENT_TYPES:
                if supported in c and isinstance(c[supported], dict):
                    props = c.pop(supported)
                    c["component"] = supported
                    c.update(props)
                    record_mutation(
                        f"Flattened nested '{supported}' key into component at index {idx}."
                    )
                    break

        # Property-based component type inference if still missing
        if not c.get("component") or not isinstance(c.get("component"), str):
            inferred: str | None = None
            if "text" in c:
                inferred = "Text"
            elif "options" in c or "choices" in c:
                inferred = "ChoicePicker"
            elif "children" in c:
                inferred = "Column"
            elif "child" in c:
                inferred = "Card"
            elif "url" in c or "src" in c:
                inferred = "Image"
            elif "tabs" in c:
                inferred = "Tabs"
            elif "action" in c:
                inferred = "Button"
            elif "validationRegexp" in c:
                inferred = "TextField"

            if inferred:
                c["component"] = inferred
                record_mutation(
                    f"Inferred component type '{inferred}' from properties at index {idx}."
                )

        # Canonicalize component type (case-insensitive and alias mapping)
        if isinstance(c.get("component"), str):
            orig_type = c["component"]
            canon = CANONICAL_COMPONENT_MAP.get(orig_type.lower())
            if canon:
                if canon != orig_type:
                    c["component"] = canon
                    if orig_type.lower() in ("heading", "header"):
                        c["component"] = "Text"
                        if (
                            "text" in c
                            and isinstance(c["text"], str)
                            and not c["text"].startswith("#")
                        ):
                            c["text"] = f"## {c['text']}"
                        c["variant"] = "body"
                    record_mutation(
                        f"Normalized component type '{orig_type}' to '{canon}' at index {idx}."
                    )

        # 2. ID resolution: Auto-assign ID if missing or empty, normalize to UAX #31
        c_id = c.get("id")
        if not c_id or not isinstance(c_id, str) or not c_id.strip():
            prefix = str(c.get("component") or "comp").lower()
            prefix = _to_valid_uax31_identifier(prefix)
            candidate = f"{prefix}_{idx}"
            counter = 1
            while candidate in existing_ids:
                candidate = f"{prefix}_{idx}_{counter}"
                counter += 1
            existing_ids.add(candidate)
            c["id"] = candidate
            record_mutation(
                f"Auto-assigned id='{candidate}' to component at index {idx} (missing ID)."
            )
        else:
            orig_id = c_id.strip()
            candidate = orig_id
            if not candidate.isidentifier():
                candidate = _to_valid_uax31_identifier(orig_id)
                record_mutation(
                    f"Normalized component id '{orig_id}' to valid UAX #31 identifier "
                    f"'{candidate}'."
                )
                id_remap[orig_id] = candidate

            if candidate in seen_ids_in_pass:
                dedup_cand = f"{candidate}_{idx}"
                counter = 1
                while dedup_cand in existing_ids:
                    dedup_cand = f"{candidate}_{idx}_{counter}"
                    counter += 1
                existing_ids.add(dedup_cand)
                c["id"] = dedup_cand
                id_remap[orig_id] = dedup_cand
                record_mutation(
                    f"Deduplicated ID for component at index {idx} from '{orig_id}' "
                    f"to '{dedup_cand}'."
                )
            else:
                seen_ids_in_pass.add(candidate)
                existing_ids.discard(orig_id)
                existing_ids.add(candidate)
                c["id"] = candidate

        c_type = c.get("component")

        # 3. Component-specific adaptations
        if c_type == "Text":
            variant = c.get("variant")
            text = c.get("text")
            if text is None:
                for text_alias in ("content", "body", "value", "label"):
                    if text_alias in c:
                        text = str(c.pop(text_alias))
                        record_mutation(
                            f"Mapped '{text_alias}' to 'text' on Text component '{c['id']}'."
                        )
                        break

            if variant in {"h1", "h2", "h3", "h4", "h5"}:
                level = int(variant[1])
                prefix = "#" * level + " "
                if isinstance(text, str) and not text.startswith("#"):
                    text = f"{prefix}{text}"
                variant = "body"
                record_mutation(
                    f"Normalized Text variant '{c.get('variant')}' to 'body' "
                    f"with markdown heading on '{c['id']}'."
                )
            elif variant == "bold":
                variant = "body"
                if isinstance(text, str) and not text.startswith("**"):
                    text = f"**{text}**"
                record_mutation(
                    f"Normalized Text variant 'bold' to 'body' with markdown bold on '{c['id']}'."
                )
            elif variant not in {"caption", "body"}:
                if variant is not None:
                    record_mutation(
                        f"Normalized unsupported Text variant '{variant}' to 'body' on '{c['id']}'."
                    )
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
            label = c.get("label") or c.get("placeholder") or c.get("id", "")
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
                record_mutation(f"Auto-generated default action for Button component '{c['id']}'.")

            if not c.get("child") or not isinstance(c.get("child"), str):
                label_text = c.pop("label", None) or c.pop("text", None) or c.pop("title", None)
                if label_text is None:
                    label_text = c["id"]
                btn_label_id = f"{c['id']}_label"
                counter = 1
                while btn_label_id in existing_ids:
                    btn_label_id = f"{c['id']}_label_{counter}"
                    counter += 1
                existing_ids.add(btn_label_id)
                extra_components.append(
                    {"id": btn_label_id, "component": "Text", "text": str(label_text)}
                )
                c["child"] = btn_label_id
                record_mutation(f"Synthesized child Text '{btn_label_id}' for Button '{c['id']}'.")

            normalized.append(c)
            continue

        if c_type == "Card":
            if not c.get("child") or not isinstance(c.get("child"), str):
                if "children" in c and isinstance(c["children"], list):
                    card_children = c.pop("children")
                    if len(card_children) == 1 and isinstance(card_children[0], str):
                        c["child"] = card_children[0]
                        record_mutation(
                            f"Converted Card '{c['id']}' children array to child "
                            f"reference '{c['child']}'."
                        )
                    else:
                        card_col_id = f"{c['id']}_col"
                        counter = 1
                        while card_col_id in existing_ids:
                            card_col_id = f"{c['id']}_col_{counter}"
                            counter += 1
                        existing_ids.add(card_col_id)
                        extra_components.append(
                            {"id": card_col_id, "component": "Column", "children": card_children}
                        )
                        c["child"] = card_col_id
                        record_mutation(
                            f"Synthesized inner Column '{card_col_id}' for Card '{c['id']}'."
                        )
                elif "title" in c or "body" in c or "content" in c:
                    title_val = c.pop("title", None)
                    body_val = c.pop("body", None) or c.pop("content", None)
                    inner_ids: list[str] = []
                    if title_val is not None:
                        t_id = f"{c['id']}_title"
                        counter = 1
                        while t_id in existing_ids:
                            t_id = f"{c['id']}_title_{counter}"
                            counter += 1
                        existing_ids.add(t_id)
                        extra_components.append(
                            {
                                "id": t_id,
                                "component": "Text",
                                "text": str(title_val),
                                "variant": "body",
                            }
                        )
                        inner_ids.append(t_id)
                    if body_val is not None:
                        if isinstance(body_val, list):
                            for b_item in body_val:
                                if isinstance(b_item, dict):
                                    norm_items = normalize_a2ui_components([b_item])
                                    top_children: list[str] = []
                                    if norm_items and norm_items[0].get("id") == "root":
                                        raw_top = norm_items[0].get("children")
                                        if isinstance(raw_top, list):
                                            top_children = [str(x) for x in raw_top]
                                    for ni in norm_items:
                                        if ni.get("id") != "root":
                                            extra_components.append(ni)
                                    for tc in top_children:
                                        if tc not in inner_ids:
                                            inner_ids.append(tc)
                                elif isinstance(b_item, str):
                                    if b_item in existing_ids:
                                        inner_ids.append(b_item)
                                    else:
                                        b_id = f"{c['id']}_item"
                                        counter = 1
                                        while b_id in existing_ids:
                                            b_id = f"{c['id']}_item_{counter}"
                                            counter += 1
                                        existing_ids.add(b_id)
                                        extra_components.append(
                                            {"id": b_id, "component": "Text", "text": b_item}
                                        )
                                        inner_ids.append(b_id)
                        elif isinstance(body_val, str) and body_val in existing_ids:
                            inner_ids.append(body_val)
                        else:
                            b_id = f"{c['id']}_body"
                            counter = 1
                            while b_id in existing_ids:
                                b_id = f"{c['id']}_body_{counter}"
                                counter += 1
                            existing_ids.add(b_id)
                            extra_components.append(
                                {
                                    "id": b_id,
                                    "component": "Text",
                                    "text": str(body_val),
                                    "variant": "body",
                                }
                            )
                            inner_ids.append(b_id)
                    card_col_id = f"{c['id']}_col"
                    counter = 1
                    while card_col_id in existing_ids:
                        card_col_id = f"{c['id']}_col_{counter}"
                        counter += 1
                    existing_ids.add(card_col_id)
                    extra_components.append(
                        {"id": card_col_id, "component": "Column", "children": inner_ids}
                    )
                    c["child"] = card_col_id
                    record_mutation(
                        f"Adapted Card '{c['id']}' with title/body into child "
                        f"Column '{card_col_id}'."
                    )
                else:
                    empty_id = f"{c['id']}_empty"
                    counter = 1
                    while empty_id in existing_ids:
                        empty_id = f"{c['id']}_empty_{counter}"
                        counter += 1
                    existing_ids.add(empty_id)
                    extra_components.append({"id": empty_id, "component": "Text", "text": ""})
                    c["child"] = empty_id
                    record_mutation(f"Defaulted empty child Text for Card '{c['id']}'.")

            normalized.append(c)
            continue

        if c_type in ("Column", "Row"):
            if "children" not in c or not isinstance(c["children"], list):
                if "child" in c and isinstance(c["child"], str):
                    c["children"] = [c.pop("child")]
                    record_mutation(
                        f"Converted singular 'child' to 'children' on {c_type} '{c['id']}'."
                    )
                else:
                    c["children"] = []
                    record_mutation(f"Defaulted missing 'children' to [] on {c_type} '{c['id']}'.")
            normalized.append(c)
            continue

        if c_type == "Image":
            if "src" in c and "url" not in c:
                c["url"] = c.pop("src")
                record_mutation(f"Renamed 'src' to 'url' on Image '{c['id']}'.")
            normalized.append(c)
            continue

        if c_type == "Slider":
            if "step" in c and "steps" not in c:
                c["steps"] = c.pop("step")
                record_mutation(f"Mapped 'step' to 'steps' on Slider '{c['id']}'.")
            normalized.append(c)
            continue

        normalized.append(c)

    normalized.extend(extra_components)

    # Remap any child references if component IDs were normalized or deduplicated
    if id_remap:
        for comp in normalized:
            if not isinstance(comp, dict):
                continue
            child = comp.get("child")
            if isinstance(child, str) and child in id_remap:
                comp["child"] = id_remap[child]
            children = comp.get("children")
            if isinstance(children, list):
                comp["children"] = [
                    id_remap.get(ch, ch) if isinstance(ch, str) else ch for ch in children
                ]
            trigger = comp.get("trigger")
            if isinstance(trigger, str) and trigger in id_remap:
                comp["trigger"] = id_remap[trigger]
            content = comp.get("content")
            if isinstance(content, str) and content in id_remap:
                comp["content"] = id_remap[content]
            tabs = comp.get("tabs")
            if isinstance(tabs, list):
                for tab in tabs:
                    if isinstance(tab, dict) and isinstance(tab.get("child"), str):
                        if tab["child"] in id_remap:
                            tab["child"] = id_remap[tab["child"]]
            action = comp.get("action")
            if isinstance(action, dict):
                event = action.get("event")
                if isinstance(event, dict) and isinstance(event.get("context"), dict):
                    new_ctx: dict[str, Any] = {}
                    for k, v in event["context"].items():
                        new_k = id_remap.get(k, k)
                        if isinstance(v, dict) and "path" in v and isinstance(v["path"], str):
                            p = v["path"]
                            for old_k, new_v in id_remap.items():
                                p = p.replace(f"/{old_k}/", f"/{new_v}/")
                                if p.endswith(f"/{old_k}"):
                                    p = p[: -len(old_k)] + new_v
                            new_ctx[new_k] = {**v, "path": p}
                        else:
                            new_ctx[new_k] = v
                    event["context"] = new_ctx

    # Ensure there is a root component for A2UI MessageProcessor/NodeResolver
    has_root = any(isinstance(c, dict) and c.get("id") == "root" for c in normalized)
    if not has_root and normalized:
        referenced_ids: set[str] = set()
        for c in normalized:
            if not isinstance(c, dict):
                continue
            child = c.get("child")
            if isinstance(child, str):
                referenced_ids.add(child)
            children = c.get("children")
            if isinstance(children, list):
                for ch in children:
                    if isinstance(ch, str):
                        referenced_ids.add(ch)
            trigger = c.get("trigger")
            if isinstance(trigger, str):
                referenced_ids.add(trigger)
            content = c.get("content")
            if isinstance(content, str):
                referenced_ids.add(content)
            tabs = c.get("tabs")
            if isinstance(tabs, list):
                for t in tabs:
                    if isinstance(t, dict) and isinstance(t.get("child"), str):
                        referenced_ids.add(t["child"])

        root_candidates = [
            str(c["id"])
            for c in normalized
            if isinstance(c, dict) and c.get("id") and str(c["id"]) not in referenced_ids
        ]
        if root_candidates:
            normalized.insert(
                0,
                {
                    "id": "root",
                    "component": "Column",
                    "children": root_candidates,
                },
            )
            record_mutation(
                f"Auto-synthesized root 'Column' container enclosing top-level component(s): "
                f"{', '.join(root_candidates)}."
            )

    return normalized


def check_a2ui_surface_warnings(components: Any) -> list[str]:
    """Inspect component definitions and return warnings for statically incomplete structures.

    Warnings do not prevent artifact creation, but alert agents to structural
    omissions such as missing 'root' components, multiple disconnected root widgets,
    or unreachable/orphaned components.
    """
    warnings: list[str] = []
    if not isinstance(components, list) or len(components) == 0:
        return warnings

    component_ids: list[str] = []
    referenced_ids: set[str] = set()

    for comp in components:
        if not isinstance(comp, dict):
            continue
        c_id = comp.get("id")
        if isinstance(c_id, str):
            component_ids.append(c_id)

        child = comp.get("child")
        if isinstance(child, str):
            referenced_ids.add(child)
        children = comp.get("children")
        if isinstance(children, list):
            for ch in children:
                if isinstance(ch, str):
                    referenced_ids.add(ch)
        trigger = comp.get("trigger")
        if isinstance(trigger, str):
            referenced_ids.add(trigger)
        content = comp.get("content")
        if isinstance(content, str):
            referenced_ids.add(content)
        tabs = comp.get("tabs")
        if isinstance(tabs, list):
            for t in tabs:
                if isinstance(t, dict) and isinstance(t.get("child"), str):
                    referenced_ids.add(t["child"])

    roots = [cid for cid in component_ids if cid not in referenced_ids]

    if "root" not in component_ids:
        if len(roots) > 1:
            warnings.append(
                f"No component with id='root' was provided, and multiple disconnected top-level "
                f"components ({', '.join(roots)}) were detected. A root 'Column' container was "
                "automatically synthesized to render them. To have full layout control, define an "
                "explicit root component with id='root' (such as Column or Row) and list these "
                "components in its 'children'."
            )
        elif len(roots) == 1:
            warnings.append(
                f"No component with id='root' was provided. Top-level component '{roots[0]}' "
                "was wrapped in an auto-synthesized root 'Column'. To ensure standard A2UI "
                "rendering, name your top-level container with id='root'."
            )
        else:
            warnings.append(
                "No component with id='root' was provided and no top-level root candidates "
                "were found."
            )
    else:
        # 'root' is defined, check for any orphaned components not reachable from 'root'
        adj: dict[str, list[str]] = {cid: [] for cid in component_ids}
        for comp in components:
            if not isinstance(comp, dict):
                continue
            c_id = comp.get("id")
            if not isinstance(c_id, str):
                continue
            for ch in [comp.get("child"), comp.get("trigger"), comp.get("content")]:
                if isinstance(ch, str) and ch in adj:
                    adj[c_id].append(ch)
            children = comp.get("children")
            if isinstance(children, list):
                for ch in children:
                    if isinstance(ch, str) and ch in adj:
                        adj[c_id].append(ch)
            tabs = comp.get("tabs")
            if isinstance(tabs, list):
                for t in tabs:
                    if (
                        isinstance(t, dict)
                        and isinstance(t.get("child"), str)
                        and t["child"] in adj
                    ):
                        adj[c_id].append(t["child"])

        reachable: set[str] = set()
        queue = ["root"]
        while queue:
            curr = queue.pop(0)
            if curr in reachable:
                continue
            reachable.add(curr)
            for neighbor in adj.get(curr, []):
                if neighbor not in reachable:
                    queue.append(neighbor)

        orphans = [cid for cid in component_ids if cid not in reachable]
        if orphans:
            warnings.append(
                f"Orphaned component(s) {orphans} are not reachable from 'root' and will "
                "not be rendered on the surface."
            )

    return warnings


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
    auto_declare_buttons: bool = False,
) -> list[str]:
    """Validate that the components and manifest form a valid, renderable A2UI surface.

    Returns a list of human-readable error descriptions matching @a2ui/web_core
    validation diagnostics. An empty list signifies a valid surface that can be
    successfully rendered by A2UI.
    """
    errors: list[str] = []

    raw_list: Any = components
    if isinstance(raw_list, str):
        try:
            raw_list = json.loads(raw_list)
        except Exception:
            errors.append(
                f"components must be a list of component objects, got {type(components).__name__}."
            )
            return errors

    if isinstance(raw_list, dict):
        if "components" in raw_list and isinstance(raw_list["components"], list):
            raw_list = raw_list["components"]
        elif "body" in raw_list and isinstance(raw_list["body"], list):
            raw_list = raw_list["body"]

    if not isinstance(raw_list, list):
        errors.append(
            f"components must be a list of component objects, got {type(components).__name__}."
        )
        return errors

    if len(raw_list) == 0:
        errors.append("components list cannot be empty.")
        return errors

    for idx, comp in enumerate(raw_list):
        if not isinstance(comp, dict):
            errors.append(
                f"Component at index {idx} is not an object/dict (got {type(comp).__name__})."
            )
    if errors:
        return errors

    # Normalize components loosely (ChoiceSet -> ChoicePicker, TextInput -> TextField,
    # auto-assign missing IDs, auto-rename type/componentType, synthesize root container, etc.)
    normalized = normalize_a2ui_components(raw_list)
    if not normalized:
        errors.append("components list cannot be empty.")
        return errors

    if auto_declare_buttons and manifest is not None:
        auto_declare_manifest_buttons(manifest, normalized)

    components_by_id = {c["id"]: c for c in normalized if isinstance(c, dict) and "id" in c}
    normalized_ids = set(components_by_id.keys())

    # Component ID validation against UAX #31 identifier syntax
    for c_id in normalized_ids:
        if not c_id.isidentifier():
            errors.append(f"Component id '{c_id}' must be a valid UAX #31 identifier.")

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
    adj: dict[str, list[str]] = {cid: [] for cid in normalized_ids}
    parent_map: dict[str, list[str]] = {cid: [] for cid in normalized_ids}

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
            if ch not in normalized_ids:
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
    color: dict[str, int] = {cid: 0 for cid in normalized_ids}

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

    for node in normalized_ids:
        if color[node] == 0:
            dfs_cycle(node, [])

    # 7. Root existence check
    roots = [cid for cid, parents in parent_map.items() if not parents]
    if len(normalized_ids) > 0 and len(roots) == 0:
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
        norm_manifest_buttons = {b_id.replace("-", "_") for b_id in manifest_button_ids}
        for c_id in normalized_ids:
            c_comp = components_by_id.get(c_id, {})
            c_type, _ = _extract_component_type_and_props(c_comp)
            if c_type == "Button":
                if (
                    c_id not in manifest_button_ids
                    and c_id.replace("-", "_") not in norm_manifest_buttons
                ):
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
                        if target_id not in normalized_ids:
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
                "text": f"## {title}",
                "variant": "body",
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
                    "text": f"**{q.body}**",
                    "variant": "body",
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

        submit_btn_id = "submit_btn"
        submit_label_id = "submit_label"
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
                    id="submit_btn",
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

        submit_btn_id = "submit_btn"
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
                "text": f"# {clean_title}",
                "variant": "body",
            },
            {
                "id": "plan_content",
                "component": "Text",
                "text": content,
            },
            {
                "id": "plan_actions",
                "component": "Row",
                "children": ["review_btn", "proceed_btn"],
            },
            {
                "id": "review_btn",
                "component": "Button",
                "child": "review_label",
                "variant": "default",
                "action": {
                    "event": {
                        "name": "review_plan",
                        "context": {},
                    }
                },
            },
            {
                "id": "review_label",
                "component": "Text",
                "text": "Review",
            },
            {
                "id": "proceed_btn",
                "component": "Button",
                "child": "proceed_label",
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
                "id": "proceed_label",
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
                    id="review_btn",
                    mode="append",
                    clicks="*",
                    unblocking=False,
                    closing=False,
                ),
                ManifestButton(
                    id="proceed_btn",
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
        if b.id == button_id or b.id.replace("-", "_") == button_id.replace("-", "_"):
            btn_config = b
            button_id = b.id
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
