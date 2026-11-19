"""Message assembly, bubble extraction, and pagination for Seamus conversations."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Literal

from seamus.server.schemas import (
    ChatMessageResponse,
    MessagePartSchema,
    PaginatedMessagesResponse,
    ThreadTransitionInfoSchema,
    ToolCallRecordSchema,
)


def _format_timestamp(raw: Any) -> str:
    """Format any timestamp value into an ISO8601 string."""
    if isinstance(raw, (int, float)):
        # If milliseconds (common in JS/timestamps > 1e11)
        if raw > 1e11:
            raw = raw / 1000.0
        return datetime.fromtimestamp(raw, tz=UTC).isoformat()
    if isinstance(raw, str) and raw:
        return raw
    return datetime.now(UTC).isoformat()


def aggregate_events_to_chat_messages(events: list[Any]) -> list[ChatMessageResponse]:
    """Aggregate a chronological stream of raw AG-UI events into structured ChatMessages.

    Handles text chunks, streaming reasoning, tool calls, results, and thread transitions.
    """
    messages: list[ChatMessageResponse] = []

    for event in events:
        if hasattr(event, "model_dump"):
            try:
                ev = event.model_dump(mode="json")
            except Exception:
                ev = event.model_dump()
        elif isinstance(event, dict):
            ev = event
        else:
            continue

        raw_type = ev.get("type") or ev.get("event")
        if hasattr(raw_type, "value"):
            raw_type = raw_type.value
        if not raw_type:
            continue
        ev_type = str(raw_type)
        if ev_type.startswith("EventType."):
            ev_type = ev_type[len("EventType.") :]

        ev_time = _format_timestamp(ev.get("timestamp") or ev.get("created_at") or ev.get("time"))

        if ev_type == "THREAD_TRANSITION":
            to_thread_id = str(
                ev.get("to_thread_id")
                or ev.get("toThreadId")
                or ev.get("thread_id")
                or ev.get("threadId")
                or ""
            )
            is_first = bool(ev.get("is_first"))
            if to_thread_id and not is_first:
                # Add system transition marker if not already present
                if not any(
                    m.threadTransition and m.threadTransition.threadId == to_thread_id
                    for m in messages
                ):
                    mode = ev.get("mode") or "chat"
                    phase = ev.get("phase")
                    mode_label = ev.get("mode_label") or (f"{mode}/{phase}" if phase else mode)
                    messages.append(
                        ChatMessageResponse(
                            id=f"transition-{to_thread_id}",
                            role="system",
                            text="",
                            timestamp=ev_time,
                            threadTransition=ThreadTransitionInfoSchema(
                                threadId=to_thread_id,
                                threadName=ev.get("thread_name") or ev.get("name"),
                                mode=mode,
                                phase=phase,
                                modeLabel=mode_label,
                            ),
                        )
                    )

        elif ev_type == "USER_MESSAGE":
            msg_id = str(ev.get("id") or f"user-{len(messages)}")
            content = ev.get("content")
            text = ""
            if isinstance(content, str):
                text = content
            elif isinstance(content, list) and content and isinstance(content[0], dict):
                text = str(content[0].get("text") or "")
            elif ev.get("text"):
                text = str(ev.get("text"))

            if not any(m.id == msg_id for m in messages):
                messages.append(
                    ChatMessageResponse(
                        id=msg_id,
                        role="user",
                        text=text,
                        timestamp=ev_time,
                    )
                )

        elif ev_type == "TEXT_MESSAGE_START":
            msg_id = str(ev.get("message_id") or ev.get("messageId") or f"msg-{len(messages)}")
            ev_role = ev.get("role")
            if hasattr(ev_role, "value"):
                ev_role = ev_role.value
            role: Literal["user", "assistant"] = (
                "user" if str(ev_role).lower().endswith("user") else "assistant"
            )

            if role == "assistant" and messages and messages[-1].role == "assistant":
                last = messages[-1]
                existing_parts = list(last.parts or [])
                text_part = MessagePartSchema(
                    type="text",
                    id=msg_id,
                    content="",
                    timestamp=ev_time,
                )
                existing_parts.append(text_part)
                last.parts = existing_parts
                last.isReasoning = False
            else:
                initial_parts: list[MessagePartSchema] | None = (
                    [MessagePartSchema(type="text", id=msg_id, content="", timestamp=ev_time)]
                    if role == "assistant"
                    else None
                )
                messages.append(
                    ChatMessageResponse(
                        id=msg_id,
                        role=role,
                        text="",
                        parts=initial_parts,
                        timestamp=ev_time,
                    )
                )

        elif ev_type in ("TEXT_MESSAGE_CHUNK", "TEXT_MESSAGE_CONTENT"):
            msg_id = str(ev.get("message_id") or ev.get("messageId") or "")
            delta = str(ev.get("delta") or ev.get("content") or ev.get("text") or "")
            if not delta:
                continue

            target: ChatMessageResponse | None = None
            if msg_id:
                for m in messages:
                    if m.id == msg_id:
                        target = m
                        break

            if target is None and messages and messages[-1].role == "assistant":
                target = messages[-1]

            if target is not None:
                target.text = (target.text or "") + delta
                target.isReasoning = False
                parts = list(target.parts or [])
                if parts and parts[-1].type == "text":
                    parts[-1].content = (parts[-1].content or "") + delta
                    parts[-1].timestamp = ev_time
                else:
                    parts.append(
                        MessagePartSchema(
                            type="text",
                            id=msg_id or f"text-{len(parts)}",
                            content=delta,
                            timestamp=ev_time,
                        )
                    )
                target.parts = parts
            else:
                new_id = msg_id or f"asst-{len(messages)}"
                messages.append(
                    ChatMessageResponse(
                        id=new_id,
                        role="assistant",
                        text=delta,
                        parts=[
                            MessagePartSchema(
                                type="text", id=new_id, content=delta, timestamp=ev_time
                            )
                        ],
                        timestamp=ev_time,
                    )
                )

        elif ev_type in ("REASONING_START", "REASONING_MESSAGE_START"):
            reasoning_id = str(
                ev.get("message_id") or ev.get("messageId") or f"reasoning-{len(messages)}"
            )
            part = MessagePartSchema(
                type="reasoning",
                id=reasoning_id,
                content="",
                isStreaming=False,
                timestamp=ev_time,
            )

            if messages and messages[-1].role == "assistant":
                last = messages[-1]
                parts = list(last.parts or [])
                parts.append(part)
                last.parts = parts
                last.isReasoning = True
            else:
                new_id = f"asst-{len(messages)}"
                messages.append(
                    ChatMessageResponse(
                        id=new_id,
                        role="assistant",
                        text="",
                        reasoning="",
                        isReasoning=True,
                        parts=[part],
                        timestamp=ev_time,
                    )
                )

        elif ev_type in ("REASONING_MESSAGE_CONTENT", "REASONING_MESSAGE_CHUNK"):
            reasoning_id = str(ev.get("message_id") or ev.get("messageId") or "")
            delta = str(ev.get("delta") or ev.get("content") or ev.get("text") or "")
            if not delta:
                continue

            target = messages[-1] if (messages and messages[-1].role == "assistant") else None
            if target is not None:
                target.reasoning = (target.reasoning or "") + delta
                parts = list(target.parts or [])
                if parts and parts[-1].type == "reasoning":
                    parts[-1].content = (parts[-1].content or "") + delta
                    parts[-1].timestamp = ev_time
                else:
                    parts.append(
                        MessagePartSchema(
                            type="reasoning",
                            id=reasoning_id or f"reasoning-{len(parts)}",
                            content=delta,
                            timestamp=ev_time,
                        )
                    )
                target.parts = parts
            else:
                new_id = f"asst-{len(messages)}"
                r_id = reasoning_id or f"reasoning-{new_id}"
                messages.append(
                    ChatMessageResponse(
                        id=new_id,
                        role="assistant",
                        text="",
                        reasoning=delta,
                        isReasoning=True,
                        parts=[
                            MessagePartSchema(
                                type="reasoning", id=r_id, content=delta, timestamp=ev_time
                            )
                        ],
                        timestamp=ev_time,
                    )
                )

        elif ev_type in ("REASONING_END", "REASONING_MESSAGE_END"):
            if messages and messages[-1].role == "assistant":
                messages[-1].isReasoning = False

        elif ev_type == "TOOL_CALL_START":
            call_id = str(ev.get("tool_call_id") or ev.get("toolCallId") or f"call-{len(messages)}")
            call_name = str(ev.get("tool_call_name") or ev.get("toolCallName") or "tool")
            tool_record = ToolCallRecordSchema(
                id=call_id,
                name=call_name,
                status="pending",
                rawArgs="",
                args={},
                timestamp=ev_time,
            )
            part = MessagePartSchema(
                type="tool_call",
                id=call_id,
                toolCall=tool_record,
                timestamp=ev_time,
            )

            if messages and messages[-1].role == "assistant":
                last = messages[-1]
                tcs = list(last.toolCalls or [])
                tcs.append(tool_record)
                last.toolCalls = tcs
                parts = list(last.parts or [])
                parts.append(part)
                last.parts = parts
                last.isReasoning = False
            else:
                asst_id = f"asst-{len(messages)}"
                messages.append(
                    ChatMessageResponse(
                        id=asst_id,
                        role="assistant",
                        text="",
                        toolCalls=[tool_record],
                        parts=[part],
                        timestamp=ev_time,
                    )
                )

        elif ev_type in ("TOOL_CALL_ARGS", "TOOL_CALL_CHUNK"):
            call_id = str(ev.get("tool_call_id") or ev.get("toolCallId") or "")
            delta = str(ev.get("delta") or "")
            explicit_args = ev.get("args")

            # Find tool call across messages
            for m in reversed(messages):
                if not m.toolCalls:
                    continue
                tc = next((c for c in m.toolCalls if not call_id or c.id == call_id), None)
                if tc is not None:
                    if delta:
                        tc.rawArgs = (tc.rawArgs or "") + delta
                    if isinstance(explicit_args, dict):
                        tc.args = explicit_args
                    elif tc.rawArgs:
                        try:
                            tc.args = json.loads(tc.rawArgs)
                        except Exception:
                            pass
                    tc.status = "wip" if tc.status != "done" else "done"
                    # Sync into parts
                    if m.parts:
                        for p in m.parts:
                            if p.type == "tool_call" and p.toolCall and p.toolCall.id == tc.id:
                                p.toolCall = tc
                    break

        elif ev_type == "TOOL_CALL_END":
            call_id = str(ev.get("tool_call_id") or ev.get("toolCallId") or "")
            for m in reversed(messages):
                if not m.toolCalls:
                    continue
                tc = next((c for c in m.toolCalls if not call_id or c.id == call_id), None)
                if tc is not None:
                    if (not tc.args or not tc.args.keys()) and tc.rawArgs:
                        try:
                            tc.args = json.loads(tc.rawArgs)
                        except Exception:
                            pass
                    tc.status = "done" if tc.status == "done" else "wip"
                    tc.timestamp = ev_time
                    if m.parts:
                        for p in m.parts:
                            if p.type == "tool_call" and p.toolCall and p.toolCall.id == tc.id:
                                p.toolCall = tc
                    break

        elif ev_type == "TOOL_CALL_RESULT":
            call_id = str(ev.get("tool_call_id") or ev.get("toolCallId") or "")
            result = ev.get("result") or ev.get("content")
            for m in reversed(messages):
                if not m.toolCalls:
                    continue
                tc = next((c for c in m.toolCalls if not call_id or c.id == call_id), None)
                if tc is not None:
                    tc.result = result
                    tc.status = "done"
                    tc.timestamp = ev_time
                    if m.parts:
                        for p in m.parts:
                            if p.type == "tool_call" and p.toolCall and p.toolCall.id == tc.id:
                                p.toolCall = tc
                    break

        elif ev_type in ("ARTIFACT_CREATED", "ARTIFACT_UPDATED"):
            art_id = str(ev.get("artifact_id") or ev.get("artifactId") or ev.get("name") or "")
            if art_id and messages and messages[-1].role == "assistant":
                art_dict = {"uuid": art_id, "name": art_id, "kind": ev.get("kind") or "artifacts"}
                art_part = MessagePartSchema(
                    type="artifact",
                    id=f"artifact-{art_id}",
                    artifact=art_dict,
                    timestamp=ev_time,
                )
                last = messages[-1]
                parts = list(last.parts or [])
                if not any(p.id == f"artifact-{art_id}" for p in parts):
                    parts.append(art_part)
                    last.parts = parts

    return messages


def extract_bubbles_from_messages(
    messages: list[ChatMessageResponse],
) -> list[tuple[str, int]]:
    """Extract ordered (bubble_id, message_index) tuples representing visual UI bubbles.

    Matches frontend bubble semantics:
    - Thread transitions: 1 boundary bubble
    - User message: 1 bubble
    - Assistant message: 1 bubble per reasoning block, tool call, artifact, or text part.
    """
    bubbles: list[tuple[str, int]] = []
    for m_idx, msg in enumerate(messages):
        if msg.threadTransition:
            bubbles.append((msg.id, m_idx))
            continue
        if msg.role == "user":
            bubbles.append((msg.id, m_idx))
            continue
        if msg.role == "assistant":
            if msg.parts and len(msg.parts) > 0:
                for part in msg.parts:
                    if part.type in ("reasoning", "tool_call", "artifact"):
                        bubbles.append((part.id, m_idx))
                    elif part.type == "text" and part.content and part.content.strip():
                        bubbles.append((part.id, m_idx))
            else:
                if msg.reasoning:
                    bubbles.append((f"{msg.id}-reasoning", m_idx))
                if msg.toolCalls:
                    for tc in msg.toolCalls:
                        bubbles.append((tc.id, m_idx))
                if msg.text and msg.text.strip():
                    bubbles.append((f"{msg.id}-text", m_idx))
    return bubbles


def paginate_chat_messages(
    messages: list[ChatMessageResponse],
    limit: int = 50,
    before_id: str | None = None,
    after_id: str | None = None,
    tail: bool = False,
) -> PaginatedMessagesResponse:
    """Slice chat messages based on bubble count and cursor boundaries."""
    all_bubbles = extract_bubbles_from_messages(messages)
    total_bubbles = len(all_bubbles)

    if total_bubbles == 0:
        return PaginatedMessagesResponse(
            messages=[],
            total_bubbles=0,
            has_more_before=False,
            has_more_after=False,
            oldest_bubble_id=None,
            newest_bubble_id=None,
        )

    start_idx = 0
    end_idx = total_bubbles

    if before_id:
        # Find index of before_id
        target_idx = next(
            (i for i, (b_id, _) in enumerate(all_bubbles) if b_id == before_id),
            None,
        )
        if target_idx is not None:
            end_idx = target_idx
            start_idx = max(0, target_idx - limit)
        else:
            # Fallback to tail
            start_idx = max(0, total_bubbles - limit)
            end_idx = total_bubbles
    elif after_id:
        target_idx = next(
            (i for i, (b_id, _) in enumerate(all_bubbles) if b_id == after_id),
            None,
        )
        if target_idx is not None:
            start_idx = target_idx + 1
            end_idx = min(total_bubbles, start_idx + limit)
        else:
            start_idx = max(0, total_bubbles - limit)
            end_idx = total_bubbles
    elif tail or before_id is None:
        # Default: tail N bubbles
        start_idx = max(0, total_bubbles - limit)
        end_idx = total_bubbles

    sliced_bubbles = all_bubbles[start_idx:end_idx]
    if not sliced_bubbles:
        return PaginatedMessagesResponse(
            messages=[],
            total_bubbles=total_bubbles,
            has_more_before=start_idx > 0,
            has_more_after=end_idx < total_bubbles,
            oldest_bubble_id=None,
            newest_bubble_id=None,
        )

    # Determine unique message indices covering the sliced bubbles in order
    msg_indices = sorted({m_idx for _, m_idx in sliced_bubbles})
    sliced_bubble_keys = {b_id for b_id, _ in sliced_bubbles}
    result_messages: list[ChatMessageResponse] = []

    for m_idx in msg_indices:
        msg = messages[m_idx]
        if msg.threadTransition:
            if msg.id in sliced_bubble_keys:
                result_messages.append(msg)
            continue

        if msg.role == "user":
            if msg.id in sliced_bubble_keys:
                result_messages.append(msg)
            continue

        # Assistant or system message with parts
        if msg.parts:
            visible_parts = [p for p in msg.parts if p.id in sliced_bubble_keys]
            if visible_parts:
                visible_calls: list[ToolCallRecordSchema] | None = None
                if msg.toolCalls:
                    visible_call_ids = {
                        p.toolCall.id for p in visible_parts if p.type == "tool_call" and p.toolCall
                    }
                    visible_calls = [
                        tc
                        for tc in msg.toolCalls
                        if tc.id in visible_call_ids or tc.id in sliced_bubble_keys
                    ]
                visible_text = "".join(
                    p.content for p in visible_parts if p.type == "text" and p.content
                )
                msg_copy = msg.model_copy(
                    update={
                        "parts": visible_parts,
                        "toolCalls": visible_calls,
                        "text": visible_text,
                    }
                )
                result_messages.append(msg_copy)
            elif msg.id in sliced_bubble_keys:
                result_messages.append(msg)
        elif msg.toolCalls:
            visible_calls = [tc for tc in msg.toolCalls if tc.id in sliced_bubble_keys]
            if visible_calls:
                msg_copy = msg.model_copy(update={"toolCalls": visible_calls})
                result_messages.append(msg_copy)
            elif msg.id in sliced_bubble_keys:
                result_messages.append(msg)
        elif msg.id in sliced_bubble_keys:
            result_messages.append(msg)

    return PaginatedMessagesResponse(
        messages=result_messages,
        total_bubbles=total_bubbles,
        has_more_before=start_idx > 0,
        has_more_after=end_idx < total_bubbles,
        oldest_bubble_id=sliced_bubbles[0][0],
        newest_bubble_id=sliced_bubbles[-1][0],
    )
