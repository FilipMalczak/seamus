# 0025. TodoListMiddleware Integration, Prompt Composition, and Inspector Task Tracking

Date: 2026-11-03

## Status

Accepted

## Context

Task planning and progress tracking are essential for autonomous agent workflows on non-trivial, multi-step engineering tasks. In LangChain's agent ecosystem, `TodoListMiddleware` provides the structured `write_todos` tool, maintains task states (`pending`, `in_progress`, `completed`) in `PlanningState`, and appends task management prompt guidance.

However, in Seamus:
1. DeepAgents no longer includes `TodoListMiddleware` or `write_todos` in its default tool suite; only specific model profiles (such as OpenAI Codex) inject it via `extra_middleware`.
2. Seamus's runner stack (`SessionAgentRunner._build_deep_agent`) omitted `TodoListMiddleware` entirely.
3. Seamus generates structured dynamic LM-XML prompts via `DynamicSystemPromptMiddleware`. If `DynamicSystemPromptMiddleware` executes after other system-prompt-altering middleware without appending or preserving prior content, it replaces `request.system_message` with its generated prompt, wiping out downstream or upstream prompt blocks.
4. The Agent Inspector backend and frontend did not list `write_todos` offline or expose active session todos from checkpoint state.

## Decision

1. **Incorporate `TodoListMiddleware` into DeepAgent Construction**:
   - In `SessionAgentRunner._build_deep_agent()`, import `TodoListMiddleware` from `langchain.agents.middleware`.
   - Instantiate `todo_list_middleware = TodoListMiddleware()` for each session agent.
   - Register it in `create_deep_agent(..., middleware=[dynamic_prompt_middleware, todo_list_middleware])`.

2. **Middleware Ordering and System Prompt Composition**:
   - `DynamicSystemPromptMiddleware` is placed first in the user middleware list so that it dynamically establishes Seamus's base LM-XML system prompt (`build_effective_system_prompt(...)`) per inference turn.
   - `TodoListMiddleware` is placed subsequent to `DynamicSystemPromptMiddleware`. When `TodoListMiddleware.awrap_model_call` executes, it appends its `WRITE_TODOS_SYSTEM_PROMPT` block directly onto the dynamic system prompt established by `DynamicSystemPromptMiddleware`.
   - The provider receives both the structured Seamus XML prompt and the `## write_todos` guidance block in a clean, multi-part system message.

3. **Offline Schema & Inspector Tool Discovery**:
   - In `seamus.harness.inspector.get_default_tools_inspect_info()`, include `TodoListMiddleware()` when compiling the dummy graph, ensuring `write_todos` is discovered and its arguments schema is cached even when no active runner exists.
   - Classify `write_todos` with `backend = "harness"`, distinguishing it from containerized `"opensandbox"` filesystem operations.

4. **Inspector Task Tracking & UI Surface**:
   - Extend `AgentInspectReport` in `seamus.harness.inspector` with `todos: list[TodoInspectItem] = Field(default_factory=list)`, where `TodoInspectItem` captures `content` and `status` (`pending`, `in_progress`, `completed`).
   - In `extract_agent_inspect_info()`, inspect the latest thread checkpoint tuple or active graph state for `todos`, deserializing and populating `report.todos`.
   - In the web UI (`AgentInspector.tsx`), introduce a dedicated **Todos** tab displaying active task items, status indicators, and total counts.

## Consequences

- Agents across all model providers have immediate, out-of-the-box access to `write_todos` for structured task breakdown and real-time state tracking.
- System prompt sent to providers reliably includes both Seamus LM-XML context and `write_todos` operational guidance.
- Users gain explicit, real-time visibility into the agent's internal task plan in the inspector UI.
- `PlanningState` (`todos` list) is saved transparently in `GitCheckpointSaver` during regular turn commits.

