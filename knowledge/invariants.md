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

## Cross-References
- [backlog.md](./backlog.md)
- [requirements.md](./requirements.md)
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
