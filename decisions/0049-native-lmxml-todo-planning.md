# 0049. Native LM-XML Hierarchical Planning Toolset

Date: 2026-11-09

## Status

Accepted

## Context

Task planning and progress tracking in Seamus were previously integrated via DeepAgents' built-in `TodoListMiddleware` ([0025-todo-list-middleware.md](./0025-todo-list-middleware.md)).

However, `TodoListMiddleware` suffered from significant architectural limitations:
1. **System Prompt Clutter**: Injected raw, flat markdown guidance (`## write_todos`) outside of Seamus's structured LM-XML dynamic system prompt architecture ([0018-dynamic-system-prompt-architecture.md](./0018-dynamic-system-prompt-architecture.md)).
2. **Monolithic Tool Interface**: Provided only a single `write_todos` tool, requiring the agent to rewrite and re-transmit the entire task array on every modification, leading to high token expenditure and state corruption risk.
3. **Flat Task Representation**: Did not support task decomposition, parent-child hierarchies, or subtask organization.
4. **Lack of Lifecycle Invariants**: Could not model skipped/abandoned tasks or maintain consistency between parent objectives and subtask progress.

Following the successful native rewrite of the skills system ([0048-native-lmxml-skills-system.md](./0048-native-lmxml-skills-system.md)), this decision introduces a first-party, native Seamus task planning implementation (`todo_implementation = TodoImplementation.SEAMUS`).

## Decision

1. **Configurable Planning Implementation and Default Alignment**:
   - Add `TodoImplementation.SEAMUS = "seamus"` and set it as the default across `AgentConfig`.
   - Retain `deepagents` and `none` for backward compatibility.
   - Decouple planning execution cleanly between DeepAgents middleware and Seamus native tools.

2. **LM-XML Dynamic Prompt Embedding**:
   - Model the active plan in `SystemPromptDocument` (`src/seamus/harness/prompt.py`) via the `<plan>` element.
   - When todos exist on the active thread, serialize them into an indented, 1-based hierarchical tree.
   - When no todos exist (`plan is None`), cleanly omit the `<plan>` element from the serialized LM-XML prompt via `exclude_none=True`.

3. **Hierarchical Tree Representation & Stable IDs**:
   - Assign each task an immutable 4-hex identifier (`uuid4().hex[-4:]`) upon creation. All tool calls target stable IDs, never paths.
   - Represent hierarchical depth using 1-based advisory paths (`1.`, `1.1.`, `1.2.`) and 2-space indentation. Paths are dynamically re-indexed when tasks are moved or deleted.
   - Format each line as `<indent><path> (<id>) [<status>] <content>`.
   - Support four task statuses: `pending` (`[TODO]`), `wip` (`[WIP]`), `done` (`[DONE]`), and `abandoned` (`[ABANDONED]`).

4. **Discrete Atomic Planning Toolset**:
   Implement `SeamusTodoMiddleware` registering three first-party agent tools:
   - `create_todo_item(content: str, status: str = "pending", parent_id: str | None = None) -> str`: Validates non-empty content and status (`pending`, `wip`, `done`; `abandoned` rejected on create). Verifies `parent_id` exists if supplied.
   - `edit_todo_item(id: str, new_content: str | None = None, new_status: str | None = None, new_parent: str | None = None, new_position: int | None = None) -> str`: Validates call correctness (at least one parameter provided) before entity checks. Validates status transitions (`DONE` cannot transition to `ABANDONED`). Supports atomic subtree reparenting and 1-based reordering with cycle detection and self-parenting prevention.
   - `delete_todo_item(id: str) -> str`: Recursively cascades deletion through the entire subtree rooted at `id` and re-indexes surviving siblings.

5. **Depth-First Auto-State Machine**:
   - **Rule 1 (Parent becomes CLOSED)**: When a parent transitions to `CLOSED` (`DONE` or `ABANDONED`), its `WIP` children take the parent's closed status, and its `PENDING` children become `ABANDONED` (cascading recursively).
   - **Rule 2 (Child added OPEN under DONE parent)**: When a new child is added with status OPEN (`pending` or `wip`) under a `DONE` parent, the parent (and its ancestor chain, depth-first) transitions to `WIP`.
   - **Rule 3 (Child reopened under DONE parent)**: When an existing child transitions from `CLOSED` to `OPEN` under a `DONE` parent, the parent (and its ancestor chain, depth-first) transitions to `WIP`.

6. **Thread-Scoped Entity Persistence & Inspector Observability**:
   - Store `todos: list[TodoItem] = Field(default_factory=list)` directly on `Thread` (`src/seamus/domain/entities.py`), persisting to `<thread_state_dir>/todos.json`.
   - Surface hierarchical paths, IDs, depths, and statuses in `AgentInspector.tsx` and allow configuration in `ConfigModal.tsx`.

## Consequences

### Positive
- Strict alignment with Seamus's structured LM-XML dynamic system prompt architecture.
- Replaces bulky whole-array rewriting with surgical atomic tool calls.
- Full hierarchical task decomposition with 1-based paths and stable short IDs.
- Deterministic auto-state rules eliminate contradictory task states (such as closed parents with running children).
- Full backwards compatibility with `deepagents` and `none` implementations.

### Negative / Trade-offs
- Model must reference 4-hex IDs rather than numeric paths in tool invocations.
- Deferring plan cleanup and compaction tools requires periodic manual pruning in exceptionally long sessions.

