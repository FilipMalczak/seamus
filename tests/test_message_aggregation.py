"""Unit tests for event-to-bubble aggregation, bubble extraction, and pagination."""

from seamus.harness.messages import (
    aggregate_events_to_chat_messages,
    extract_bubbles_from_messages,
    paginate_chat_messages,
)
from seamus.server.schemas import ChatMessageResponse, MessagePartSchema, ToolCallRecordSchema


def test_aggregate_events_user_and_assistant_turn() -> None:
    events = [
        {"type": "USER_MESSAGE", "id": "u1", "content": "Hello agent"},
        {"type": "REASONING_START", "message_id": "r1"},
        {"type": "REASONING_MESSAGE_CONTENT", "message_id": "r1", "delta": "Thinking about plan"},
        {"type": "REASONING_END", "message_id": "r1"},
        {
            "type": "TOOL_CALL_START",
            "tool_call_id": "c1",
            "tool_call_name": "list_files",
        },
        {"type": "TOOL_CALL_ARGS", "tool_call_id": "c1", "delta": '{"path": "."}'},
        {"type": "TOOL_CALL_END", "tool_call_id": "c1"},
        {"type": "TOOL_CALL_RESULT", "tool_call_id": "c1", "result": ["file1.txt", "file2.txt"]},
        {"type": "TEXT_MESSAGE_START", "message_id": "t1", "role": "assistant"},
        {"type": "TEXT_MESSAGE_CONTENT", "message_id": "t1", "delta": "I found 2 files."},
        {"type": "TEXT_MESSAGE_END", "message_id": "t1"},
    ]

    messages = aggregate_events_to_chat_messages(events)
    assert len(messages) == 2

    # User message
    user_msg = messages[0]
    assert user_msg.id == "u1"
    assert user_msg.role == "user"
    assert user_msg.text == "Hello agent"

    # Assistant message
    asst_msg = messages[1]
    assert asst_msg.role == "assistant"
    assert asst_msg.parts is not None
    assert len(asst_msg.parts) == 3
    assert asst_msg.parts[0].type == "reasoning"
    assert asst_msg.parts[0].content == "Thinking about plan"
    assert asst_msg.parts[1].type == "tool_call"
    assert asst_msg.parts[1].toolCall is not None
    assert asst_msg.parts[1].toolCall.name == "list_files"
    assert asst_msg.parts[1].toolCall.result == ["file1.txt", "file2.txt"]
    assert asst_msg.parts[2].type == "text"
    assert asst_msg.parts[2].content == "I found 2 files."

    # Visual bubbles: 1 user bubble + 3 assistant bubbles = 4 bubbles
    bubbles = extract_bubbles_from_messages(messages)
    assert len(bubbles) == 4
    assert [b[0] for b in bubbles] == ["u1", "r1", "c1", "t1"]


def test_pagination_tail_and_cursors() -> None:
    # Build 100 simple user messages (100 bubbles)
    events = [
        {"type": "USER_MESSAGE", "id": f"msg-{i}", "content": f"Message {i}"} for i in range(100)
    ]
    messages = aggregate_events_to_chat_messages(events)
    bubbles = extract_bubbles_from_messages(messages)
    assert len(bubbles) == 100

    # Default / tail: 50 items
    res_tail = paginate_chat_messages(messages, limit=50, tail=True)
    assert len(res_tail.messages) == 50
    assert res_tail.total_bubbles == 100
    assert res_tail.has_more_before is True
    assert res_tail.has_more_after is False
    assert res_tail.oldest_bubble_id == "msg-50"
    assert res_tail.newest_bubble_id == "msg-99"

    # Backward pagination before msg-50
    res_before = paginate_chat_messages(messages, limit=50, before_id="msg-50")
    assert len(res_before.messages) == 50
    assert res_before.has_more_before is False
    assert res_before.has_more_after is True
    assert res_before.oldest_bubble_id == "msg-0"
    assert res_before.newest_bubble_id == "msg-49"

    # Forward pagination after msg-49
    res_after = paginate_chat_messages(messages, limit=25, after_id="msg-49")
    assert len(res_after.messages) == 25
    assert res_after.oldest_bubble_id == "msg-50"
    assert res_after.newest_bubble_id == "msg-74"
    assert res_after.has_more_after is True


def test_pagination_empty() -> None:
    res = paginate_chat_messages([], limit=50)
    assert len(res.messages) == 0
    assert res.total_bubbles == 0
    assert res.has_more_before is False
    assert res.has_more_after is False


def test_pagination_slices_parts_within_single_assistant_message() -> None:
    """A long turn with 100 tool calls in a single assistant message is paginated across parts."""
    parts = [
        MessagePartSchema(
            type="tool_call",
            id=f"call-{i}",
            toolCall=ToolCallRecordSchema(id=f"call-{i}", name="cmd"),
        )
        for i in range(100)
    ]
    tool_calls = [ToolCallRecordSchema(id=f"call-{i}", name="cmd") for i in range(100)]
    msg = ChatMessageResponse(
        id="asst-1",
        role="assistant",
        text="",
        parts=parts,
        toolCalls=tool_calls,
        timestamp="12:00:00",
    )

    # Tail 40
    res_tail = paginate_chat_messages([msg], limit=40, tail=True)
    assert res_tail.total_bubbles == 100
    assert res_tail.has_more_before is True
    assert res_tail.has_more_after is False
    assert len(res_tail.messages) == 1
    assert len(res_tail.messages[0].parts or []) == 40
    assert res_tail.oldest_bubble_id == "call-60"
    assert res_tail.newest_bubble_id == "call-99"

    # Previous 40 before oldest
    res_prev = paginate_chat_messages([msg], limit=40, before_id=res_tail.oldest_bubble_id)
    assert res_prev.total_bubbles == 100
    assert res_prev.has_more_before is True
    assert res_prev.has_more_after is True
    assert len(res_prev.messages) == 1
    assert len(res_prev.messages[0].parts or []) == 40
    assert res_prev.oldest_bubble_id == "call-20"
    assert res_prev.newest_bubble_id == "call-59"

    # Remaining 20 before that
    res_first = paginate_chat_messages([msg], limit=40, before_id=res_prev.oldest_bubble_id)
    assert res_first.total_bubbles == 100
    assert res_first.has_more_before is False
    assert res_first.has_more_after is True
    assert len(res_first.messages) == 1
    assert len(res_first.messages[0].parts or []) == 20
    assert res_first.oldest_bubble_id == "call-0"
    assert res_first.newest_bubble_id == "call-19"
