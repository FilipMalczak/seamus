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
- **Statement**: External system icons in the navigation tree left panel must be strictly conditional on integration availability. The Logfire navigation icon must only render when Logfire is actively configured to send telemetry, accurately reflecting `LOGFIRE_SEND_TO_LOGFIRE` overrides and token presence. Furthermore, system `/health` heartbeat checks must never produce request telemetry spans.
- **Justification**: [REQ-013](./requirements.md#req-013-external-system-navigation-links--telemetry-visibility-guard), [0006-external-system-links.md](../decisions/0006-external-system-links.md).
- **Enforcement**: `seamus.telemetry.is_logfire_enabled()` evaluates send status and token presence; `GET /api/v-alpha/system/info` exposes `SystemInfoResponse`; `Sidebar.tsx` conditionally mounts the icon; `instrument_fastapi` filters `/health` with `excluded_urls`.

## Cross-References
- [requirements.md](./requirements.md)
- [0001-project-initialization.md](../decisions/0001-project-initialization.md)
- [0002-harness-server-mvp.md](../decisions/0002-harness-server-mvp.md)
- [0003-react-web-ui.md](../decisions/0003-react-web-ui.md)
- [0004-inline-tree-editing-session-status.md](../decisions/0004-inline-tree-editing-session-status.md)
- [0005-logfire-integration.md](../decisions/0005-logfire-integration.md)
- [0006-external-system-links.md](../decisions/0006-external-system-links.md)
