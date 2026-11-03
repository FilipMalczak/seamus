# Invariants

Properties and rules that must always hold across the repository.

## Invariant Catalog

### INV-001: UV and Python 3.12 Consistency
- **Statement**: `pyproject.toml` and `uv.lock` must remain synchronized at all times. Python version requirement must be `>=3.12`.
- **Justification**: [REQ-001](./requirements.md#req-001-modern-python-312-runtime--uv-package-management), [0001-project-initialization.md](../decisions/0001-project-initialization.md).
- **Enforcement**: CI and pre-completion commands `uv run ...` and lockfile checks.

### INV-002: Zero Tooling Check Failures
- **Statement**: No task may finish or be submitted for review while any of `pytest`, `ruff check`, `ruff format --check`, or `mypy` fail.
- **Justification**: [REQ-002](./requirements.md#req-002-rigorous-code-quality--static-verification), [AGENTS.md](../AGENTS.md).
- **Enforcement**: Running full test, lint, format, and typecheck commands prior to marking task complete.

### INV-003: Knowledge Synchronization
- **Statement**: Every structural, architectural, or invariant change must be reflected in `./knowledge/` and `./decisions/` in the same branch before completion.
- **Justification**: [REQ-003](./requirements.md#req-003-traceable-architectural--durable-knowledge-documentation), [AGENTS.md](../AGENTS.md).
- **Enforcement**: Checklist in `AGENTS.md` and repository review workflow.

### INV-004: Config Completeness Invariant
- **Statement**: An Agent or Session configuration must contain a valid inference format, non-empty base URL, model name, and valid API key before a session's DeepAgent can be initialized or execute.
- **Justification**: [REQ-004](./requirements.md#req-004-config-template-singleton--derivation), [0002-harness-server-mvp.md](../decisions/0002-harness-server-mvp.md).
- **Enforcement**: Domain model validation in `AgentConfig.validate_complete()` and pre-initialization checks in session runner.

### INV-005: Single Open Thread Invariant
- **Statement**: Within any Session, exactly one thread—the most recently created one—is open (`is_open = True`). All previous threads must be closed (`is_open = False`).
- **Justification**: [REQ-006](./requirements.md#req-006-thread-redirection-event-streaming--status-tracking), [0002-harness-server-mvp.md](../decisions/0002-harness-server-mvp.md).
- **Enforcement**: Session thread management methods in `Session.create_thread()`.

### INV-006: Slug Format and Scope Uniqueness
- **Statement**: Any non-null entity name must be a slug matching `^[a-z0-9]+(?:-[a-z0-9]+)*$` and must be unique within its parent scope (agents globally, sessions per agent, threads per session).
- **Justification**: [REQ-005](./requirements.md#req-005-hierarchical-rest-api-with-dual-identifier-resolution), [0002-harness-server-mvp.md](../decisions/0002-harness-server-mvp.md).
- **Enforcement**: Slug validation in domain entities and scope check in the repository store.

### INV-007: No Resource Deletion Invariant
- **Statement**: The API surface must contain zero HTTP DELETE routes. Resources created in the harness cannot be removed via API calls.
- **Justification**: [REQ-007](./requirements.md#req-007-safe-non-destructive-api-surface), [0002-harness-server-mvp.md](../decisions/0002-harness-server-mvp.md).
- **Enforcement**: Server router definitions and automated route inspection in API test suite.

### INV-008: UI Client-Side Busy Guard
- **Statement**: The web UI must disable message submission and display active status when a thread's status is not `AWAITING_USER` or when a thread is marked closed (`is_open = False`), preventing unnecessary 409 Conflict round-trips.
- **Justification**: [REQ-008](./requirements.md#req-008-web-ui-with-navigation-tree-real-time-streaming--json-config-editor), [0003-react-web-ui.md](../decisions/0003-react-web-ui.md).
- **Enforcement**: Composer input validation and disabled state bindings in `ChatArea.tsx`.

### INV-009: Default Session and Open Thread Creation
- **Statement**: Every newly created Agent automatically initializes with one default session (`name = None`), which immediately initializes with one open thread (`name = None`), ensuring an immediate conversational context exists.
- **Justification**: [REQ-009](./requirements.md#req-009-default-session-and-open-thread-automatic-creation-zero-prompt-ux--auto-focus), [0003-react-web-ui.md](../decisions/0003-react-web-ui.md).
- **Enforcement**: `HarnessStore.create_agent()` calls `agent.create_session(name=None)`.

### INV-010: Entity Display Name Fallback
- **Statement**: In the UI navigation tree and breadcrumbs, if an entity's `name` is non-empty, that name must be displayed; if `name` is empty or null, its full UUID must be displayed.
- **Justification**: [REQ-009](./requirements.md#req-009-default-session-and-open-thread-automatic-creation-zero-prompt-ux--auto-focus), [0003-react-web-ui.md](../decisions/0003-react-web-ui.md).
- **Enforcement**: Display interpolation in `Sidebar.tsx` and `ChatArea.tsx`.

### INV-011: Zero-Prompt Creation and Auto-Focus Invariant
- **Statement**: Entity creation actions (Agent, Session, Thread) in the UI must never open modal name prompts during creation. When an entity is created or selected, the message composer input field must be focused automatically to minimize time-to-typing.
- **Justification**: [REQ-009](./requirements.md#req-009-default-session-and-open-thread-automatic-creation-zero-prompt-ux--auto-focus), [0003-react-web-ui.md](../decisions/0003-react-web-ui.md).
- **Enforcement**: Direct entity creation handlers in `Sidebar.tsx` / `App.tsx` and composer autofocus effects in `ChatArea.tsx`.

### INV-012: User Message Event Recording & Replay Invariant
- **Statement**: Every user message input dispatched to a session must be converted into AG-UI text message events (`TextMessageStartEvent` with `role = 'user'`, `TextMessageContentEvent`, `TextMessageEndEvent`) and appended to the target thread's event history as well as broadcast over SSE. Replaying thread events must preserve all user inputs alongside assistant runs across thread switches and client reconnects.
- **Justification**: [REQ-006](./requirements.md#req-006-thread-redirection-event-streaming--status-tracking), [0003-react-web-ui.md](../decisions/0003-react-web-ui.md).
- **Enforcement**: `SessionAgentRunner.dispatch_user_input()` appends user AG-UI events to `thread.events`; `useThreadStream.ts` parses `role = 'user'` text messages on replay.

### INV-013: Inline Tree Editing & Session Status Invariant
- **Statement**: The navigation tree must never trigger browser `prompt()` dialogs for renaming; editing must occur inline within the tree node label with a tick-box accept button (`<Check />`). In addition, Session nodes must visibly surface the operational status of their active open thread using standard status icons.
- **Justification**: [REQ-011](./requirements.md#req-011-inline-tree-node-renaming-and-session-node-status-visibility), [0004-inline-tree-editing-session-status.md](../decisions/0004-inline-tree-editing-session-status.md).
- **Enforcement**: `Sidebar.tsx` inline editing state and `renderSessionStatusIcon()` renderer.

### INV-014: Hierarchical Agent-Session-Thread Execution Spans
- **Statement**: Every execution run dispatched to a thread must be wrapped in a strict three-level hierarchical trace: an Agent span (`agent {agent_identifier}`) as the root enclosing a Session span (`session {session_identifier}`), which encloses a Thread span (`thread {thread_identifier}`). All underlying LangGraph graph executions, model invocations, and tool executions must execute within the Thread span context, establishing a clean child hierarchy.
- **Justification**: [REQ-012](./requirements.md#req-012-logfire-tracing-with-agent-session-and-thread-hierarchical-spans), [0005-logfire-integration.md](../decisions/0005-logfire-integration.md).
- **Enforcement**: `SessionAgentRunner._run_loop()` wraps execution in nested `logfire.span(...)` contexts with standardized attributes.

### INV-015: External System Link Visibility & Telemetry Guard
- **Statement**: External system icons in the navigation tree left panel must be strictly conditional on integration availability. The Logfire navigation icon must only render when Logfire is actively configured to send telemetry, accurately reflecting `LOGFIRE_SEND_TO_LOGFIRE` overrides and token presence. Gitea navigation icons (Home, Agent Git branch, and Session Git branch composite buttons) must only render when Gitea persistence is enabled, with contextual branch buttons reflecting active/disabled selection states. Furthermore, system `/health` heartbeat checks must never produce request telemetry spans.
- **Justification**: [REQ-013](./requirements.md#req-013-external-system-navigation-links--telemetry-visibility-guard), [REQ-015](./requirements.md#req-015-gitea-backed-versioned-agent-persistence--workspace-isolation), [0006-external-system-links.md](../decisions/0006-external-system-links.md), [0008-git-persistence.md](../decisions/0008-git-persistence.md).
- **Enforcement**: `seamus.telemetry.is_logfire_enabled()` evaluates send status and token presence; `GET /api/v-alpha/system/info` exposes `SystemInfoResponse`; `Sidebar.tsx` conditionally mounts the footer icons with contextual branch URL resolution; `instrument_fastapi` filters `/health` with `excluded_urls`.

### INV-016: AG-UI Reasoning Stream & Multi-Turn Span Message Alignment
- **Statement**: Provider reasoning deltas (`reasoning`, `reasoning_content`, `reasoning_details`) must be preserved on LangChain message chunks so `ag_ui_langgraph` emits `REASONING_*` events that are recorded in thread history, replayed over SSE, and rendered in `MessageItem.tsx`. In addition, `SeamusLangGraphAgent.langgraph_default_merge_state` must retain existing checkpoint messages ahead of new turn messages so `gen_ai.prompt.messages` remains a prefix of `gen_ai.completion.messages` on `LangGraph` spans in Logfire.
- **Justification**: [REQ-014](./requirements.md#req-014-ag-ui-reasoning-exposure--multi-turn-trace-message-alignment), [0007-agui-reasoning-and-trace-messages.md](../decisions/0007-agui-reasoning-and-trace-messages.md).
- **Enforcement**: `ReasoningChatOpenAI` and `SeamusLangGraphAgent` in `seamus.harness.runner`, `useThreadStream.ts`, `MessageItem.tsx`, and unit/telemetry test suites.

### INV-017: Git-Tracked Agent Workspace & Config Boundary
- **Statement**: The agent's persistent filesystem operations and shell execution must run inside an isolated OpenSandbox container (`SeamusOpenSandboxBackend`) with only `<session_workspace>/data/` mounted as the operational directory (`/workspace`). Agents must never have filesystem access or visibility to `agent/` or `.git/`, and the system prompt must explicitly inform the agent that `/workspace` is the Git-tracked operational directory and all paths outside it are transient.
- **Justification**: [REQ-015](./requirements.md#req-015-gitea-backed-versioned-agent-persistence--workspace-isolation), [REQ-017](./requirements.md#req-017-containerized-opensandbox-execution--operational-directory-mount), [0008-git-persistence.md](../decisions/0008-git-persistence.md), [0010-opensandbox-filesystem-sandboxing.md](../decisions/0010-opensandbox-filesystem-sandboxing.md).
- **Enforcement**: `SessionAgentRunner._build_deep_agent()` wires `SeamusOpenSandboxBackend` (mounting `data/` at `/workspace`) and `build_sandbox_system_prompt()` into `create_deep_agent`.

### INV-018: Atomic Checkpoint Data & State Persistence & Commit Delineation
- **Statement**: LangGraph checkpoints must automatically serialize state and trigger Git commits of all modified files in `data/` and `agent/state/` with commit messages prefixed with `checkpoint:`, while thread event updates commit with `state:`, and configuration changes commit the whole `agent/config/**` directory with commit messages prefixed with `config:`. Commits must be immediately pushed to the Gitea remote on the session branch or main branch.
- **Justification**: [REQ-015](./requirements.md#req-015-gitea-backed-versioned-agent-persistence--workspace-isolation), [0008-git-persistence.md](../decisions/0008-git-persistence.md).
- **Enforcement**: `GitCheckpointSaver.put()`, `aput()`, and writes hooks in `seamus.persistence`, and `HarnessStore` mutation calls to `GitWorkspaceManager`.

### INV-019: Client-Side Markdown Rendering & Content Safety
- **Statement**: All conversation messages (user and assistant) displayed in the Web UI must be parsed and rendered as Markdown through `MarkdownRenderer` with `remark-gfm`. External links must strictly enforce `target="_blank"` and `rel="noopener noreferrer"`. Code blocks and tables must be contained with overflow guards (`overflow-x: auto`) to guarantee message bubble structural integrity.
- **Justification**: [REQ-016](./requirements.md#req-016-ui-markdown-rendering), [0009-ui-markdown-renderer.md](../decisions/0009-ui-markdown-renderer.md).
- **Enforcement**: `MarkdownRenderer.tsx`, `MessageItem.tsx`, and CSS constraints in `ui/src/App.css`.

### INV-020: Runtime-Managed OpenSandbox Authentication
- **Statement**: The OpenSandbox lifecycle server API key must never be exposed to the user, `.env.template`, or external API responses. It must be autogenerated and managed internally by the runtime (`get_or_create_sandbox_api_key` and `opensandbox/entrypoint.sh`).
- **Justification**: [REQ-017](./requirements.md#req-017-containerized-opensandbox-execution--operational-directory-mount), [0010-opensandbox-filesystem-sandboxing.md](../decisions/0010-opensandbox-filesystem-sandboxing.md).
- **Enforcement**: `seamus.harness.sandbox.get_or_create_sandbox_api_key()`, `opensandbox/entrypoint.sh`, `.env.template`, and unit tests in `tests/test_sandbox.py`.

### INV-021: Agent Inspection & Credential Redaction Invariant
- **Statement**: The agent inspector report must never expose raw API keys or secrets (API keys are reported solely as a boolean `api_key_configured` flag). System prompts must be decomposed into composite, scaffold, and custom layers, and all tools must expose their JSON parameter schemas and target backend.
- **Justification**: [REQ-018](./requirements.md#req-018-deepagent-inspection-console--branch-state-provenance), [0011-agent-inspector.md](../decisions/0011-agent-inspector.md).
- **Enforcement**: `seamus.harness.inspector.build_agent_inspect_report()`, `AgentInspectReport` schema validation, and unit tests in `tests/test_inspector.py`.

### INV-022: Thread Acceptance and Sync PR Lifecycle
- **Statement**: When Gitea persistence is enabled, every active session with an open thread must maintain an open Sync PR from `session/{session_id}` to `main`. Thread acceptance must be atomic: closing the active thread, merging the active Sync PR into `main`, creating a new thread on the same session branch, and opening a renewed Sync PR to `main`. The UI must not provide manual controls to create or open arbitrary threads.
- **Justification**: [REQ-019](./requirements.md#req-019-gitea-sync-prs-and-thread-acceptance-lifecycle), [0012-sync-prs-and-thread-accept.md](../decisions/0012-sync-prs-and-thread-accept.md), [0015-session-changes-diff-tab.md](../decisions/0015-session-changes-diff-tab.md).
- **Enforcement**: `HarnessStore.accept_thread()`, `GitWorkspaceManager.open_sync_pr()`, `GitWorkspaceManager.merge_sync_pr()`, `POST .../thread/{thread_identifier}/accept`, and UI component removal of manual thread creation in `Sidebar.tsx` and `ChatArea.tsx`.

### INV-023: Tool Call Lifecycle and State Representation
- **Statement**: Tool calls must strictly progress through deterministic lifecycle states (`Pending` -> `WIP` -> `Done` or `Failed`). During argument streaming (`TOOL_CALL_START`, `TOOL_CALL_ARGS`), tool calls remain in `pending`; upon completion of argument streaming (`TOOL_CALL_END`), tool calls transition to `wip` and thread status remains in `EXECUTING_TOOL`; upon receipt of execution output (`TOOL_CALL_RESULT`), output is extracted from `content` and the call transitions to `done` (or `error` on failure). Replayed event streams and snapshots (`MESSAGES_SNAPSHOT`) must reconcile all tool calls with their final execution state without leaving calls in `Running` or resetting tool names. Within the conversation UI, thought processes, tool calls, and text responses must be interweaved in their actual chronological sequence. Completed tools and reasoning blocks whose streaming has finished (or been succeeded by another block) must automatically collapse, while preserving user manual toggle controls.
- **Justification**: [REQ-020](./requirements.md#req-020-tool-call-lifecycle-visibility--accurate-ui-stream-rendering), [0013-tool-call-lifecycle-ui.md](../decisions/0013-tool-call-lifecycle-ui.md).
- **Enforcement**: `seamus.harness.runner.SessionAgentRunner._update_status_from_event()`, `useThreadStream.ts`, `ToolCallItem.tsx`, `MessageItem.tsx`, and tests in `tests/test_runner.py`.

### INV-024: Session Changes Diff and Acceptance Placement
- **Statement**: The thread acceptance action button must be located in the dedicated "Changes" view alongside the visual diff of the active session's Sync PR rather than the conversation header, allowing visual review of codebase and state modifications before accepting. The diff must be served by `GET /api/v-alpha/agent/{agent}/session/{session}/diff` and rendered via `@pierre/diffs`.
- **Justification**: [REQ-021](./requirements.md#req-021-sync-pr-diff-inspection-and-changes-tab), [0015-session-changes-diff-tab.md](../decisions/0015-session-changes-diff-tab.md).
- **Enforcement**: `ChangesViewer.tsx`, `App.tsx`, and backend routes in `src/seamus/server/routes/sessions.py`.

### INV-025: Scope Sync PRs and Thread Acceptance Merges to data/ Deliverables
- **Statement**: Reviewable Sync PR diffs served by `GET /api/v-alpha/agent/{agent}/session/{session}/diff` and rendered in the Changes tab must strictly contain file modifications within `data/` (`a/data/` or `b/data/`), filtering out `agent/config/**` and `agent/state/**`. Furthermore, `GitWorkspaceManager.merge_sync_pr` must perform a data-scoped merge into `main` that preserves the base agent configuration and clean state on `main` without pollution or collision from session configuration or thread checkpoints.
- **Justification**: [REQ-022](./requirements.md#req-022-restrict-sync-prs-and-thread-acceptance-to-data-deliverables), [0016-sync-pr-data-scope.md](../decisions/0016-sync-pr-data-scope.md).
- **Enforcement**: `filter_sync_pr_diff()`, `GitWorkspaceManager.merge_sync_pr()`, and unit tests in `tests/test_workspace.py`.

### INV-026: Test Suite Persistence and Host Workspace Isolation
- **Statement**: Automated test suite execution must never mutate, create repositories in, or communicate with the live development Gitea instance (`http://localhost:3001`) or write to the live host workspace root (`.seamus/workspaces`). When Docker is available, persistence operations during tests must strictly target an ephemeral, SQLite-backed Gitea container allocated to an isolated dynamic port with a temporary workspace root, completely cleaned up upon test session teardown.
- **Justification**: [REQ-002](./requirements.md#req-002-rigorous-code-quality--static-verification), [0017-dedicated-test-gitea.md](../decisions/0017-dedicated-test-gitea.md).
- **Enforcement**: Pytest session fixture in `tests/conftest.py` orchestrating ephemeral container lifecycle, dynamic port binding, temporary directory management, and workspace manager singleton resetting.

### INV-027: LM-XML Dynamic System Prompt Assembly
- **Statement**: System prompts provided to language models must be formatted in deterministic XML serialized via `lmxml` from structured schema models (`SystemPromptDocument`). The prompt must be evaluated per-inference turn through `DynamicSystemPromptMiddleware`, incorporating dynamic turn context (timestamp, operational directory, session/agent ids) and user custom instructions (`<custom_instructions>`) when configured.
- **Justification**: [REQ-023](./requirements.md#req-023-dynamic-lm-xml-structured-system-prompt-architecture), [0018-dynamic-system-prompt-architecture.md](../decisions/0018-dynamic-system-prompt-architecture.md).
- **Enforcement**: `seamus.harness.prompt.build_effective_system_prompt()`, `DynamicSystemPromptMiddleware`, `SessionAgentRunner._build_deep_agent()`, and unit tests in `tests/test_prompt.py`.

### INV-028: Mode Transition Thread-Spawning Boundary
- **Statement**: Every transition between operational modes (e.g. `plan`, `chat`, `act`, `analyse`, `routing`) within a session must immediately close the active thread and spawn a new thread. No single thread may span multiple operational modes. Furthermore, mode-specific phase transitions (such as transitioning from plan formulation to plan execution in `plan` mode) must spawn a fresh thread.
- **Justification**: [0019-threads-modes-personas-architecture.md](../decisions/0019-threads-modes-personas-architecture.md), [threads_modes_personas.md](./threads_modes_personas.md).
- **Enforcement**: Session runner orchestration and domain lifecycle in `src/seamus/harness/runner.py`.

### INV-029: Session Terminal Immutability & Resource Teardown
- **Statement**: When a session enters a terminal state (`KILLED` or `FAILED`), it must permanently reject any further user message submissions (`POST .../input` returning 409 Conflict) and block thread creation. Transition to a terminal state must cancel active execution tasks, immediately destroy the session's OpenSandbox container (`sandbox_backend.destroy()`), and close the active Gitea Sync PR without merging. Killing a session during active tool execution must append interrupted `TOOL_CALL_RESULT` events (`is_error=True`) and a `RUN_ERROR` event to resolve in-flight tools, set thread status to `AgentStatus.ERROR`, and ensure the composer send button does not render in a spinning state. The kill session action must be hidden and disabled whenever a session is already in an errored state.
- **Justification**: [REQ-027](./requirements.md#req-027-terminal-session-lifecycle-states-and-teardown-guard), [0022-branching-out-and-session-lifecycle.md](../decisions/0022-branching-out-and-session-lifecycle.md).
- **Enforcement**: Domain validations in `Session.kill()`, `Session.fail()`, `SessionAgentRunner.dispatch_user_input()`, `SessionAgentRunner.kill()`, `useThreadStream.ts`, and `ChatArea.tsx`.

### INV-030: Session Branching Turn Isolation & Provenance Tracking
- **Statement**: Branching a session ($S_1$) from an assistant message must create a new session ($S_2$) whose initial thread events are strictly bounded to the end of that assistant message turn (`RUN_FINISHED`), with status initialized to `AWAITING_USER`. $S_2$'s Git branch (`session/{id}`) must originate from the exact commit SHA of that turn, and a fresh Gitea Sync PR targeting `main` must be opened. $S_2$ must record its immediate origin in `provenance` and preserve cumulative ancestor branch points in `lineage`, and $S_1$ must remain completely unmodified. Multi-level branching ($S_1 \to S_2 \to S_3$) must maintain the full lineage chain, surfacing inline provenance separators at each respective branch point. Branching must be supported from `ACTIVE`, `KILLED`, and `FAILED` sessions alike. Furthermore:
  - Branching after tool execution with `retry_inference=True` slices the thread history immediately after the tool results (`TOOL_CALL_RESULT`), copies checkpoint memory and writes to the child thread, sets the new thread status to `AWAITING_LLM`, and initiates background turn resumption.
  - Branching from a user message branches from the latest prior assistant bubble and dispatches the user prompt into the new session (or creates a clean session if branching on the initial user message).
- **Justification**: [REQ-026](./requirements.md#req-026-exact-turn-level-session-branching-and-lineage-provenance), [0022-branching-out-and-session-lifecycle.md](../decisions/0022-branching-out-and-session-lifecycle.md).
- **Enforcement**: `HarnessStore.branch_session()`, `GitWorkspaceManager.create_session_workspace()`, `GitCheckpointSaver.copy_thread()`, `SessionAgentRunner.resume_turn()`, `ChatArea.tsx`, and unit tests in `tests/test_session_branching_and_lifecycle.py`.

### INV-031: Read-Only System Skill Sandboxing & Clean Missing Directory Handling
- **Statement**: Any system-wide skill directory mounted into an OpenSandbox container must be mounted strictly read-only (`readOnly=True`) at in-sandbox paths `/skills/system/{idx}` corresponding to its 0-based index in `SystemSettings.skill_directories`. Sandboxed agent executions must not be permitted to mutate or delete files within host-level system skill directories, and host filesystem paths must never be exposed in system prompts or skill sources. All paths must expand user tilde (`~`) syntax (supporting containerized hosts via `SEAMUS_HOST_HOME`). If any configured skill directory does not exist on the host, it must be cleanly skipped without errors, warnings, or mounting attempts, while preserving index mapping for existing directories.
- **Justification**: [0024-anthropic-skills-and-system-settings.md](../decisions/0024-anthropic-skills-and-system-settings.md), [0026-in-sandbox-skill-mount-paths.md](../decisions/0026-in-sandbox-skill-mount-paths.md).
- **Enforcement**: `resolve_skill_path()` resolves tilde syntax (accounting for `SEAMUS_HOST_HOME`), verifies directory existence, `SeamusOpenSandboxBackend.build_skill_volumes()` mounts at `/skills/system/{idx}` with `readOnly=True`, and `SeamusOpenSandboxBackend.get_skill_sources()` delivers in-sandbox paths to `SessionAgentRunner._build_deep_agent()`. In Docker Compose, the host home directory is mounted read-only into the backend service so skill directories can be validated and provisioned to sibling sandbox containers.

### INV-032: System Repository Persistence Lifecycle
- **Statement**: System settings (`settings.json`, defaulting to `["~/.seamus/skills", "~/.skills"]`) and the service-wide agent configuration template (`config-template.json`) must be persisted to a dedicated `system` Git repository in Gitea, surviving server restarts with first-run defaults without requiring external databases or additional volumes.
- **Justification**: [0024-anthropic-skills-and-system-settings.md](../decisions/0024-anthropic-skills-and-system-settings.md).
- **Enforcement**: `GitWorkspaceManager.initialize_system_repo()`, `commit_system_settings()`, and `commit_system_config_template()`.

### INV-033: Configurable Todo Planning and System Prompt Composition
- **Statement**: When `session.config.todo_implementation == TodoImplementation.DEEPAGENTS`, DeepAgents instances must include `SeamusTodoListMiddleware` positioned immediately following `DynamicSystemPromptMiddleware`. `DynamicSystemPromptMiddleware` sets the base LM-XML system prompt (`build_effective_system_prompt`), and `SeamusTodoListMiddleware` appends its `WRITE_TODOS_SYSTEM_PROMPT` block without either layer clobbering the other. When `todo_implementation == TodoImplementation.NONE`, no todo middleware is added, no `write_todos` tool is available to the agent or shown in the Inspector tool list, and active todos in the Inspector are empty.
- **Justification**: [REQ-029](./requirements.md#req-029-task-planning-progress-tracking-and-todolist-middleware-integration), [0025-todo-list-middleware.md](../decisions/0025-todo-list-middleware.md).
- **Enforcement**: `SessionAgentRunner._build_deep_agent()`, `seamus.harness.inspector.build_agent_inspect_report()`, and automated tests in `tests/test_runner.py`, `tests/test_config.py`, and `tests/test_inspector.py`.

### INV-034: Dynamic Session Runner Recompilation on Save
- **Statement**: Updating a Session's configuration via `POST /agent/{id}/session/{id}` must immediately recompile the active runner's compiled graph (if cached) via `RunnerRegistry.reload_session_runner()`, ensuring the very next inference turn aligns with the updated configuration without restarting the runner process or dropping SSE listeners.
- **Justification**: [0025-todo-list-middleware.md](../decisions/0025-todo-list-middleware.md).
- **Enforcement**: `seamus.server.routes.sessions.update_session()`, `RunnerRegistry.reload_session_runner()`, and tests in `tests/test_server.py` and `tests/test_runner.py`.

### INV-035: Skill Precedence Hierarchy and In-Sandbox Isolation
- **Statement**: Sandboxed agents must access system-wide skills exclusively via in-sandbox mount paths `/skills/system/{idx}` (matching indices in `SystemSettings.skill_directories`), with zero host path exposure in system prompts or tool environments. All workspace and auxiliary project mounts must support both visible `skills` and hidden `.skills` subdirectories, where non-dotted `skills` takes precedence over dotted `.skills`. The complete skill precedence hierarchy from highest to lowest priority is: (1) future `/skills/bundled` (immutable platform skills), (2) `/workspace/skills`, (3) `/workspace/.skills`, (4) future auxiliary project mounts (`/projects/<repo>/skills` then `.skills`), and (5) system-wide directories in descending index priority (`system[0]` > `system[1]` ... > `system[last]`). DeepAgents sources passed to `create_deep_agent` must order lower-priority sources first to enforce this hierarchy under the "last one wins" rule.
- **Justification**: [0024-anthropic-skills-and-system-settings.md](../decisions/0024-anthropic-skills-and-system-settings.md), [0026-in-sandbox-skill-mount-paths.md](../decisions/0026-in-sandbox-skill-mount-paths.md).
- **Enforcement**: `SeamusOpenSandboxBackend.build_skill_volumes()`, `SeamusOpenSandboxBackend.get_skill_sources()`, `WorkspaceManager.create_session_workspace()`, and unit tests in `tests/test_sandbox.py` and `tests/test_workspace.py`.

### INV-036: Purposeful Workspace Synchronization & Auto-Pull
- **Statement**: The agent workspace is not a freely accessible content base. Any external commit landed on an agent session's Gitea branch represents an authorized, purposeful modification (such as administrator intervention or manual skill provisioning). The harness must auto-pull remote changes with rebase (`sync_session_workspace`) upon session checkout and prior to each inference turn loop, ensuring external changes immediately reflect in the agent's live workspace and OpenSandbox container, and automatically rebase checkpoint commits if remote advanced.
- **Justification**: [0008-git-persistence.md](../decisions/0008-git-persistence.md), [0026-in-sandbox-skill-mount-paths.md](../decisions/0026-in-sandbox-skill-mount-paths.md).
- **Enforcement**: `GitWorkspaceManager.sync_session_workspace()`, `GitWorkspaceManager.create_session_workspace()`, `SessionAgentRunner._run_loop()`, `GitWorkspaceManager.commit_checkpoint_changes()`, and unit tests in `tests/test_workspace.py`.

## Cross-References
- [backlog.md](./backlog.md)
- [requirements.md](./requirements.md)
- [threads_modes_personas.md](./threads_modes_personas.md)
- [0001-project-initialization.md](../decisions/0001-project-initialization.md)
- [0002-harness-server-mvp.md](../decisions/0002-harness-server-mvp.md)
- [0003-react-web-ui.md](../decisions/0003-react-web-ui.md)
- [0004-inline-tree-editing-session-status.md](../decisions/0004-inline-tree-editing-session-status.md)
- [0005-logfire-integration.md](../decisions/0005-logfire-integration.md)
- [0006-external-system-links.md](../decisions/0006-external-system-links.md)
- [0007-agui-reasoning-and-trace-messages.md](../decisions/0007-agui-reasoning-and-trace-messages.md)
- [0008-git-persistence.md](../decisions/0008-git-persistence.md)
- [0009-ui-markdown-renderer.md](../decisions/0009-ui-markdown-renderer.md)
- [0010-opensandbox-filesystem-sandboxing.md](../decisions/0010-opensandbox-filesystem-sandboxing.md)
- [0011-agent-inspector.md](../decisions/0011-agent-inspector.md)
- [0012-sync-prs-and-thread-accept.md](../decisions/0012-sync-prs-and-thread-accept.md)
- [0013-tool-call-lifecycle-ui.md](../decisions/0013-tool-call-lifecycle-ui.md)
- [0014-ui-layout-proportions-breadcrumbs.md](../decisions/0014-ui-layout-proportions-breadcrumbs.md)
- [0015-session-changes-diff-tab.md](../decisions/0015-session-changes-diff-tab.md)
- [0016-sync-pr-data-scope.md](../decisions/0016-sync-pr-data-scope.md)
- [0017-dedicated-test-gitea.md](../decisions/0017-dedicated-test-gitea.md)
- [0018-dynamic-system-prompt-architecture.md](../decisions/0018-dynamic-system-prompt-architecture.md)
- [0019-threads-modes-personas-architecture.md](../decisions/0019-threads-modes-personas-architecture.md)
- [0022-branching-out-and-session-lifecycle.md](../decisions/0022-branching-out-and-session-lifecycle.md)
- [0024-anthropic-skills-and-system-settings.md](../decisions/0024-anthropic-skills-and-system-settings.md)
- [0025-todo-list-middleware.md](../decisions/0025-todo-list-middleware.md)
- [0026-in-sandbox-skill-mount-paths.md](../decisions/0026-in-sandbox-skill-mount-paths.md)
