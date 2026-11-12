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
- **Statement**: Within any Session, exactly one thread—the most recently created or active one—is open (`is_open = True`). All previous threads must be closed (`is_open = False`). When a new thread is requested or a mode is switched on an empty thread (`is_empty = True`), the empty thread is reused in place rather than closed, preserving single open thread invariants without creating orphaned threads.
- **Justification**: [REQ-006](./requirements.md#req-006-thread-redirection-event-streaming--status-tracking), [0002-harness-server-mvp.md](../decisions/0002-harness-server-mvp.md), [0030-operational-modes-and-plan-mode.md](../decisions/0030-operational-modes-and-plan-mode.md).
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
- **Statement**: The agent's persistent filesystem operations and shell execution must run inside an isolated OpenSandbox container (`SeamusOpenSandboxBackend`) with only `<session_workspace>/data/` mounted as the operational directory (`/workspace`). Containers execute with a first-party developer runtime image (`seamus-sandbox:latest` containing Python 3, Astral `uv`, Node.js, npm, Git, and build essentials) or a custom image configured per agent/session via `sandbox_image`. Agents must never have filesystem access or visibility to `agent/` or `.git/`, and the system prompt must explicitly inform the agent that `/workspace` is the Git-tracked operational directory and all paths outside it are transient.
- **Justification**: [REQ-015](./requirements.md#req-015-gitea-backed-versioned-agent-persistence--workspace-isolation), [REQ-017](./requirements.md#req-017-containerized-opensandbox-execution--operational-directory-mount), [0008-git-persistence.md](../decisions/0008-git-persistence.md), [0010-opensandbox-filesystem-sandboxing.md](../decisions/0010-opensandbox-filesystem-sandboxing.md), [0043-dedicated-developer-sandbox-image.md](../decisions/0043-dedicated-developer-sandbox-image.md).
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
- **Statement**: System prompts provided to language models must be formatted in deterministic XML serialized via `lmxml` from structured schema models (`SystemPromptDocument`). The prompt must be evaluated per-inference turn through `DynamicSystemPromptMiddleware`, incorporating dynamic turn context (timestamp, operational directory, session/agent ids), discovered workspace project rules (`<project_rules>` from `AGENTS.md` and `.seamus/rules/`), and user custom instructions (`<custom_instructions>`) when configured.
- **Justification**: [REQ-023](./requirements.md#req-023-dynamic-lm-xml-structured-system-prompt-architecture), [0018-dynamic-system-prompt-architecture.md](../decisions/0018-dynamic-system-prompt-architecture.md), [0027-skills-config-project-rules-and-inspector.md](../decisions/0027-skills-config-project-rules-and-inspector.md).
- **Enforcement**: `seamus.harness.prompt.build_effective_system_prompt()`, `discover_project_rules()`, `DynamicSystemPromptMiddleware`, `SessionAgentRunner._build_deep_agent()`, and unit tests in `tests/test_prompt.py`.

### INV-028: Mode Transition Thread-Spawning Boundary
- **Statement**: Operational mode is a first-class property of `AgentConfig` (`AgentConfig.mode`), defaulting to `plan` (discuss phase), and initial session threads inherit the session's configured mode. Every transition between operational modes (e.g. `plan`, `chat`, `act`, `analyse`, `routing`) within a session must immediately update `session.config.mode`, persist the session configuration to Git, and either reuse an empty open thread in place or close the active thread and spawn a new thread. No single thread may span multiple operational modes. Furthermore, mode-specific phase transitions (such as transitioning from discuss to make to execute in `plan` mode) spawn a fresh thread with clean checkpoint history while maintaining state in `/workspace` and `/artifacts`.
- **Justification**: [0019-threads-modes-personas-architecture.md](../decisions/0019-threads-modes-personas-architecture.md), [0030-operational-modes-and-plan-mode.md](../decisions/0030-operational-modes-and-plan-mode.md), [0032-operational-mode-in-agent-config-and-defaults.md](../decisions/0032-operational-mode-in-agent-config-and-defaults.md), [threads_modes_personas.md](./threads_modes_personas.md).
- **Enforcement**: Session runner orchestration and domain lifecycle in `src/seamus/harness/runner.py`, `src/seamus/harness/store.py`, and `Session.create_thread(reuse_empty=True)`.

### INV-029: Session Terminal Immutability & Resource Teardown
- **Statement**: When a session enters a terminal state (`KILLED` or `FAILED`), it must permanently reject any further user message submissions (`POST .../input` returning 409 Conflict) and block thread creation. Transition to a terminal state must cancel active execution tasks, immediately destroy the session's OpenSandbox container (`sandbox_backend.destroy()`), and close the active Gitea Sync PR without merging. Killing a session during active tool execution must append interrupted `TOOL_CALL_RESULT` events (`is_error=True`) and a `RUN_ERROR` event to resolve in-flight tools, set thread status to `AgentStatus.ERROR`, and ensure the composer send button does not render in a spinning state. The kill session action must be hidden and disabled whenever a session is already in an errored state.
- **Justification**: [REQ-027](./requirements.md#req-027-terminal-session-lifecycle-states-and-teardown-guard), [0022-branching-out-and-session-lifecycle.md](../decisions/0022-branching-out-and-session-lifecycle.md).
- **Enforcement**: Domain validations in `Session.kill()`, `Session.fail()`, `SessionAgentRunner.dispatch_user_input()`, `SessionAgentRunner.kill()`, `useThreadStream.ts`, and `ChatArea.tsx`.

### INV-030: Session Branching Turn Isolation & Provenance Tracking
- **Statement**: Branching a session ($S_1$) can target any historical item ($I$: user message, synthetic system event, bot message, bot reasoning block, or tool call) with position $P \in \{\text{before}, \text{after}\}$, or an assistant turn identifier via legacy parameters:
  - *Branch Before*:
    - **User message / system event**: Slices history prior to the message/event, returning the child session to `AWAITING_USER` state with workspace Git commit resolved to the immediate parent (`commit~1`).
    - **Bot message / thinking**: Truncates history prior to the generation and sets status to `AWAITING_LLM`, re-running inference to produce a fresh response.
    - **Tool call / group**: Slices the thread prior to tool execution (before `TOOL_CALL_RESULT`), setting status to `AWAITING_LLM` and restarting all tools in the group.
  - *Branch After*:
    - **User message / system event**: Slices history including the user message or synthetic event, sets status to `AWAITING_LLM`, and starts inference on the prompt.
    - **Bot message**: Slices history including the assistant message. If the turn finished with no subsequent tools, sets status to `AWAITING_USER` (including `RUN_FINISHED`), otherwise continues processing (`AWAITING_LLM`).
    - **Bot thinking**: Slices history including reasoning tokens and resumes inference (`AWAITING_LLM`).
    - **Tool call / group**: Slices history including all tool results (`TOOL_CALL_RESULT`) from the parent session and resumes execution (`AWAITING_LLM`).
  - $S_2$'s Git branch (`session/{id}`) must originate from the exact commit SHA corresponding to the slice point (resolving parent commit `sha~1` when branching before an event), and a fresh Gitea Sync PR targeting `main` must be opened. $S_2$'s open thread must preserve the parent thread's operational `mode`, `phase`, `active_skills`, and `todos` (and `active_plan_id` on the session). $S_2$ must record its immediate origin in `provenance` (recording `branch_position`, `item_type`, and `preceding_message_id`) and preserve cumulative ancestor branch points in `lineage`, and $S_1$ must remain completely unmodified. Multi-level branching ($S_1 \to S_2 \to S_3$) must maintain the full lineage chain, surfacing inline provenance separators at each respective branch point: above or below target bubbles for messages/reasoning, and for tool calls/groups running underneath the tool call bubble(s) at the vertical midpoint with the provenance pill to the right when branched before, or below the tool call/group when branched after. Branching must be supported from `ACTIVE`, `KILLED`, and `FAILED` sessions alike.
- **Justification**: [REQ-026](./requirements.md#req-026-exact-turn-level-session-branching-and-lineage-provenance), [0022-branching-out-and-session-lifecycle.md](../decisions/0022-branching-out-and-session-lifecycle.md), [0054-granular-bidirectional-session-branching.md](../decisions/0054-granular-bidirectional-session-branching.md).
- **Enforcement**: `HarnessStore.branch_session()`, `HarnessStore._find_branch_slice_point()`, `GitWorkspaceManager.find_commit_for_event(before=...)`, `GitWorkspaceManager.create_session_workspace()`, `GitCheckpointSaver.copy_thread()`, `SessionAgentRunner.resume_turn()`, `BubbleBranchActions` in `MessageItem.tsx`, and unit tests in `tests/test_session_branching_and_lifecycle.py`.

### INV-031: Read-Only System Skill Sandboxing & Clean Missing Directory Handling
- **Statement**: Any system-wide skill directory mounted into an OpenSandbox container must be mounted strictly read-only (`readOnly=True`) at in-sandbox paths `/skills/system/{idx}` corresponding to its 0-based index in `SystemSettings.skill_directories`. Sandboxed agent executions must not be permitted to mutate or delete files within host-level system skill directories, and host filesystem paths must never be exposed in system prompts or skill sources. All paths must expand user tilde (`~`) syntax (supporting containerized hosts via `SEAMUS_HOST_HOME`). If any configured skill directory does not exist on the host, it must be cleanly skipped without errors, warnings, or mounting attempts, while preserving index mapping for existing directories.
- **Justification**: [0024-anthropic-skills-and-system-settings.md](../decisions/0024-anthropic-skills-and-system-settings.md), [0026-in-sandbox-skill-mount-paths.md](../decisions/0026-in-sandbox-skill-mount-paths.md).
- **Enforcement**: `resolve_skill_path()` resolves tilde syntax (accounting for `SEAMUS_HOST_HOME`), verifies directory existence, `SeamusOpenSandboxBackend.build_skill_volumes()` mounts at `/skills/system/{idx}` with `readOnly=True`, and `SeamusOpenSandboxBackend.get_skill_sources()` delivers in-sandbox paths to `SessionAgentRunner._build_deep_agent()`. In Docker Compose, the host home directory is mounted read-only into the backend service so skill directories can be validated and provisioned to sibling sandbox containers.

### INV-032: System Repository Persistence Lifecycle
- **Statement**: System settings (`settings.json`, defaulting to `["~/.seamus/skills", "~/.skills"]`) and the service-wide agent configuration template (`config-template.json`) must be persisted to a dedicated `system` Git repository in Gitea, surviving server restarts with first-run defaults without requiring external databases or additional volumes.
- **Justification**: [0024-anthropic-skills-and-system-settings.md](../decisions/0024-anthropic-skills-and-system-settings.md).
- **Enforcement**: `GitWorkspaceManager.initialize_system_repo()`, `commit_system_settings()`, and `commit_system_config_template()`.

### INV-033: Configurable Todo and Skills Middleware and System Prompt Composition
- **Statement**: Both `todo_implementation` and `skills_implementation` on `AgentConfig` default to `seamus`. When `session.config.todo_implementation == TodoImplementation.SEAMUS`, instances register native `SeamusTodoMiddleware` providing three discrete tools (`create_todo_item`, `edit_todo_item`, `delete_todo_item`) targeting stable 4-hex short IDs, dynamic 1-based advisory paths, and deterministic depth-first auto-state propagation; the active plan is embedded directly in the structured LM-XML system prompt within `<plan>`, cleanly omitted when empty. When `session.config.todo_implementation == TodoImplementation.DEEPAGENTS`, DeepAgents instances include `SeamusTodoListMiddleware` (`write_todos`) appending raw markdown guidance. When `todo_implementation == TodoImplementation.NONE`, no todo tools are available and todos are reported empty. Similarly, when `skills_implementation == SkillsImplementation.SEAMUS`, native `SeamusSkillsMiddleware` manages explicit load/unload tools; when `skills_implementation == SkillsImplementation.DEEPAGENTS`, in-sandbox skill sources are passed to `create_deep_agent`; when `none`, skills are disabled.
- **Justification**: [REQ-029](./requirements.md#req-029-task-planning-progress-tracking-and-todolist-middleware-integration), [0025-todo-list-middleware.md](../decisions/0025-todo-list-middleware.md), [0027-skills-config-project-rules-and-inspector.md](../decisions/0027-skills-config-project-rules-and-inspector.md), [0048-native-lmxml-skills-system.md](../decisions/0048-native-lmxml-skills-system.md), [0049-native-lmxml-todo-planning.md](../decisions/0049-native-lmxml-todo-planning.md).
- **Enforcement**: `SessionAgentRunner._build_deep_agent()`, `seamus.harness.todos.SeamusTodoMiddleware`, `seamus.harness.inspector.build_agent_inspect_report()`, and automated tests in `tests/test_todos.py`, `tests/test_runner.py`, `tests/test_config.py`, and `tests/test_inspector.py`.

### INV-034: Dynamic Session Runner Recompilation on Save
- **Statement**: Updating a Session's configuration via `POST /agent/{id}/session/{id}` must immediately recompile the active runner's compiled graph (if cached) via `RunnerRegistry.reload_session_runner()`, ensuring the very next inference turn aligns with the updated configuration without restarting the runner process or dropping SSE listeners.
- **Justification**: [0025-todo-list-middleware.md](../decisions/0025-todo-list-middleware.md).
- **Enforcement**: `seamus.server.routes.sessions.update_session()`, `RunnerRegistry.reload_session_runner()`, and tests in `tests/test_server.py` and `tests/test_runner.py`.

### INV-035: Skill Precedence Hierarchy and In-Sandbox Isolation
- **Statement**: Sandboxed agents must access system-wide skills exclusively via in-sandbox mount paths `/skills/system/{idx}` (matching indices in `SystemSettings.skill_directories`), with zero host path exposure in system prompts or tool environments. All workspace and auxiliary project mounts must support both visible `skills` and hidden `.skills` subdirectories, where non-dotted `skills` takes precedence over dotted `.skills`. The complete skill precedence hierarchy from highest to lowest priority is: (1) `/skills/bundled` (immutable platform skills), (2) `/workspace/skills`, (3) `/workspace/.skills`, (4) mounted external projects in configured order (`/projects/{mount_name}` where `projects[0]` > `projects[1]` > ..., with `.../skills` > `.../.skills` within each project), and (5) system-wide directories in descending index priority (`system[0]` > `system[1]` ... > `system[last]`). DeepAgents sources passed to `create_deep_agent` must order lower-priority sources first to enforce this hierarchy under the "last one wins" rule.
- **Justification**: [0024-anthropic-skills-and-system-settings.md](../decisions/0024-anthropic-skills-and-system-settings.md), [0026-in-sandbox-skill-mount-paths.md](../decisions/0026-in-sandbox-skill-mount-paths.md), [0036-mount-bundled-skills-via-shared-volume.md](../decisions/0036-mount-bundled-skills-via-shared-volume.md), [0047-discovered-context-and-project-skills.md](../decisions/0047-discovered-context-and-project-skills.md).
- **Enforcement**: `SeamusOpenSandboxBackend.build_skill_volumes()`, `SeamusOpenSandboxBackend.build_bundled_skill_volume()`, `SeamusOpenSandboxBackend.get_skill_sources()`, `extract_session_skills()`, and unit tests in `tests/test_sandbox.py`, `tests/test_workspace.py`, `tests/test_bundled_skills.py`, and `tests/test_inspector.py`.

### INV-047: Bundled Platform Skills Shared Volume Sandboxing
- **Statement**: Built-in platform skills (`src/seamus/skills/bundled/`, e.g. `artifacts` and `a2ui_components`) must be mounted into OpenSandbox containers at `/skills/bundled` strictly read-only (`readOnly=True`). In containerized deployments where `workspace_volume` is configured, platform skills must be synchronized into shared workspace volume storage at `workspace_root / "bundled_skills"` and mounted via `pvc=PVC(claimName=workspace_volume, subPath="bundled_skills", createIfNotExists=True, deleteOnSandboxTermination=False)` to prevent empty host-bind mount collisions from sibling container isolation. In non-containerized environments, mounting falls back to direct host path binding.
- **Justification**: [0026-in-sandbox-skill-mount-paths.md](../decisions/0026-in-sandbox-skill-mount-paths.md), [0036-mount-bundled-skills-via-shared-volume.md](../decisions/0036-mount-bundled-skills-via-shared-volume.md).
- **Enforcement**: `seamus.harness.sandbox.sync_bundled_skills()`, `SeamusOpenSandboxBackend.build_bundled_skill_volume()`, `GitWorkspaceManager.__init__()`, and unit tests in `tests/test_bundled_skills.py`.

### INV-036: Purposeful Workspace Synchronization & Auto-Pull
- **Statement**: The agent workspace is not a freely accessible content base. Any external commit landed on an agent session's Gitea branch represents an authorized, purposeful modification (such as administrator intervention or manual skill provisioning). The harness must auto-pull remote changes with rebase (`sync_session_workspace`) upon session checkout and prior to each inference turn loop, ensuring external changes immediately reflect in the agent's live workspace and OpenSandbox container, and automatically rebase checkpoint commits if remote advanced.
- **Justification**: [0008-git-persistence.md](../decisions/0008-git-persistence.md), [0026-in-sandbox-skill-mount-paths.md](../decisions/0026-in-sandbox-skill-mount-paths.md).
- **Enforcement**: `GitWorkspaceManager.sync_session_workspace()`, `GitWorkspaceManager.create_session_workspace()`, `SessionAgentRunner._run_loop()`, `GitWorkspaceManager.commit_checkpoint_changes()`, and unit tests in `tests/test_workspace.py`.

### INV-039: Verbose `RUN_ERROR` Event Persistence & UI State Synchronization
- **Statement**: When an unhandled exception occurs during `SessionAgentRunner._run_loop()`, the emitted `RUN_ERROR` event must include `error_type` (exception class name) and `traceback` (formatted stack trace) alongside `message`, and must be appended to `thread.events` before broadcasting so replayed streams preserve full failure diagnostics. In the Web UI, the active agent, session, thread, and main panel tab must stay synchronized with URL query parameters (`?agent=...&session=...&thread=...&tab=...`), and both the Changes diff view and sidebar tree must automatically refresh across active execution turns.
- **Justification**: [REQ-032](./requirements.md#req-032-ui-url-state-synchronization-live-refresh-and-verbose-error-diagnostics), [0028-ui-ux-ergonomics-and-url-state.md](../decisions/0028-ui-ux-ergonomics-and-url-state.md).
- **Enforcement**: `SessionAgentRunner._run_loop()`, `useAgentsTree.ts`, `App.tsx`, `ChangesViewer.tsx`, `useThreadStream.ts`, `ChatArea.tsx`, and unit tests in `tests/test_runner.py`.

### INV-040: Artifact Hierarchy, Read-Only Sandboxing, and Atomic Interaction Lifecycle
- **Statement**: Session artifacts are stored in `<session_workspace>/artifacts/<family>/<uuid>/`, mounted into OpenSandbox containers at `/artifacts` strictly read-only (`readOnly=True`), and committed to Git on session branches. Artifact instances contain `manifest.json`, `body.json`, pretty-printed `state.json` (recording `state.last_event`), `closed.marker`, `/interactions/<button_id>.jsonl` (recording untrimmed raw event history as JSONL), and auxiliary `answers.md` for question-centric artifacts. Dynamic context pointers (`{path: ...}`) on button action contexts are disallowed and automatically dropped during normalization with mutation logging; input widget snapshots are captured automatically by value in event `data` on click. `body.json` must exist before or at the creation of `manifest.json` (absence triggers unrecoverable `ERROR` turn state requiring session branching). Before storing artifact files or emitting `ARTIFACT_CREATED`, custom artifact generation via `make_artifact` must validate the component tree and manifest against A2UI surface rendering rules (`validate_a2ui_surface`); if any errors are detected, the artifact is not stored on disk, no event is emitted, and the tool returns a message listing the errors and explicitly confirming that the artifact was not stored. Component trees are loosely normalized by `normalize_a2ui_components` prior to validation (auto-assigning missing IDs, mapping type aliases such as `"type"` or `"component_type"` and casing, inferring component types from properties, synthesizing child `Text` for buttons, adapting `Card` containers with title/body/children, auto-declaring undeclared manifest buttons, and auto-synthesizing an enclosing root `Column` container if `id="root"` is missing); when mutations occur, an educational mutation log notice is returned to the agent in the `make_artifact` response. If an artifact component tree omits an explicit component with `id: "root"` or defines multiple disconnected top-level components, static structure warnings are also returned in the tool response. An artifact is closed if and only if `closed.marker` exists in its instance directory. While an open blocking artifact exists (`blocking=true`), standard user text dispatch (`POST /agent/.../session/.../input`) must be rejected with HTTP 409 Conflict and composer input disabled in the UI. Inquiry and artifact tools are atomic (`make_artifact`, `make_questionnaire`, `make_form`, `make_plan`). The harness supports explicit agent waiting via `wait_for_click` and injects `<SYNTHETIC MESSAGE INDICATOR>` when clicks arrive after assistant messages. In the Changes diff viewer, artifacts are presented with toggles between diff and read-only rendered views, and closed artifacts in rendered mode are strictly non-editable.
- **Justification**: [REQ-033](./requirements.md#req-033-mature-a2ui-subset-artifact-model-opinionated-persistence-and-atomic-generation), [0034-mature-a2ui-artifacts-model.md](../decisions/0034-mature-a2ui-artifacts-model.md), [0037-validate-a2ui-surface-render-on-make-artifact.md](../decisions/0037-validate-a2ui-surface-render-on-make-artifact.md), [0038-a2ui-root-component-and-incomplete-structure-warning.md](../decisions/0038-a2ui-root-component-and-incomplete-structure-warning.md), [0039-loose-artifact-normalization-and-mutation-log.md](../decisions/0039-loose-artifact-normalization-and-mutation-log.md), [0053-artifact-event-snapshots-and-static-context.md](../decisions/0053-artifact-event-snapshots-and-static-context.md), [artifacts.md](./artifacts.md).
- **Enforcement**: `seamus.harness.artifacts.ArtifactResolver`, `seamus.harness.artifacts.ArtifactBuilder`, `seamus.harness.artifacts.normalize_a2ui_components`, `seamus.harness.artifacts.auto_declare_manifest_buttons`, `seamus.harness.artifacts.validate_a2ui_surface`, `seamus.harness.artifacts.check_a2ui_surface_warnings`, `GitWorkspaceManager`, `SeamusOpenSandboxBackend`, `SessionAgentRunner.handle_make_artifact()`, `SessionAgentRunner.handle_wait_for_click()`, `SessionAgentRunner.dispatch_user_input()`, `SessionAgentRunner.dispatch_artifact_click()`, `ChatArea.tsx`, `ChangesViewer.tsx`, and unit tests in `tests/test_artifacts.py`.

### INV-041: Operational Mode Mount Policy, Non-Blocking Tabbed Plans, and Recursion Limit
- **Statement**: In `plan` mode phase `discuss`, the workspace mount `/workspace` (`data/`) is mounted read-write (`workspace_readonly=False`) so the agent has flexibility to record notes, research, and specifications anywhere in the workspace without being restricted to `/workspace/notes`. In `make` phase, `/workspace` is mounted read-only (`workspace_readonly=True`) for plan authoring. In `execute` phase, the workspace is mounted read-write (`workspace_readonly=False`) with notes mounted read-only. Plan artifacts (`artifacts/plans/<uuid>/`) have `exposition=tabbed`, `blocking=false`, and `commentable=true` (exactly one session-local active plan across all three phases), persisting `manifest.json`, `body.json`, canonical `plan.md` for direct sandbox execution handoff, rendered as dedicated tabs to the right of Changes in the Web UI with inline commenting and a "Proceed" action. Mode badges in the UI navigation tree must be left-aligned (`<icon><label><ID or name>`). LangGraph agent execution must use an elevated recursion limit (defaulting to 250, overridable via `SEAMUS_RECURSION_LIMIT`) to prevent premature `GraphRecursionError` on extended multi-step reasoning.
- **Justification**: [REQ-034](./requirements.md#req-034-operational-modes-multi-phase-plan-lifecycle-tabbed-plan-artifacts-and-recursion-limit), [0030-operational-modes-and-plan-mode.md](../decisions/0030-operational-modes-and-plan-mode.md), [0033-decouple-plans-and-submissions-from-a2ui.md](../decisions/0033-decouple-plans-and-submissions-from-a2ui.md), [0034-mature-a2ui-artifacts-model.md](../decisions/0034-mature-a2ui-artifacts-model.md), [artifacts.md](./artifacts.md).
- **Enforcement**: `seamus.harness.sandbox.SeamusOpenSandboxBackend.build_session_volumes()`, `seamus.harness.artifacts.PlanBuilder`, `seamus.harness.runner.DEFAULT_RECURSION_LIMIT`, `Sidebar.tsx`, and tests in `tests/test_modes_and_plan.py` and `tests/test_sandbox.py`.

### INV-042: In-Memory Secret Evaluation, Per-Inference Version Watching, and Session Config Explosion
- **Statement**: Symbolic secret expressions (`${secret('/path')}` or `${secret(path='/path', field='value')}`) are evaluated strictly in memory against OpenBao; resolved secret values are never persisted to disk or Git. User-supplied configurations (`AgentConfig`, `InferenceConfig`, `ConfigTemplate`) must not contain a `version` parameter in `secret(...)` expressions (`allow_version=False`). Prior to each inference run and model call (`refresh_secrets` / `refresh_secrets_sync`), `SessionAgentRunner` checks OpenBao for the current version of every referenced secret and automatically reloads the secret and updates the active LLM instance in-place whenever `current_version > loaded_version`. Upon workspace persistence, checkpoint persistence, or session config updates (`write_session_config_file`, `commit_session_config`, `commit_checkpoint_changes`, and `GitCheckpointSaver._save_checkpoint_to_disk`), on-disk `agent/config/config.json` is written and committed with every secret reference exploded to `${secret(path='/...', field='...', version=N)}` (explicitly listing `path=`, `field=`, and `version=`), while live in-memory `session.config` remains unversioned (and any persisted `version=` is stripped when hydrating from Gitea into in-memory entities while retaining `session.secret_versions`).
- **Justification**: [REQ-035](./requirements.md#req-035-openbao-secrets-vault-integration-per-inference-version-watching-and-checkpoint-explosion), [0041-openbao-secrets-vault-integration.md](../decisions/0041-openbao-secrets-vault-integration.md).
- **Enforcement**: `seamus.vault.parser.parse_secret_reference`, `seamus.vault.interpolator`, `seamus.config.models.InferenceConfig._validate_secrets`, `seamus.config.models.AgentConfig._validate_secrets`, `seamus.harness.runner.SessionAgentRunner.refresh_secrets_sync`, `seamus.persistence.checkpointer.GitCheckpointSaver._save_checkpoint_to_disk`, `seamus.persistence.workspace.GitWorkspaceManager.write_session_config_file`, `seamus.persistence.workspace.GitWorkspaceManager.commit_session_config`, `seamus.persistence.workspace.GitWorkspaceManager.commit_checkpoint_changes`, and unit tests in `tests/vault/` and `tests/test_vault_routes.py`.

### INV-043: External Git Repository Sandbox Isolation, Dual-Index Persistence, and Credential Safety
- **Statement**: Configured external Git repositories (`ExternalRepositoryConfig`) are mounted into OpenSandbox at `/projects/{mount_name}` (with mount names derived from the URL path, resolving collisions by suffixing `_0`, `_1`, ... to all colliding names). The agent's operational workspace remains at `/workspace`. Inside `/projects/{mount_name}`, the agent retains standard, full Git capabilities (`git status`, `git diff`, `git add`, `git commit`, `git branch`). Seamus automatic filesystem snapshots must never pollute or advance the semantic project Git branch or modify the agent's index (`.git/index`), `HEAD`, or working tree. Snapshotting uses an out-of-tree alternate index (`.seamus_indexes/{attachment_id}.idx`) to record working tree state (respecting `.gitignore`) and captures the agent's staged index as `staged_tree`. Snapshots are committed with independent ancestry and pushed to dedicated Gitea internal repositories (`project-{project_id}`) under `refs/seamus/checkpoints/{session_id}/{checkpoint_id}`. Remote Git credentials referencing OpenBao secrets (`${secret(...)}`) are resolved strictly in memory on the host and never written to disk, committed to Git, or exposed inside container environment variables.
- **Justification**: [REQ-036](./requirements.md#req-036-mount-external-git-repositories-into-agent-sandboxes-with-dual-index-persistence), [0042-mount-external-git-repositories.md](../decisions/0042-mount-external-git-repositories.md).
- **Enforcement**: `seamus.config.models.ExternalRepositoryConfig`, `seamus.persistence.external_repo.ExternalRepositoryManager`, `seamus.harness.sandbox.SeamusOpenSandboxBackend.build_repository_volumes()`, `tests/test_external_repos.py`.

### INV-044: Multi-Repository Checkpoint Ordering, Atomic Manifest Commit, and Exact Historical Restoration
- **Statement**: During agent checkpointing, all mounted external repositories must be snapshotted and pushed to durable Gitea storage before the agent repository checkpoint is committed. Checkpoint metadata (`MountedRepositoryCheckpointRecord` containing `attachment_id`, `project_id`, `mount_name`, `url`, `branch`, `semantic_head`, `semantic_branch`, `staged_tree`, `snapshot_tree`, `checkpoint_sha`, `gitea_repo_name`, and `gitea_repo_url`) is written to `agent/state/external_checkpoints.json` and committed directly to the agent repository's session branch. When branching a session (`branch_session`) or recovering from a crash, the target agent commit's manifest is used to reconstruct each working copy to its exact historical state: checking out `semantic_head` on `semantic_branch`, restoring untracked/modified files from `snapshot_tree` via `git archive` without touching the index, and restoring the agent's staged index via `git read-tree staged_tree`.
- **Justification**: [REQ-036](./requirements.md#req-036-mount-external-git-repositories-into-agent-sandboxes-with-dual-index-persistence), [0042-mount-external-git-repositories.md](../decisions/0042-mount-external-git-repositories.md).
- **Enforcement**: `seamus.persistence.checkpointer.GitCheckpointSaver._checkpoint_external_repositories`, `seamus.persistence.workspace.GitWorkspaceManager.save_thread_external_checkpoints`, `seamus.harness.store.HarnessStore.branch_session`, `tests/test_external_repos.py`.

### INV-045: Ephemeral Working-Tree Semantics Across Repository Unmount/Remount
- **Statement**: If an external repository is unmounted from an active session (by removing it from `session.config.repositories` and reloading configuration) and subsequently remounted, any uncommitted working-tree modifications and untracked files are discarded. The remounted working copy starts clean from the project repository's configured branch (`repo_config.branch`, e.g. `master` or `main`).
- **Justification**: [REQ-036](./requirements.md#req-036-mount-external-git-repositories-into-agent-sandboxes-with-dual-index-persistence), [0042-mount-external-git-repositories.md](../decisions/0042-mount-external-git-repositories.md).
- **Enforcement**: `seamus.harness.runner.SessionAgentRunner.reload_config`, `seamus.persistence.external_repo.ExternalRepositoryManager.unmount_working_copy`, `tests/test_external_repos.py`.

### INV-046: Real-Time Sandbox Terminal Streaming and Working Directory Continuity
- **Statement**: Terminal command execution dispatched via `POST /agent/{agent_id}/session/{session_id}/terminal/stream` must stream standard output and standard error lines in real-time as Server-Sent Events (`text/event-stream`) without intermediate line or execution buffering. The runner must deliver chunked output lines as they arrive from OpenSandbox `sandbox.commands.run()`, track working directory transitions across `cd` commands (`__SEAMUS_CWD__=$(pwd)` sentinel), and yield a terminal `exit` event containing the exact exit code and updated working directory.
- **Justification**: [REQ-037](./requirements.md#req-037-real-time-interactive-web-terminal--shell-emulator-for-agent-sandbox), [0044-interactive-web-terminal.md](../decisions/0044-interactive-web-terminal.md).
- **Enforcement**: `seamus.harness.runner.SessionAgentRunner.stream_terminal_command`, `seamus.server.routes.sessions.stream_terminal_command`, `ui/src/components/TerminalView.tsx`, and tests in `tests/test_terminal.py`.


### INV-048: Ollama Healthcheck and Active Model Execution Management
- **Statement**: When an agent configuration targets Ollama (`InferenceFormat.OLLAMA` or base URL port `11434`), API keys are optional. Before instantiating or updating the inference client, the runner must execute an HTTP healthcheck against the Ollama daemon (probing candidate endpoints: configured `base_url`, `http://ollama:11434`, and `http://host.docker.internal:11434` when localhost is specified), actively verify/load the specified model into memory (`POST /api/generate` with `{"model": model_name}`), and automatically pull missing models (`POST /api/pull` with `stream: False`). If the daemon is unreachable on all candidate endpoints or the model cannot be loaded, execution must immediately fail with a descriptive `RuntimeError`.
- **Justification**: [REQ-038](./requirements.md#req-038-ollama-local-model-provider-support--active-model-execution-management), [0045-ollama-local-model-provider.md](../decisions/0045-ollama-local-model-provider.md).
- **Enforcement**: `seamus.harness.runner._ensure_ollama_model`, `seamus.config.models.InferenceConfig.is_complete`, `seamus.config.models.AgentConfig.validate_complete`, `docker-compose.yml`, `tests/test_config.py`, `tests/test_runner.py`.

### INV-049: Non-Agentic Daemon Execution, Geometric Stepback, and Parallel Slug Priority
- **Statement**: Daemons must execute as plain, one-shot prompt prefills without tools, multi-turn message history, or agentic loop constructs. Exchange counting strictly counts completed full user/assistant interactions (spanning user input start to assistant text end or blocking artifact moment, rounding down to exclude in-progress turns), triggering daemon execution if and only if exchange counts match the doubling stepback sequence $2^k - 1$ ($1, 3, 7, 15, \dots$). Slugs on `Thread` and `Session` are maintained in parallel (`custom_name` and `daemon_name`), where effective `name` always prioritizes `custom_name` over `daemon_name`, and clearing `custom_name` automatically falls back to `daemon_name`. LLM output parsing must preemptively unwrap markdown, quotes, and prefixes before slug validation.
- **Justification**: [REQ-039](./requirements.md#req-039-non-agentic-daemons--geometric-stepback-threadsession-naming), [0046-daemons-naming.md](../decisions/0046-daemons-naming.md).
- **Enforcement**: `seamus.harness.daemons.naming.is_stepback_trigger`, `seamus.harness.daemons.parser.parse_loose_slug`, `seamus.domain.entities.Thread.name`, `seamus.domain.entities.Session.name`, `seamus.harness.runner._run_loop`, `tests/test_daemons.py`.

### INV-050: Deterministic Agent Slug Generation and Parallel Fallback
- **Statement**: Every agent must have a non-empty `generated_name` generated via `coolname`. If `custom_name` is provided, `agent.name` evaluates to `custom_name`; otherwise, `agent.name` evaluates to `generated_name`. When `custom_name` is cleared (`name=None`), `agent.name` automatically reverts to `generated_name`. Both `custom_name` and `generated_name` must conform to `SLUG_PATTERN`, and the effective slug must be unique among registered agents.
- **Justification**: [REQ-040](./requirements.md#req-040-deterministic-agent-slug-generation-via-coolname), [0046-daemons-naming.md](../decisions/0046-daemons-naming.md).
- **Enforcement**: `seamus.domain.entities.Agent.name`, `seamus.harness.store.HarnessStore.create_agent`, `seamus.harness.store.HarnessStore.update_agent`, `tests/test_daemons.py`.

### INV-051: Configuration Model and UI Symmetry Across Scopes
- **Statement**: Configuration schemas and UI editing interfaces must share an identical shape across all three configuration scopes (`ConfigTemplate`, `AgentConfig`, and `SessionConfig`). `ConfigTemplate` is permitted to be partially complete (e.g. omitting API keys, base URLs, or complete model validation), but must support and expose identical fields (`rules_patterns`, `repositories`, `inference`, `mode`, `system_prompt`, `todo_implementation`, `skills_implementation`, `thread_message_overlap`, `sandbox_image`, `daemons`). Deriving an agent from the template via `copy_with_overrides()` must preserve all explicitly set template configurations unless overridden.
- **Justification**: [REQ-041](./requirements.md#req-041-configuration-model-and-ui-symmetry-across-scopes), [0047-discovered-context-and-project-skills.md](../decisions/0047-discovered-context-and-project-skills.md).
- **Enforcement**: `seamus.config.models.AgentConfig`, `seamus.config.template.ConfigTemplateStore.derive_agent_config`, `ui/src/components/ConfigModal.tsx`, `ui/src/api/types.ts`, and unit tests in `tests/test_config.py`.

### INV-052: Dynamic Workspace and Project Context Discovery and LM-XML Injection
- **Statement**: System prompts dynamically assembled per inference turn must evaluate `rules_patterns` (defaulting to `["AGENTS.md", ".seamus/rules/**"]`) across `/workspace` and mounted external projects (`/projects/{mount_name}` in the order listed in `session.config.repositories`). Within each root, matching files must be regular files excluding `.git/` directories, with wildcards sorted alphabetically, deduplicated by sandbox path preserving earliest match, and safely skipping binary/unreadable files and files exceeding 1 MB. Discovered files must be injected into `SystemPromptDocument.discovered_context` as `{path: ..., content: ...}` objects serialized to LM-XML `<discovered_context>`; if empty or none, the section must be completely omitted.
- **Justification**: [REQ-042](./requirements.md#req-042-dynamic-workspace-and-project-context-discovery-and-lm-xml-prompt-injection), [0047-discovered-context-and-project-skills.md](../decisions/0047-discovered-context-and-project-skills.md).
- **Enforcement**: `seamus.harness.prompt.discover_context_files`, `seamus.harness.prompt.build_effective_system_prompt`, `SessionAgentRunner.build_effective_system_prompt`, `SessionAgentRunner._provide_prompt_for_request`, `extract_session_skills`, and unit tests in `tests/test_prompt.py` and `tests/test_inspector.py`.

### INV-053: Pure Tag Structure for LM-XML Skills Serialization
- **Statement**: Skills prompt documents must serialize into LM-XML using pure child element tag trees (`<skills><available_skills><list><item index="N"><name>...</name><description>...</description></item></list></available_skills><active_skills><list><item index="N"><name>...</name><instructions>...</instructions></item></list></active_skills><guidelines>...</guidelines></skills>`) with zero XML attributes. When no skills are loaded, `<active_skills>` must be omitted via `exclude_none=True`. When no skills exist across sources, the `<skills>` section must be completely omitted.
- **Justification**: [REQ-043](./requirements.md#req-043-native-lm-xml-skills-system-with-explicit-loadunload-tools), [0048-native-lmxml-skills-system.md](../decisions/0048-native-lmxml-skills-system.md).
- **Enforcement**: `seamus.harness.prompt.SkillsPromptDocument`, `seamus.harness.prompt.build_effective_system_prompt`, `tests/test_skills.py::test_lmxml_skills_prompt_serialization_no_attributes`.

### INV-054: Thread-Scoped Active Skills Lifecycle and Dynamic Tool Gating
- **Statement**: Active skill state must be stored on `Thread.active_skills`, persisting across checkpoints and persistence commits within a conversation thread, and resetting to empty upon operational mode switches or fresh thread spawning. When `skills_implementation == SkillsImplementation.SEAMUS`, DeepAgents `SkillsMiddleware` is bypassed (`skills=None`), `load_skill` and `unload_skill` are exposed via `SeamusSkillsMiddleware`, and tools declared in unshadowed skills' `allowed_tools` are gated from model requests until their owning skill is loaded into the active thread.
- **Justification**: [REQ-043](./requirements.md#req-043-native-lm-xml-skills-system-with-explicit-loadunload-tools), [0048-native-lmxml-skills-system.md](../decisions/0048-native-lmxml-skills-system.md).
- **Enforcement**: `seamus.domain.entities.Thread.active_skills`, `seamus.harness.skills.SeamusSkillsMiddleware`, `seamus.harness.runner.SessionAgentRunner.get_active_tools_for_request`, `tests/test_skills.py`.

### INV-055: Web Search Capability Guard and Dynamic Tool Suppression
- **Statement**: When `session.config.web_search == WebSearchImplementation.NONE`, web search tools (`web_search`, `fetch_web_page`) must not be bound to the session DeepAgent, must be filtered out of active tools returned by `get_active_tools_for_request()`, and must be excluded from `AgentInspectReport.tools`. When `web_search == WebSearchImplementation.DUCKDUCKGO`, both tools must be registered and annotated with backend `"web"` in the Inspector.
- **Justification**: [REQ-044](./requirements.md#req-044-web-search-capability--enum-configuration-guard), [0050-web-search-tool.md](../decisions/0050-web-search-tool.md).
- **Enforcement**: `src/seamus/harness/web_search.py`, `SessionAgentRunner.create_agent`, `SessionAgentRunner.get_active_tools_for_request`, `get_agent_inspect_report`, and unit tests in `tests/test_web_search.py`, `tests/test_runner.py`, and `tests/test_inspector.py`.

### INV-056: Chat Bubble Timestamps and Autonomous Sequence Indexing
- **Statement**: All conversational message bubbles rendered in the Web UI must render timestamps with seconds precision (`HH:MM:SS`) in the bubble footer or message header. Whenever a contiguous sequence of messages by the same sender role exceeds `BUBBLE_SEQUENCE_THRESHOLD` (default 5, configurable), each message in that sequence must render a 1-based index badge (`#1`, `#2`, ..., `#N`) at its top-left corner (or in the header if text content is absent). Thread transitions and synthetic event notifications must break sequence continuity.
- **Justification**: [REQ-045](./requirements.md#req-045-chat-bubble-timestamps-and-autonomous-sequence-indexing), [0051-chat-bubble-timestamps-and-sequence-indexing.md](../decisions/0051-chat-bubble-timestamps-and-sequence-indexing.md).
- **Enforcement**: `ui/src/utils/sequence.ts`, `ui/src/components/ChatArea.tsx`, `ui/src/components/MessageItem.tsx`, and automated tests in `ui/tests/sequence.test.mjs`.

### INV-057: A2UI v1.0 UAX #31 Component Identifier and Envelope Invariant
- **Statement**: Outbound A2UI event envelopes emitted to the UI must declare version `"1.0"`. All component IDs in declarative surfaces (`body.json`) must strictly conform to Unicode Standard Annex #31 (UAX #31) identifier syntax (`c_id.isidentifier()`). During normalization (`normalize_a2ui_components`), hyphens and invalid identifier characters must be converted to underscores, duplicate identifiers disambiguated with numeric suffixes, and all component pointer references (`child`, `children`, `trigger`, `content`, `tabs`, `action.event.context`) rewritten to their normalized target IDs. Surface pre-render validation (`validate_a2ui_surface`) must fail if any non-identifier component ID remains. In addition, Text component variants must belong to `{"caption", "body"}`; heading variants (`h1`-`h5`) must be rewritten to markdown headings (`#`, `##`, etc.) under `variant: "body"`. Built-in builders and runtime button dispatch must support snake_case IDs (`submit_btn`, `review_btn`, `proceed_btn`).
- **Justification**: [REQ-046](./requirements.md#req-046-adaptive-ui-a2ui-v10-specification-upgrade--strict-uax-31-identifier-validation), [0052-backlog-low-hanging-fruits.md](../decisions/0052-backlog-low-hanging-fruits.md).
- **Enforcement**: `src/seamus/harness/artifacts.py`, `ui/src/components/A2UIArtifactRenderer.tsx`, and unit tests in `tests/test_artifacts.py`.

### INV-058: Model Reasoning Effort Parameter Forwarding Invariant
- **Statement**: When `InferenceConfig.reasoning_effort == ReasoningEffort.DEFAULT`, the `reasoning_effort` argument must be omitted when instantiating `ReasoningChatOpenAI` and excluded from model request payloads, allowing the provider to use its native default. When `reasoning_effort` is set to any non-default tier (`none`, `minimal`, `low`, `medium`, `high`, `xhigh`), the corresponding string value must be explicitly passed into `ReasoningChatOpenAI(reasoning_effort=...)`.
- **Justification**: [REQ-047](./requirements.md#req-047-configurable-model-reasoning-effort-tiers), [0052-backlog-low-hanging-fruits.md](../decisions/0052-backlog-low-hanging-fruits.md).
- **Enforcement**: `src/seamus/config/models.py`, `src/seamus/harness/runner.py`, `tests/test_runner.py`.

### INV-059: Dynamic Tool Labeling JSON Resource Alignment
- **Statement**: Semantic tool labels, categories, and colors must be loaded from `src/seamus/harness/resources/tool_labeling.json` via `get_tool_labeling()`. The Inspector service (`get_agent_inspect_report`) must assign each tool its configured `list[ToolLabelInfo]`. If a tool is not explicitly mapped in `tool_labeling.json`, it must default to empty labels rather than raising an error. The Web UI Inspector must render these semantic badges and allow filtering tools by label title.
- **Justification**: [REQ-048](./requirements.md#req-048-semantic-tool-categorization-color-labeling--filtering-in-agent-inspector), [0052-backlog-low-hanging-fruits.md](../decisions/0052-backlog-low-hanging-fruits.md).
- **Enforcement**: `src/seamus/harness/resources/tool_labeling.json`, `src/seamus/harness/inspector.py`, `ui/src/components/AgentInspector.tsx`, and tests in `tests/test_inspector.py`.

### INV-060: Explicit Thread Skill Retention and Token Leakage Guard
- **Statement**: Conversation thread creation (`Session.create_thread`, `HarnessStore.create_thread`, `runner.transition_to_phase`) must accept `retained_skills: list[str] | None`. When `retained_skills` is provided, the newly spawned thread's `active_skills` must be populated with `retained_skills`; when omitted or `None`, `active_skills` must initialize to empty `[]`. Unretained skills from previous threads must be dropped to prevent unbounded context token accumulation across phase rollovers.
- **Justification**: [REQ-049](./requirements.md#req-049-cross-phase-retained-skills-continuity-across-thread-rollovers), [0052-backlog-low-hanging-fruits.md](../decisions/0052-backlog-low-hanging-fruits.md).
- **Enforcement**: `src/seamus/domain/entities.py`, `src/seamus/harness/store.py`, `src/seamus/harness/runner.py`, `tests/test_skills.py`.


## Cross-References
- [backlog.md](./backlog.md)
- [requirements.md](./requirements.md)
- [threads_modes_personas.md](./threads_modes_personas.md)
- [artifacts.md](./artifacts.md)
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
- [0014-SUPERSEDED-ui-layout-proportions-breadcrumbs.md](../decisions/0014-SUPERSEDED-ui-layout-proportions-breadcrumbs.md)
- [0015-session-changes-diff-tab.md](../decisions/0015-session-changes-diff-tab.md)
- [0016-sync-pr-data-scope.md](../decisions/0016-sync-pr-data-scope.md)
- [0017-dedicated-test-gitea.md](../decisions/0017-dedicated-test-gitea.md)
- [0018-dynamic-system-prompt-architecture.md](../decisions/0018-dynamic-system-prompt-architecture.md)
- [0019-threads-modes-personas-architecture.md](../decisions/0019-threads-modes-personas-architecture.md)
- [0022-branching-out-and-session-lifecycle.md](../decisions/0022-branching-out-and-session-lifecycle.md)
- [0024-anthropic-skills-and-system-settings.md](../decisions/0024-anthropic-skills-and-system-settings.md)
- [0025-todo-list-middleware.md](../decisions/0025-todo-list-middleware.md)
- [0026-in-sandbox-skill-mount-paths.md](../decisions/0026-in-sandbox-skill-mount-paths.md)
- [0027-skills-config-project-rules-and-inspector.md](../decisions/0027-skills-config-project-rules-and-inspector.md)
- [0028-ui-ux-ergonomics-and-url-state.md](../decisions/0028-ui-ux-ergonomics-and-url-state.md)
- [0030-operational-modes-and-plan-mode.md](../decisions/0030-operational-modes-and-plan-mode.md)
- [0031-SUPERSEDED-migrate-a2ui-to-adaptive-cards.md](../decisions/0031-SUPERSEDED-migrate-a2ui-to-adaptive-cards.md)
- [0032-operational-mode-in-agent-config-and-defaults.md](../decisions/0032-operational-mode-in-agent-config-and-defaults.md)
- [0034-mature-a2ui-artifacts-model.md](../decisions/0034-mature-a2ui-artifacts-model.md)
- [0035-harness-low-hanging-fruits.md](../decisions/0035-harness-low-hanging-fruits.md)
- [0036-mount-bundled-skills-via-shared-volume.md](../decisions/0036-mount-bundled-skills-via-shared-volume.md)
- [0037-validate-a2ui-surface-render-on-make-artifact.md](../decisions/0037-validate-a2ui-surface-render-on-make-artifact.md)
- [0038-a2ui-root-component-and-incomplete-structure-warning.md](../decisions/0038-a2ui-root-component-and-incomplete-structure-warning.md)
- [0039-loose-artifact-normalization-and-mutation-log.md](../decisions/0039-loose-artifact-normalization-and-mutation-log.md)
- [0041-openbao-secrets-vault-integration.md](../decisions/0041-openbao-secrets-vault-integration.md)
- [0042-mount-external-git-repositories.md](../decisions/0042-mount-external-git-repositories.md)
- [0045-ollama-local-model-provider.md](../decisions/0045-ollama-local-model-provider.md)
- [0046-daemons-naming.md](../decisions/0046-daemons-naming.md)
- [0047-discovered-context-and-project-skills.md](../decisions/0047-discovered-context-and-project-skills.md)
- [0048-native-lmxml-skills-system.md](../decisions/0048-native-lmxml-skills-system.md)
- [0049-native-lmxml-todo-planning.md](../decisions/0049-native-lmxml-todo-planning.md)
- [0050-web-search-tool.md](../decisions/0050-web-search-tool.md)
- [0051-chat-bubble-timestamps-and-sequence-indexing.md](../decisions/0051-chat-bubble-timestamps-and-sequence-indexing.md)
- [0052-backlog-low-hanging-fruits.md](../decisions/0052-backlog-low-hanging-fruits.md)
- [persistence.md](./persistence.md)
