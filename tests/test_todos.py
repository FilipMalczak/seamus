"""Unit tests for native LM-XML task planning toolset and tree restructuring."""

from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from seamus.domain.entities import Thread, TodoItem
from seamus.harness.todos import (
    SeamusTodoMiddleware,
    apply_child_added_rule,
    move_item,
    normalize_status,
    propagate_state_changes,
    render_plan_text,
)


def test_normalize_status() -> None:
    """Verify case-insensitivity, whitespace trimming, and alias mapping."""
    assert normalize_status("PENDING") == "pending"
    assert normalize_status("  Todo  ") == "pending"
    assert normalize_status("wip") == "wip"
    assert normalize_status("In_Progress") == "wip"
    assert normalize_status("done") == "done"
    assert normalize_status("Completed") == "done"
    assert normalize_status("abandoned") == "abandoned"
    assert normalize_status("Skipped") == "abandoned"
    assert normalize_status("omitted") == "abandoned"

    with pytest.raises(ValueError, match="Invalid status 'unknown'"):
        normalize_status("unknown")


def test_render_plan_text_hierarchy() -> None:
    """Verify hierarchical 1-based paths, 2-space indentation, and display tokens."""
    # Empty plan
    assert render_plan_text([]) is None

    t0 = datetime(2026, 11, 9, 10, 0, tzinfo=UTC)
    items = [
        TodoItem(id="abcd", content="foo", status="wip", parent_id=None, position=1, created_at=t0),
        TodoItem(
            id="1abc", content="bar", status="done", parent_id="abcd", position=1, created_at=t0
        ),
        TodoItem(
            id="2abc", content="baz", status="wip", parent_id="abcd", position=2, created_at=t0
        ),
        TodoItem(
            id="ab3d",
            content="barbaz",
            status="pending",
            parent_id="abcd",
            position=3,
            created_at=t0,
        ),
        TodoItem(
            id="8e1f",
            content="skipped",
            status="abandoned",
            parent_id="abcd",
            position=4,
            created_at=t0,
        ),
        TodoItem(
            id="1234",
            content="top second",
            status="pending",
            parent_id=None,
            position=2,
            created_at=t0,
        ),
    ]

    expected = (
        "1. (abcd) [WIP] foo\n"
        "  1.1. (1abc) [DONE] bar\n"
        "  1.2. (2abc) [WIP] baz\n"
        "  1.3. (ab3d) [TODO] barbaz\n"
        "  1.4. (8e1f) [ABANDONED] skipped\n"
        "2. (1234) [TODO] top second"
    )
    assert render_plan_text(items) == expected


def test_move_item_reordering_under_same_parent() -> None:
    """Verify reordering sibling items using 1-based new_position."""
    t0 = datetime(2026, 11, 9, 10, 0, tzinfo=UTC)
    items = [
        TodoItem(id="root", content="foo", parent_id=None, position=1, created_at=t0),
        TodoItem(id="bar", content="bar", parent_id="root", position=1, created_at=t0),
        TodoItem(id="baz", content="baz", parent_id="root", position=2, created_at=t0),
        TodoItem(id="qux", content="qux", parent_id="root", position=3, created_at=t0),
    ]

    # Move qux to position 1
    ok, msg = move_item(items, "qux", new_parent=None, new_position=1)
    assert ok, msg
    assert msg == "OK"

    # Sibling order under root should now be qux (1), bar (2), baz (3)
    by_id = {it.id: it for it in items}
    assert by_id["qux"].position == 1
    assert by_id["bar"].position == 2
    assert by_id["baz"].position == 3


def test_move_item_reparenting_and_cycle_prevention() -> None:
    """Verify moving an item to a new parent, to root, and preventing cycles."""
    t0 = datetime(2026, 11, 9, 10, 0, tzinfo=UTC)
    items = [
        TodoItem(id="p1", content="parent 1", parent_id=None, position=1, created_at=t0),
        TodoItem(id="c1", content="child 1", parent_id="p1", position=1, created_at=t0),
        TodoItem(id="gc1", content="grandchild 1", parent_id="c1", position=1, created_at=t0),
        TodoItem(id="p2", content="parent 2", parent_id=None, position=2, created_at=t0),
    ]

    # Prevent self-parenting
    ok, err = move_item(items, "p1", new_parent="p1", new_position=None)
    assert not ok
    assert "cannot become its own parent" in err

    # Prevent cycles (moving p1 under grandchild gc1)
    ok, err = move_item(items, "p1", new_parent="gc1", new_position=None)
    assert not ok
    assert "cycle detected" in err

    # Out of bounds position check
    ok, err = move_item(items, "c1", new_parent="p2", new_position=99)
    assert not ok
    assert "Invalid new_position" in err

    # Valid move: move c1 under p2 (omitting new_position -> append)
    ok, msg = move_item(items, "c1", new_parent="p2", new_position=None)
    assert ok
    c1_item = next(it for it in items if it.id == "c1")
    assert c1_item.parent_id == "p2"
    assert c1_item.position == 1

    # Promote c1 to root
    ok, msg = move_item(items, "c1", new_parent="root", new_position=1)
    assert ok
    assert c1_item.parent_id is None
    assert c1_item.position == 1


def test_auto_state_rule_1_parent_closed() -> None:
    """Rule 1: Parent becomes CLOSED -> WIP children match parent, PENDING become ABANDONED."""
    items = [
        TodoItem(id="p", content="parent", status="wip", parent_id=None, position=1),
        TodoItem(id="c_wip", content="c1", status="wip", parent_id="p", position=1),
        TodoItem(id="c_todo", content="c2", status="pending", parent_id="p", position=2),
        TodoItem(id="c_done", content="c3", status="done", parent_id="p", position=3),
        TodoItem(id="c_sub", content="c4", status="pending", parent_id="c_wip", position=1),
    ]

    # Parent transitions to DONE
    propagate_state_changes(items, "p", old_status="wip", new_status="done")
    by_id = {it.id: it for it in items}
    assert by_id["c_wip"].status == "done"
    assert by_id["c_todo"].status == "abandoned"
    assert by_id["c_done"].status == "done"  # Preserved
    assert by_id["c_sub"].status == "abandoned"  # Cascaded down

    # Test parent becoming ABANDONED
    items2 = [
        TodoItem(id="p", content="parent", status="wip", parent_id=None, position=1),
        TodoItem(id="c_wip", content="c1", status="wip", parent_id="p", position=1),
        TodoItem(id="c_todo", content="c2", status="pending", parent_id="p", position=2),
    ]
    propagate_state_changes(items2, "p", old_status="wip", new_status="abandoned")
    by_id2 = {it.id: it for it in items2}
    assert by_id2["c_wip"].status == "abandoned"
    assert by_id2["c_todo"].status == "abandoned"


def test_auto_state_rule_2_child_added_open_to_done_parent() -> None:
    """Rule 2: Parent is DONE and child is added OPEN -> parent becomes WIP depth-first."""
    items = [
        TodoItem(id="root", content="root", status="done", parent_id=None, position=1),
        TodoItem(id="sub", content="sub", status="done", parent_id="root", position=1),
    ]

    new_child = TodoItem(id="leaf", content="leaf", status="pending", parent_id="sub", position=1)
    items.append(new_child)
    apply_child_added_rule(items, new_child)

    by_id = {it.id: it for it in items}
    assert by_id["sub"].status == "wip"
    assert by_id["root"].status == "wip"


def test_auto_state_rule_3_child_reopened_to_open() -> None:
    """Rule 3: Child reopened from CLOSED to OPEN under DONE parent -> parent becomes WIP."""
    items = [
        TodoItem(id="root", content="root", status="done", parent_id=None, position=1),
        TodoItem(id="sub", content="sub", status="done", parent_id="root", position=1),
        TodoItem(id="leaf", content="leaf", status="done", parent_id="sub", position=1),
    ]

    # Reopen leaf from done to wip
    leaf = next(it for it in items if it.id == "leaf")
    leaf.status = "wip"
    propagate_state_changes(items, "leaf", old_status="done", new_status="wip")

    by_id = {it.id: it for it in items}
    assert by_id["sub"].status == "wip"
    assert by_id["root"].status == "wip"


def test_seamus_todo_middleware_tools() -> None:
    """Verify create_todo_item, edit_todo_item, and delete_todo_item tools."""
    thread = Thread()
    mock_ws = MagicMock()
    middleware = SeamusTodoMiddleware(
        get_thread=lambda: thread,
        workspace_manager=mock_ws,
        agent_id=uuid4(),
        session_id=uuid4(),
        on_todos_changed=MagicMock(),
    )

    # 1. create_todo_item
    # Content empty -> error
    res = middleware.handle_create_todo_item(content="   ")
    assert "Error: content cannot be empty" in res

    # Status abandoned on create -> error
    res = middleware.handle_create_todo_item(content="test", status="abandoned")
    assert "Cannot create a todo item with status 'abandoned'" in res

    # Missing parent -> error
    res = middleware.handle_create_todo_item(content="test", parent_id="dead")
    assert "Parent todo item 'dead' not found" in res

    # Successful create root item
    res = middleware.handle_create_todo_item(content="Root task", status="pending")
    assert "Created todo item" in res
    assert "[TODO]" in res
    assert len(thread.todos) == 1
    root_id = thread.todos[0].id

    # Create subtask under root task
    res = middleware.handle_create_todo_item(content="Child task", status="wip", parent_id=root_id)
    assert "Created todo item" in res
    assert "[WIP]" in res
    assert len(thread.todos) == 2
    child_id = thread.todos[1].id

    # 2. edit_todo_item
    # Call correctness: no arguments -> error
    res = middleware.handle_edit_todo_item(id=child_id)
    assert (
        "At least one of new_content, new_status, new_parent, or new_position must be provided"
        in res
    )

    # Empty stripped content -> error
    res = middleware.handle_edit_todo_item(id=child_id, new_content="   ")
    assert "new_content cannot be empty" in res

    # Invalid status -> error
    res = middleware.handle_edit_todo_item(id=child_id, new_status="invalid_status")
    assert "Invalid status 'invalid_status'" in res

    # Target not found -> error
    res = middleware.handle_edit_todo_item(id="nonexistent", new_content="Valid")
    assert "Todo item 'nonexistent' not found" in res

    # Edit content and status
    res = middleware.handle_edit_todo_item(
        id=child_id, new_content="Updated child", new_status="done"
    )
    assert f"Updated todo item ({child_id})" in res
    child = next(it for it in thread.todos if it.id == child_id)
    assert child.content == "Updated child"
    assert child.status == "done"

    # Cannot transition DONE to ABANDONED
    res = middleware.handle_edit_todo_item(id=child_id, new_status="abandoned")
    assert "Cannot transition todo item" in res
    assert "[DONE] to [ABANDONED]" in res

    # 3. delete_todo_item
    # Nonexistent ID -> error
    res = middleware.handle_delete_todo_item(id="bad_id")
    assert "Todo item 'bad_id' not found" in res

    # Delete root task cascades to child task
    res = middleware.handle_delete_todo_item(id=root_id)
    assert "Deleted todo item" in res
    assert "and 1 subtasks" in res
    assert len(thread.todos) == 0
