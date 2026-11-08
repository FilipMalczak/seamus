"""Formatter for conversation thread history and artifacts into daemon prompt inputs."""

from __future__ import annotations

import json
import re
from typing import Any

from seamus.domain.artifacts import SYNTHETIC_MESSAGE_INDICATOR

SYNTHETIC_CLICK_RE = re.compile(
    rf"{re.escape(SYNTHETIC_MESSAGE_INDICATOR)}\s*"
    r"User clicked\s*['\"]([^'\"]+)['\"]\s*on artifact\s*['\"]([^'\"]+)['\"]"
    r"(?:\s*with payload:\s*(.*))?",
    re.DOTALL,
)


def _get_field(ev: Any, field_name: str, default: Any = None) -> Any:
    """Safely get field from either a Pydantic event object or a dictionary."""
    if isinstance(ev, dict):
        return ev.get(field_name, default)
    return getattr(ev, field_name, default)


def _normalize_event_type(ev: Any) -> str:
    """Extract and normalize event type to uppercase string without enum prefix."""
    raw = _get_field(ev, "type", "")
    if hasattr(raw, "value"):
        raw = raw.value
    raw_str = str(raw)
    if "." in raw_str:
        raw_str = raw_str.split(".")[-1]
    return raw_str.upper()


def format_thread_history(events: list[Any], max_chars: int = 4000) -> str:
    """Format thread events into a clean, concise conversation transcript for naming daemons.

    Presents:
    - User inputs (translating synthetic unblocking messages into artifact action notations).
    - Assistant responses (concatenating text messages and artifact creations).
    """
    if not events:
        return "(empty conversation)"

    turns: list[str] = []
    current_role: str | None = None
    current_text_parts: list[str] = []
    current_artifacts: list[str] = []

    def flush_turn() -> None:
        nonlocal current_role, current_text_parts, current_artifacts
        if not current_role:
            return

        text = "".join(current_text_parts).strip()
        lines: list[str] = []

        if current_role == "user":
            if text:
                m = SYNTHETIC_CLICK_RE.match(text)
                if m:
                    btn, art_id, payload_raw = m.groups()
                    payload_summary = ""
                    if payload_raw:
                        try:
                            payload_data = json.loads(payload_raw.strip())
                            if isinstance(payload_data, dict) and payload_data:
                                payload_summary = f" Payload: {json.dumps(payload_data)}"
                        except Exception:
                            payload_summary = f" Payload: {payload_raw.strip()}"
                    action_line = (
                        f"User: [Artifact Action: '{btn}' on artifact '{art_id}']{payload_summary}"
                    )
                    lines.append(action_line)
                else:
                    lines.append(f"User: {text}")
        else:
            assistant_content: list[str] = []
            if text:
                assistant_content.append(text)
            for art in current_artifacts:
                assistant_content.append(art)
            if assistant_content:
                lines.append(f"Assistant: {' '.join(assistant_content)}")

        if lines:
            turns.append("\n".join(lines))

        current_role = None
        current_text_parts = []
        current_artifacts = []

    for ev in events:
        ev_type = _normalize_event_type(ev)

        if ev_type in ("TEXT_MESSAGE_START", "MESSAGE_START"):
            role_val = _get_field(ev, "role") or "assistant"
            if hasattr(role_val, "value"):
                role_val = role_val.value
            role = str(role_val).lower()
            if current_role and current_role != role:
                flush_turn()
            current_role = role

        elif ev_type in (
            "TEXT_MESSAGE_CONTENT",
            "TEXT_MESSAGE_CHUNK",
            "TEXT_MESSAGE_DELTA",
        ):
            delta = _get_field(ev, "delta") or _get_field(ev, "content", "")
            if delta:
                current_text_parts.append(str(delta))

        elif ev_type in ("TEXT_MESSAGE_END", "MESSAGE_END"):
            # Don't flush immediately if there might be adjacent artifacts or assistant events
            pass

        elif ev_type in ("USER_MESSAGE",):
            flush_turn()
            current_role = "user"
            content = (
                _get_field(ev, "content")
                or _get_field(ev, "message")
                or _get_field(ev, "delta", "")
            )
            if content:
                current_text_parts.append(str(content))
            flush_turn()

        elif ev_type == "ARTIFACT_CREATED":
            if current_role and current_role != "assistant":
                flush_turn()
            current_role = "assistant"
            art_kind = _get_field(ev, "kind", "artifact")
            art_title = _get_field(ev, "title") or _get_field(ev, "artifact_id", "artifact")
            current_artifacts.append(f'[Artifact: {art_kind} "{art_title}"]')

        elif ev_type == "ARTIFACT_INTERACTION":
            if current_role and current_role != "user":
                flush_turn()
            current_role = "user"
            btn = _get_field(ev, "button_id", "action")
            art_uuid = _get_field(ev, "uuid", "")
            ctx = _get_field(ev, "context", {})
            ctx_summary = f" Payload: {json.dumps(ctx)}" if ctx else ""
            current_text_parts.append(f"[Artifact Action: '{btn}' on '{art_uuid}']{ctx_summary}")
            flush_turn()

    flush_turn()

    transcript = "\n\n".join(turns).strip()
    if len(transcript) > max_chars:
        # Keep head and tail of transcript if very long
        half = max_chars // 2
        transcript = transcript[:half] + "\n\n[...]\n\n" + transcript[-half:]

    return transcript or "(empty conversation)"
