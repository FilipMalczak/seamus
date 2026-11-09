"""Native LM-XML task planning toolset, tree restructuring, and auto-state machine."""

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from langchain.agents.middleware import AgentMiddleware
from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field

from seamus.domain.entities import Thread, TodoItem, TodoStatus
from seamus.persistence.workspace import GitWorkspaceManager

logger = logging.getLogger(__name__)

STATUS_DISPLAY_MAP: dict[str, str] = {
    TodoStatus.PENDING.value: "TODO",
    TodoStatus.WIP.value: "WIP",
    TodoStatus.DONE.value: "DONE",
    TodoStatus.ABANDONED.value: "ABANDONED",
}

STATUS_ALIASES: dict[str, str] = {
    "todo": TodoStatus.PENDING.value,
    "pending": TodoStatus.PENDING.value,
    "wip": TodoStatus.WIP.value,
    "in_progress": TodoStatus.WIP.value,
    "done": TodoStatus.DONE.value,
    "completed": TodoStatus.DONE.value,
    "abandoned": TodoStatus.ABANDONED.value,
    "skipped": TodoStatus.ABANDONED.value,
    "omitted": TodoStatus.ABANDONED.value,
}

OPEN_STATUSES: set[str] = {TodoStatus.PENDING.value, TodoStatus.WIP.value}
CLOSED_STATUSES: set[str] = {TodoStatus.DONE.value, TodoStatus.ABANDONED.value}


def normalize_status(raw_status: str) -> str:
    """Normalize a task status string case-insensitively, handling aliases."""
    cleaned = raw_status.strip().lower()
    if cleaned in STATUS_ALIASES:
        return STATUS_ALIASES[cleaned]
    allowed = ", ".join(sorted(STATUS_DISPLAY_MAP.keys()))
    msg = f"Invalid status '{raw_status}'. Allowed values: {allowed}."
    raise ValueError(msg)


def generate_unique_id(existing_ids: set[str]) -> str:
    """Generate a collision-resistant 4-hex random identifier."""
    for _ in range(1000):
        cand = uuid4().hex[-4:]
        if cand not in existing_ids:
            return cand
    msg = "Failed to allocate a unique 4-hex todo ID after 1000 attempts."
    raise RuntimeError(msg)


class RenderedTodoLine(BaseModel):
    """Calculated path, depth, and display details for a todo item."""

    item: TodoItem
    path: str
    depth: int
    display_status: str


def compute_hierarchical_paths(items: list[TodoItem]) -> list[RenderedTodoLine]:
    """Compute 1-based advisory paths and depth for items in creation/position order."""
    if not items:
        return []

    parent_map: dict[str | None, list[TodoItem]] = {}
    for it in items:
        parent_map.setdefault(it.parent_id, []).append(it)

    for sibling_list in parent_map.values():
        sibling_list.sort(key=lambda s: (s.position, s.created_at))

    results: list[RenderedTodoLine] = []

    def _traverse(parent_id: str | None, prefix: str, depth: int) -> None:
        children = parent_map.get(parent_id, [])
        for idx, child in enumerate(children, start=1):
            curr_path = f"{prefix}{idx}."
            disp = STATUS_DISPLAY_MAP.get(child.status, child.status.upper())
            results.append(
                RenderedTodoLine(
                    item=child,
                    path=curr_path,
                    depth=depth,
                    display_status=disp,
                )
            )
            _traverse(child.id, curr_path, depth + 1)

    _traverse(None, "", 0)
    return results


def render_plan_text(items: list[TodoItem]) -> str | None:
    """Render the hierarchical todo list into indented plain text or None if empty."""
    lines_info = compute_hierarchical_paths(items)
    if not lines_info:
        return None

    rendered_lines: list[str] = []
    for info in lines_info:
        indent = "  " * info.depth
        rendered_lines.append(
            f"{indent}{info.path} ({info.item.id}) [{info.display_status}] {info.item.content}"
        )
    return "\n".join(rendered_lines)


def get_all_descendants(items: list[TodoItem], item_id: str) -> list[TodoItem]:
    """Return all descendant todo items rooted at item_id (depth-first)."""
    parent_map: dict[str, list[TodoItem]] = {}
    for it in items:
        if it.parent_id:
            parent_map.setdefault(it.parent_id, []).append(it)

    descendants: list[TodoItem] = []
    stack = [item_id]
    while stack:
        curr = stack.pop()
        children = parent_map.get(curr, [])
        for ch in children:
            descendants.append(ch)
            stack.append(ch.id)
    return descendants


def move_item(
    items: list[TodoItem],
    item_id: str,
    new_parent: str | None,
    new_position: int | None,
) -> tuple[bool, str]:
    """Atomically reparent and/or reorder a todo item in place.

    Returns (True, "OK") or (False, error_message).
    """
    item = next((it for it in items if it.id == item_id), None)
    if not item:
        return False, f"Todo item '{item_id}' not found."

    old_parent = item.parent_id

    # Resolve target parent
    if new_parent is None:
        target_parent = old_parent
    elif new_parent.strip().lower() in ("", "root", "none", "null"):
        target_parent = None
    else:
        clean_parent = new_parent.strip()
        p_obj = next((it for it in items if it.id == clean_parent), None)
        if not p_obj:
            return False, f"Destination parent item '{clean_parent}' not found."
        target_parent = p_obj.id

    if target_parent == item_id:
        return False, "An item cannot become its own parent."

    descendant_ids = {d.id for d in get_all_descendants(items, item_id)}
    if target_parent in descendant_ids:
        return (
            False,
            f"Cannot move item '{item_id}' under descendant '{target_parent}' (cycle detected).",
        )

    # Destination siblings (excluding item)
    dest_siblings = [s for s in items if s.parent_id == target_parent and s.id != item_id]
    dest_siblings.sort(key=lambda s: (s.position, s.created_at))
    max_position = len(dest_siblings) + 1

    if new_position is not None:
        if new_position < 1 or new_position > max_position:
            return (
                False,
                f"Invalid new_position {new_position}. Must be between 1 and {max_position}.",
            )
        target_pos = new_position
    elif target_parent != old_parent:
        target_pos = max_position
    else:
        target_pos = item.position

    # Perform atomic re-indexing
    if target_parent != old_parent:
        # Re-index old siblings
        old_siblings = [s for s in items if s.parent_id == old_parent and s.id != item_id]
        old_siblings.sort(key=lambda s: (s.position, s.created_at))
        for idx, s in enumerate(old_siblings, start=1):
            s.position = idx

    item.parent_id = target_parent
    dest_siblings.insert(target_pos - 1, item)
    for idx, s in enumerate(dest_siblings, start=1):
        s.position = idx

    return True, "OK"


def propagate_state_changes(
    items: list[TodoItem],
    changed_id: str,
    old_status: str,
    new_status: str,
) -> None:
    """Apply Seamus's 3 deterministic auto-state rules depth-first."""
    if old_status == new_status:
        return

    items_by_id = {it.id: it for it in items}
    target_item = items_by_id.get(changed_id)
    if not target_item:
        return

    # Rule 1: Parent becomes CLOSED -> WIP children become same status, PENDING become ABANDONED
    if new_status in CLOSED_STATUSES and old_status not in CLOSED_STATUSES:

        def _cascade_closed(parent_id: str, closed_status: str) -> None:
            children = [it for it in items if it.parent_id == parent_id]
            for ch in children:
                if ch.status == TodoStatus.WIP.value:
                    ch.status = closed_status
                    _cascade_closed(ch.id, closed_status)
                elif ch.status == TodoStatus.PENDING.value:
                    ch.status = TodoStatus.ABANDONED.value
                    _cascade_closed(ch.id, TodoStatus.ABANDONED.value)

        _cascade_closed(target_item.id, new_status)

    # Rule 3: Child reopened from CLOSED to OPEN under DONE parent -> parent becomes WIP
    if old_status in CLOSED_STATUSES and new_status in OPEN_STATUSES:
        curr_parent_id: str | None = target_item.parent_id
        while curr_parent_id:
            parent = items_by_id.get(curr_parent_id)
            if not parent:
                break
            if parent.status == TodoStatus.DONE.value:
                parent.status = TodoStatus.WIP.value
                curr_parent_id = parent.parent_id
            else:
                break


def apply_child_added_rule(items: list[TodoItem], new_item: TodoItem) -> None:
    """Rule 2: Parent is DONE and child is added OPEN -> parent becomes WIP."""
    if new_item.status not in OPEN_STATUSES or not new_item.parent_id:
        return

    items_by_id = {it.id: it for it in items}
    curr_parent_id: str | None = new_item.parent_id
    while curr_parent_id:
        parent = items_by_id.get(curr_parent_id)
        if not parent:
            break
        if parent.status == TodoStatus.DONE.value:
            parent.status = TodoStatus.WIP.value
            curr_parent_id = parent.parent_id
        else:
            break


class CreateTodoItemInput(BaseModel):
    """Input arguments for create_todo_item."""

    content: str = Field(description="Description of the task to create.")
    status: str = Field(default="pending", description="Initial status: pending, wip, or done.")
    parent_id: str | None = Field(default=None, description="Optional 4-hex parent item ID.")


class EditTodoItemInput(BaseModel):
    """Input arguments for edit_todo_item."""

    id: str = Field(description="4-hex ID of the todo item to edit or move.")
    new_content: str | None = Field(default=None, description="Updated task description.")
    new_status: str | None = Field(
        default=None, description="Updated status: pending, wip, done, or abandoned."
    )
    new_parent: str | None = Field(
        default=None, description="Optional new parent ID, or 'root' to promote to top-level."
    )
    new_position: int | None = Field(
        default=None, description="Optional 1-based insertion position in destination sibling list."
    )


class DeleteTodoItemInput(BaseModel):
    """Input arguments for delete_todo_item."""

    id: str = Field(description="4-hex ID of the todo item to delete.")


class SeamusTodoMiddleware(AgentMiddleware[Any, Any, Any]):
    """Native task planning middleware providing atomic create, edit, and delete tools."""

    def __init__(
        self,
        get_thread: Callable[[], Thread | None],
        workspace_manager: GitWorkspaceManager,
        agent_id: UUID,
        session_id: UUID,
        on_todos_changed: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.get_thread = get_thread
        self.workspace_manager = workspace_manager
        self.agent_id = agent_id
        self.session_id = session_id
        self.on_todos_changed = on_todos_changed

        self.tools: list[BaseTool] = [
            StructuredTool.from_function(
                name="create_todo_item",
                description=(
                    "Create a new task item in your active plan. Specify content, optional "
                    "status (pending, wip, done), and optional parent_id for subtasks."
                ),
                func=self.handle_create_todo_item,
                args_schema=CreateTodoItemInput,
            ),
            StructuredTool.from_function(
                name="edit_todo_item",
                description=(
                    "Update or move an existing task item by its 4-hex id. You can modify "
                    "new_content, new_status (pending, wip, done, abandoned), new_parent, "
                    "or 1-based new_position. At least one parameter must be provided."
                ),
                func=self.handle_edit_todo_item,
                args_schema=EditTodoItemInput,
            ),
            StructuredTool.from_function(
                name="delete_todo_item",
                description="Delete a task item and all of its subtasks by its 4-hex id.",
                func=self.handle_delete_todo_item,
                args_schema=DeleteTodoItemInput,
            ),
        ]

    def _get_active_thread(self) -> Thread:
        thread = self.get_thread()
        if thread is None:
            raise RuntimeError("No active thread available for task planning operation.")
        return thread

    def _persist_and_notify(self, thread: Thread) -> None:
        raw_todos = [t.model_dump(mode="json") for t in thread.todos]
        self.workspace_manager.save_thread_todos(
            self.agent_id, self.session_id, thread.id, raw_todos
        )
        if self.on_todos_changed:
            self.on_todos_changed()

    def handle_create_todo_item(
        self,
        content: str,
        status: str = "pending",
        parent_id: str | None = None,
    ) -> str:
        """Create a new task planning item."""
        clean_content = content.strip()
        if not clean_content:
            return "Error: content cannot be empty."

        try:
            norm_status = normalize_status(status)
        except ValueError as err:
            return f"Error: {err}"

        if norm_status == TodoStatus.ABANDONED.value:
            return (
                "Error: Cannot create a todo item with status 'abandoned'. "
                "Only pending, wip, or done are allowed on creation."
            )

        thread = self._get_active_thread()
        clean_parent = parent_id.strip() if parent_id and parent_id.strip() else None

        if clean_parent:
            parent_item = next((it for it in thread.todos if it.id == clean_parent), None)
            if not parent_item:
                return f"Error: Parent todo item '{clean_parent}' not found."

        existing_ids = {t.id for t in thread.todos}
        new_id = generate_unique_id(existing_ids)

        siblings = [t for t in thread.todos if t.parent_id == clean_parent]
        position = len(siblings) + 1

        new_item = TodoItem(
            id=new_id,
            content=clean_content,
            status=norm_status,
            parent_id=clean_parent,
            position=position,
            created_at=datetime.now(UTC),
        )
        thread.todos.append(new_item)

        apply_child_added_rule(thread.todos, new_item)
        self._persist_and_notify(thread)

        display_status = STATUS_DISPLAY_MAP.get(norm_status, norm_status.upper())
        return f"Created todo item ({new_id}) [{display_status}]: {clean_content}"

    def handle_edit_todo_item(
        self,
        id: str,
        new_content: str | None = None,
        new_status: str | None = None,
        new_parent: str | None = None,
        new_position: int | None = None,
    ) -> str:
        """Update or move an existing task item."""
        # 1. Call correctness checks first
        has_content = new_content is not None
        has_status = new_status is not None
        has_parent = new_parent is not None
        has_position = new_position is not None

        if not (has_content or has_status or has_parent or has_position):
            return (
                "Error: At least one of new_content, new_status, new_parent, "
                "or new_position must be provided."
            )

        clean_content: str | None = None
        if has_content:
            clean_content = str(new_content).strip()
            if not clean_content:
                return "Error: new_content cannot be empty."

        norm_status: str | None = None
        if has_status:
            try:
                norm_status = normalize_status(str(new_status))
            except ValueError as err:
                return f"Error: {err}"

        # 2. Entity existence
        clean_id = id.strip()
        thread = self._get_active_thread()
        item = next((it for it in thread.todos if it.id == clean_id), None)
        if not item:
            return f"Error: Todo item '{clean_id}' not found."

        # 3. Status transition checks: DONE cannot become ABANDONED
        if norm_status == TodoStatus.ABANDONED.value and item.status == TodoStatus.DONE.value:
            return f"Error: Cannot transition todo item '{clean_id}' from [DONE] to [ABANDONED]."

        # 4. Structural move if requested
        if has_parent or has_position:
            ok, err_msg = move_item(thread.todos, clean_id, new_parent, new_position)
            if not ok:
                return f"Error: {err_msg}"

        # 5. Apply content and status updates
        old_status = item.status
        if clean_content is not None:
            item.content = clean_content

        if norm_status is not None:
            item.status = norm_status
            propagate_state_changes(thread.todos, clean_id, old_status, norm_status)

        self._persist_and_notify(thread)
        return f"Updated todo item ({clean_id})."

    def handle_delete_todo_item(self, id: str) -> str:
        """Delete an item and all its subtasks."""
        clean_id = id.strip()
        thread = self._get_active_thread()

        target = next((it for it in thread.todos if it.id == clean_id), None)
        if not target:
            return f"Error: Todo item '{clean_id}' not found."

        descendants = get_all_descendants(thread.todos, clean_id)
        ids_to_remove = {clean_id, *(d.id for d in descendants)}

        old_parent = target.parent_id
        thread.todos = [it for it in thread.todos if it.id not in ids_to_remove]

        # Re-index siblings under old parent
        surviving_siblings = [it for it in thread.todos if it.parent_id == old_parent]
        surviving_siblings.sort(key=lambda s: (s.position, s.created_at))
        for idx, s in enumerate(surviving_siblings, start=1):
            s.position = idx

        self._persist_and_notify(thread)

        subtask_count = len(descendants)
        if subtask_count > 0:
            return f"Deleted todo item ({clean_id}) and {subtask_count} subtasks."
        return f"Deleted todo item ({clean_id})."
