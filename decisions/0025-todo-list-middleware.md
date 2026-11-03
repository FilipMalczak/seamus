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

1. **Configurable Planning Layer and `todo_implementation` Enum**:
   - Introduce `TodoImplementation(StrEnum)` with allowed values `none` and `deepagents`.
   - Add `todo_implementation: TodoImplementation = TodoImplementation.NONE` to `AgentConfig`, supported across Template, Agent, and Session configuration levels with inheritance via `copy_with_overrides`.
   - Validate strictly on save; invalid values are rejected with 422 Unprocessable Entity and surfaced cleanly in the UI modal.
   - Decouple planning architecture to allow future custom planning toolsets alongside DeepAgents middleware.

2. **Incorporate `TodoListMiddleware` Conditionally**:
   - In `SessionAgentRunner._build_deep_agent()`, conditionally register `SeamusTodoListMiddleware()` only when `session.config.todo_implementation == TodoImplementation.DEEPAGENTS`.
   - When set to `none`, omit todo middleware, preventing any todo tools, prompts, or state overhead from leaking to the agent.

3. **Dynamic Graph Reloading on Session Configuration Save**:
   - Provide `SessionAgentRunner.reload_config(session)` and `RunnerRegistry.reload_session_runner(session)`.
   - Upon updating session configuration via `POST /agent/{id}/session/{id}`, immediately reload the cached runner's compiled graph so the very next inference turn aligns with the updated configuration without needing a process restart.

4. **Middleware Ordering and System Prompt Composition**:
   - When enabled, `DynamicSystemPromptMiddleware` is placed first in the user middleware list so that it dynamically establishes Seamus's base LM-XML system prompt (`build_effective_system_prompt(...)`) per inference turn.
   - `TodoListMiddleware` is placed subsequent to `DynamicSystemPromptMiddleware`. When `TodoListMiddleware.awrap_model_call` executes, it appends its `WRITE_TODOS_SYSTEM_PROMPT` block directly onto the dynamic system prompt established by `DynamicSystemPromptMiddleware`.
   - The provider receives both the structured Seamus XML prompt and the `## write_todos` guidance block in a clean, multi-part system message.

5. **Inspector Alignment & Tool Discovery**:
   - In `seamus.harness.inspector.get_default_tools_inspect_info()`, include `TodoListMiddleware()` when compiling the dummy graph, ensuring `write_todos` is discovered and its arguments schema is cached offline with `backend = "harness"`.
   - In `build_agent_inspect_report`, if `session.config.todo_implementation == TodoImplementation.NONE`, filter out `write_todos` from reported tools and return an empty `todos` list.
   - Extend `AgentInspectReport` with `todos: list[TodoInspectItem] = Field(default_factory=list)` and display active todos in the **Todos** tab of the inspector UI.

## Consequences

- Sessions can selectively enable DeepAgents `TodoListMiddleware` or disable task list tooling entirely (`none`), preparing Seamus for custom planning toolsets.
- System prompt and available tools immediately align with `todo_implementation` upon saving session configuration.
- System prompt sent to providers reliably includes both Seamus LM-XML context and `write_todos` operational guidance when enabled.
- Users gain explicit, real-time visibility into the agent's internal task plan in the inspector UI.
- `PlanningState` (`todos` list) is saved transparently in `GitCheckpointSaver` during regular turn commits.

