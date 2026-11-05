# Requirements

Requirements, rationale, provenance, and stable IDs.

## Requirements Catalog

### REQ-001: Modern Python 3.12 Runtime & UV Package Management
- **Description**: The project must use Python 3.12 and `uv` for dependency and virtual environment management.
- **Rationale**: Ensures deterministic lockfiles, fast resolution, consistent environments across development, and modern language features.
- **Provenance**: [AGENTS.md](../AGENTS.md), [0001-project-initialization.md](../decisions/0001-project-initialization.md).
- **Linked Invariants**: [INV-001](./invariants.md#inv-001-uv-and-python-312-consistency), [INV-002](./invariants.md#inv-002-zero-tooling-check-failures).

### REQ-002: Rigorous Code Quality & Static Verification
- **Description**: All codebase modifications must be verified with `ruff` (linting and formatting), `mypy` (strict static typing), and `pytest`.
- **Rationale**: Prevents regression, guarantees type safety on public and internal boundaries, and enforces high code cleanliness.
- **Provenance**: [AGENTS.md](../AGENTS.md), [0001-project-initialization.md](../decisions/0001-project-initialization.md).
- **Linked Invariants**: [INV-002](./invariants.md#inv-002-zero-tooling-check-failures).

### REQ-003: Traceable Architectural & Durable Knowledge Documentation
- **Description**: Architectural decisions must be documented in `./decisions/` and durable implementation knowledge in `./knowledge/`, kept continuously synchronized with implementation changes.
- **Rationale**: Preserves long-term project memory, prevents architectural drift, and supports autonomous agent collaboration.
- **Provenance**: [AGENTS.md](../AGENTS.md), [0001-project-initialization.md](../decisions/0001-project-initialization.md).
- **Linked Invariants**: [INV-003](./invariants.md#inv-003-knowledge-synchronization).

### REQ-004: Config Template Singleton & Derivation
- **Description**: The harness must provide a singleton service-wide config template that may be partially complete. Creating an agent derives a copied config merged with agent overrides. Creating a session derives an isolated copy of the agent's config. Complete configuration is required to initialize a session's agent.
- **Rationale**: Decouples global defaults from individual agent and conversation instances while preventing configuration mutations across active sessions.
- **Provenance**: [0002-harness-server-mvp.md](../decisions/0002-harness-server-mvp.md).
- **Linked Invariants**: [INV-004](./invariants.md#inv-004-config-completeness-invariant).

### REQ-005: Hierarchical REST API with Dual Identifier Resolution
- **Description**: The server must expose a structured REST API under `/api/v-alpha/` for agents, sessions, and threads. Entities must support identification by UUID or slug name in all path parameters.
- **Rationale**: Enables human-readable URLs for clients while retaining globally unique machine-readable keys.
- **Provenance**: [0002-harness-server-mvp.md](../decisions/0002-harness-server-mvp.md).
- **Linked Invariants**: [INV-006](./invariants.md#inv-006-slug-format-and-scope-uniqueness).

### REQ-006: Thread Redirection, Event Streaming & Status Tracking
- **Description**: `GET .../thread` without a thread ID must issue an HTTP 307 redirect to the current open thread. `GET .../thread/<T>` must stream past AG-UI events (including user input messages and agent execution events) from history followed by live events over SSE. Execution status must be retrievable via `.../thread/<T>/status`.
- **Rationale**: Allows clients to easily bind to the active conversation context, recover full history on reload or thread switching, and display real-time execution state.
- **Provenance**: [0002-harness-server-mvp.md](../decisions/0002-harness-server-mvp.md), [0003-react-web-ui.md](../decisions/0003-react-web-ui.md).
- **Linked Invariants**: [INV-005](./invariants.md#inv-005-single-open-thread-invariant), [INV-012](./invariants.md#inv-012-user-message-event-recording--replay-invariant).

### REQ-007: Safe Non-Destructive API Surface
- **Description**: The API must not support HTTP DELETE methods on any resource. Resource updates must use HTTP POST with the full replacement object to support explicit clearing of values.
- **Rationale**: Eliminates catastrophic accidental data deletion at the API boundary and disambiguates partial updates from field deletions.
- **Provenance**: [0002-harness-server-mvp.md](../decisions/0002-harness-server-mvp.md).
- **Linked Invariants**: [INV-007](./invariants.md#inv-007-no-resource-deletion-invariant).

### REQ-008: Web UI with Navigation Tree, Real-Time Streaming & JSON Config Editor
- **Description**: The harness must provide a web user interface featuring:
  1. A hierarchical tree sidebar organizing Agents, Sessions, and Threads with operational status badges.
  2. A conversational workspace connecting to the SSE stream to display past messages, live streaming tokens, and tool calls.
  3. An in-browser modal for editing raw JSON configuration templates with format validation.
- **Rationale**: Provides developers and users with immediate visual control, conversational interaction, and simple configuration editing without requiring backend API tools.
- **Provenance**: [0003-react-web-ui.md](../decisions/0003-react-web-ui.md).
- **Linked Invariants**: [INV-008](./invariants.md#inv-008-ui-client-side-busy-guard).

### REQ-009: Default Session and Open Thread Automatic Creation, Zero-Prompt UX & Auto-Focus
- **Description**: Creating an entity (Agent, Session, Thread) must never prompt for a name during creation. Creating an agent immediately instantiates a default session (`name = None`), which instantiates an initial open thread (`name = None`). Creating an entity auto-selects down to the active open thread and automatically focuses the message composer input field. Entity names can be renamed later via explicit edit actions; non-empty names are displayed in the tree and breadcrumbs, falling back to full UUIDs when unset or empty.
- **Rationale**: Minimizes "time-to-typing-message" by eliminating modal prompt friction during creation while retaining optional renaming and unambiguous UUID identity.
- **Provenance**: [0003-react-web-ui.md](../decisions/0003-react-web-ui.md).
- **Linked Invariants**: [INV-009](./invariants.md#inv-009-default-session-and-open-thread-creation), [INV-010](./invariants.md#inv-010-entity-display-name-fallback).

### REQ-010: Containerized Launch Automation, Safe Service Restart & Clean Reset
- **Description**: The repository must provide multi-container orchestration (`docker-compose.yml`) and an automated launch script (`run.sh`). Running `./run.sh` must ensure services are running and open the UI in the default browser. Running `./run.sh --restart` (`-r`) must rebuild application container images (`backend`, `frontend`) and recreate running application containers to apply latest code updates while strictly preserving infrastructure services (`postgres`, `gitea`) and persistent data volumes (avoiding data deletion). Running `./run.sh --clean` (`-c`) must tear down all containers, purge persistent volumes (`postgres-data`, `gitea-data`, `backend-workspaces`) and data storages, and restart all services cleanly.
- **Rationale**: Streamlines local execution and development iteration while ensuring service updates never inadvertently wipe stored data unless explicitly requested via `--clean`.
- **Provenance**: [0003-react-web-ui.md](../decisions/0003-react-web-ui.md), [0008-git-persistence.md](../decisions/0008-git-persistence.md).
- **Linked Invariants**: [INV-007](./invariants.md#inv-007-no-resource-deletion-invariant).

### REQ-011: Inline Tree Node Renaming and Session Node Status Visibility
- **Description**: The navigation tree must support inline name editing for agents, sessions, and threads without browser modal prompts. Initiating an edit must convert the label into an editable text field and change the edit button into a tick-box-only `<Check />` accept button. In addition, Session nodes must display a small status icon reflecting the operational state (`AWAITING_USER`, `AWAITING_LLM`, `EXECUTING_TOOL`, `ERROR`) of the session's active open thread.
- **Rationale**: Eliminates modal interruptions, provides seamless in-place editing, and surfaces session-level execution status directly in the navigation tree.
- **Provenance**: [0004-inline-tree-editing-session-status.md](../decisions/0004-inline-tree-editing-session-status.md).
- **Linked Invariants**: [INV-010](./invariants.md#inv-010-entity-display-name-fallback), [INV-013](./invariants.md#inv-013-inline-tree-editing-and-session-status-invariant).

### REQ-012: Logfire Tracing with Agent, Session, and Thread Hierarchical Spans
- **Description**: The harness must integrate Pydantic Logfire for observability. Agent execution runs must generate a three-level hierarchical trace (`agent` wraps `session`, which wraps `thread`), enclosing LangGraph agent execution, model invocations, and tool runs. Store entity creation/update operations and FastAPI REST endpoints must also emit structured spans with standardized attributes. Telemetry initialization must automatically load environment variables from `.env` and provide a comprehensive `.env.template`.
- **Rationale**: Provides clear visibility into deep multi-turn agent execution, latency bottlenecks, and error states while preserving Seamus domain terminology.
- **Provenance**: [0005-logfire-integration.md](../decisions/0005-logfire-integration.md).
- **Linked Invariants**: [INV-014](./invariants.md#inv-014-hierarchical-agent-session-thread-execution-spans).

### REQ-013: External System Navigation Links & Telemetry Visibility Guard
- **Description**: The Web UI navigation panel must provide external system shortcut links pinned to the bottom of the left sidebar. The Logfire dashboard icon must link to `https://logfire-eu.pydantic.dev/filip-malczak/${LOGFIRE_SERVICE_NAME=seamus}`. The Logfire icon must only be rendered when telemetry export is active, accounting for `LOGFIRE_SEND_TO_LOGFIRE` toggles and token presence. Furthermore, health check probes to `/health` must be excluded from FastAPI tracing.
- **Rationale**: Gives users direct access to companion observability systems without manual URL management while preventing visual clutter when telemetry is disabled and avoiding probe trace spam.
- **Provenance**: [0006-external-system-links.md](../decisions/0006-external-system-links.md).
- **Linked Invariants**: [INV-015](./invariants.md#inv-015-external-system-link-visibility--telemetry-guard).

### REQ-014: AG-UI Reasoning Exposure & Multi-Turn Trace Message Alignment
- **Description**: The harness must extract reasoning content (`reasoning`, `reasoning_content`, `reasoning_details`) from OpenAI-compatible and OpenRouter model responses so `ag_ui_langgraph` emits AG-UI 1.0 `REASONING_*` events over SSE, persists them for thread replay, and surfaces a collapsible thought process block in the Web UI. Furthermore, `LangGraph` chain spans in Logfire must receive full checkpoint history in their input state so multi-turn traces display the conversation without duplicate leading user messages.
- **Rationale**: Surfaces model chain-of-thought for inspection in both the live UI and telemetry while preventing misleading duplicate user messages on multi-turn `LangGraph` spans.
- **Provenance**: [0007-agui-reasoning-and-trace-messages.md](../decisions/0007-agui-reasoning-and-trace-messages.md).
- **Linked Invariants**: [INV-016](./invariants.md#inv-016-ag-ui-reasoning-stream--multi-turn-span-message-alignment).

### REQ-015: Gitea-Backed Versioned Agent Persistence & Workspace Isolation
- **Description**: The harness must integrate Gitea (backed by PostgreSQL) as the golden source of truth for agent, session, and workspace persistence without requiring direct SQL dependencies in the Seamus backend. Each agent maps to a Git repository (`agent-{agent_id}`) with a `main` branch storing agent configuration (`agent/config/config.json`) and empty data baseline. Each session branches to `session/{session_id}` storing session configuration and threads metadata in `agent/config/config.json`, and thread state (AG-UI event history, LangGraph checkpoints/writes/blobs, and human-readable messages) under `agent/state/threads/{thread_id}/`. The agent's `FilesystemBackend` must be strictly isolated to `<workspace>/data/`. Changes to `data/` and `agent/state/` must be committed on every LangGraph checkpoint (`checkpoint:` commits), thread event updates committed on turn completion (`state:` commits), and configuration directory changes committed on updates (`config:` commits). On server restart, `HarnessStore` must hydrate agents, sessions, and thread events directly by querying Gitea repositories and branches, and `GitCheckpointSaver` must restore checkpoints from disk so conversation memory and HITL state resume seamlessly.
- **Rationale**: Guarantees all agent modifications, conversation events, and execution graph states are Git-versioned, isolates agent tools from configuration and Git internals, and ensures persistent state without external SQL database requirements in the harness backend.
- **Provenance**: [0008-git-persistence.md](../decisions/0008-git-persistence.md).
- **Linked Invariants**: [INV-017](./invariants.md#inv-017-git-tracked-agent-workspace--config-boundary), [INV-018](./invariants.md#inv-018-atomic-checkpoint-data-persistence).

### REQ-016: UI Markdown Rendering
- **Description**: All conversation messages (both user and assistant) must be assumed to be Markdown and rendered in the browser using a unified Markdown rendering pipeline. The renderer must support GitHub Flavored Markdown (tables, task lists, strikethrough, autolinks), ensure external links open in a new tab safely (`target="_blank"` with `rel="noopener noreferrer"`), provide copy-to-clipboard functionality on fenced code blocks with language badges, protect chat bubble layouts from table overflows via horizontal scrolling, and adapt typography contrasts cleanly between user and assistant message bubble themes.
- **Rationale**: Agents and human developers exchange formatted text, code snippets, lists, and tables. Rendering messages as Markdown provides a clear, rich, developer-friendly interface while preventing code block and layout breakage.
- **Provenance**: [0009-ui-markdown-renderer.md](../decisions/0009-ui-markdown-renderer.md).
- **Linked Invariants**: [INV-019](./invariants.md#inv-019-client-side-markdown-rendering--content-safety).

### REQ-017: Containerized OpenSandbox Execution & Operational Directory Mount
- **Description**: Agent file operations and shell execution must run inside an isolated OpenSandbox container via `langchain-sandbox-opensandbox` (`SeamusOpenSandboxBackend`) connected to a locally hosted `opensandbox-server` running in its own Docker Compose container (with `/var/run/docker.sock` mounted). Authentication with `opensandbox-server` must use a runtime-autogenerated API key never exposed to users. Only the session's Git-tracked `<workspace>/data/` directory must be mounted into the sandbox container at `/workspace`, and the agent's system prompt must explicitly instruct the agent that `/workspace` is its persistent Git-tracked operational directory while all other sandbox paths are transient.
- **Rationale**: Isolates untrusted code and command execution from the backend service while preserving seamless Git-backed checkpoint persistence for files in `/workspace` and protecting `agent/config/`, `agent/state/`, and `.git/`.
- **Provenance**: [0010-opensandbox-filesystem-sandboxing.md](../decisions/0010-opensandbox-filesystem-sandboxing.md).
- **Linked Invariants**: [INV-017](./invariants.md#inv-017-git-tracked-agent-workspace--config-boundary), [INV-020](./invariants.md#inv-020-runtime-managed-opensandbox-authentication).

### REQ-018: DeepAgent Inspection Console & Branch State Provenance
- **Description**: The harness must provide an agent inspection endpoint (`/api/v-alpha/agent/{agent}/session/{session}/inspect`) and UI tab (`[Inspector]`) surfacing the agent state as of its latest inference run. The inspector report must decompose system prompts (composite, sandbox scaffolding, and custom additions), list registered tools with their input JSON argument schemas and execution backends, display model and inference parameters with credentials redacted, surface Gitea branch and commit SHA provenance, and list message trajectory turns and workspace files.
- **Rationale**: Developers require immediate visibility into how a DeepAgent is configured and acting on a specific Git branch to verify instructions and tool schemas without digging through raw Git JSON blobs.
- **Provenance**: [0011-agent-inspector.md](../decisions/0011-agent-inspector.md).
- **Linked Invariants**: [INV-021](./invariants.md#inv-021-agent-inspection-and-credential-redaction).

### REQ-019: Gitea Sync PRs and Thread Acceptance Lifecycle
- **Description**: The UI must not provide explicit manual controls to open or spawn threads. When a session starts, the harness must open an automated Sync PR in Gitea from `session/{session_id}` to `main`. The thread acceptance action button is hosted in the dedicated "Changes" view alongside the visual diff of the Sync PR. Accepting a thread closes the active thread, approves and merges the session's active Sync PR into `main`, spawns a new open thread on the same session branch, and opens a new Sync PR to `main`.
- **Rationale**: Replaces ad-hoc manual thread opening with a rigorous human-in-the-loop acceptance workflow that automatically merges validated thread outputs into the base repository branch while keeping subsequent work in clean isolated Sync PR cycles.
- **Provenance**: [0012-sync-prs-and-thread-accept.md](../decisions/0012-sync-prs-and-thread-accept.md), [0015-session-changes-diff-tab.md](../decisions/0015-session-changes-diff-tab.md).
- **Linked Invariants**: [INV-022](./invariants.md#inv-022-thread-acceptance-and-sync-pr-lifecycle), [INV-024](./invariants.md#inv-024-session-changes-diff-and-acceptance-placement).

### REQ-020: Tool Call Lifecycle Visibility & Accurate UI Stream Rendering
- **Description**: The Web UI must track and render the full lifecycle of agent tool calls across distinct states (`Pending`, `WIP`, `Done`, and `Failed`), displaying the actual tool name, parsed arguments, and execution result. Tool results transmitted in `TOOL_CALL_RESULT.content` and `MESSAGES_SNAPSHOT` must be accurately extracted and rendered without being lost or remaining stuck in the `Running` state.
- **Rationale**: Eliminates developer blind spots during tool execution by providing unambiguous visual progression and output inspection for sandbox operations.
- **Provenance**: [0013-tool-call-lifecycle-ui.md](../decisions/0013-tool-call-lifecycle-ui.md).
- **Linked Invariants**: [INV-023](./invariants.md#inv-023-tool-call-lifecycle-and-state-representation).

### REQ-021: Sync PR Diff Inspection and Changes Tab
- **Description**: The harness must provide an endpoint `GET /api/v-alpha/agent/{agent}/session/{session}/diff` returning the active Sync PR metadata and raw unified diff. The Web UI main panel must provide a "Changes" tab next to "Inspector" rendering the diff with `@pierre/diffs`, offering a unified/split toggle and hosting the relocated thread "Accept" button.
- **Rationale**: Empowers users to inspect cumulative workspace changes in the Sync PR prior to merging them into `main`.
- **Provenance**: [0015-session-changes-diff-tab.md](../decisions/0015-session-changes-diff-tab.md).
- **Linked Invariants**: [INV-022](./invariants.md#inv-022-thread-acceptance-and-sync-pr-lifecycle), [INV-024](./invariants.md#inv-024-session-changes-diff-and-acceptance-placement).

### REQ-022: Restrict Sync PRs and Thread Acceptance to data/ Deliverables
- **Description**: Reviewable Sync PR diffs must exclusively contain file modifications under `data/`, filtering out `agent/config/**` and `agent/state/**`. Thread acceptance merging must execute a data-scoped Git merge into `main` that preserves the base agent configuration and clean state on `main` without pollution or collision from session configuration or thread checkpoints, recording the PR merge in Gitea via `manually-merged`.
- **Rationale**: The repository's base branch (`main`) must solely represent verified, clean agent deliverables across sessions, preventing session configuration leaks and concurrent merge conflicts.
- **Provenance**: [0016-sync-pr-data-scope.md](../decisions/0016-sync-pr-data-scope.md).
- **Linked Invariants**: [INV-025](./invariants.md#inv-025-scope-sync-prs-and-thread-acceptance-merges-to-data-deliverables).

### REQ-023: Dynamic LM-XML Structured System Prompt Architecture
- **Description**: The harness must format all agent system prompts in deterministic, structured XML using `lmxml`, assembling identity, sandbox workspace boundaries (`/workspace` persistence vs. transient paths), coding discipline, tool usage rules, communication style, and user custom instructions. System prompt generation must evaluate dynamically per inference turn via `DynamicSystemPromptMiddleware` to incorporate live turn context without requiring graph re-compilation.
- **Rationale**: Structured XML prompting dramatically increases model adherence to operating boundaries, tool discipline, and minimal change policies across all model families, while per-inference evaluation enables runtime context adaptation.
- **Provenance**: [0018-dynamic-system-prompt-architecture.md](../decisions/0018-dynamic-system-prompt-architecture.md).
- **Linked Invariants**: [INV-027](./invariants.md#inv-027-lm-xml-dynamic-system-prompt-assembly).

### REQ-024: Agent Personas and Baseline Archetypes
- **Description**: The harness must support an extensible architecture for agent personas, with immediate near-term focus on the `Coder` persona to support self-hosting / dogfooding development, while supporting custom persona registration in the long term. Personas establish baseline `<identity>`, domain background, and tool catalog (exact rules for persona switching/inheritance across sessions remain TBD).
- **Rationale**: Prepares Seamus for multi-domain autonomous workflows while prioritizing autonomous coding for Seamus self-development.
- **Provenance**: [0019-threads-modes-personas-architecture.md](../decisions/0019-threads-modes-personas-architecture.md), [threads_modes_personas.md](./threads_modes_personas.md).

### REQ-025: Operational Modes and Thread Transition Triggers
- **Description**: The harness must support an open, extensible set of operational execution modes (such as `plan`, `chat`, `act`, `analyse`, and a planned classifier-based `routing` mode) that dictate interaction posture, prompt framing, and workspace mutability. Operational mode is a first-class property of `AgentConfig` (`AgentConfig.mode`), defaulting to `plan` (discuss phase), inherited from configuration templates to agents and down to sessions, and configurable on the session level. Switching operational modes within a session must deterministically update `session.config.mode`, persist the configuration to Git, and close the active thread to open a fresh thread (reusing an empty open thread in place). Modes also define internal thread-opening triggers (e.g. transitioning across `discuss` -> `make` -> `execute` phases in `plan` mode).
- **Rationale**: Cleanly isolates exploratory planning and conversational scratchpads from execution trajectories and Git Sync PR diffs, while allowing purpose-built agents and sessions to configure their operational posture upfront.
- **Provenance**: [0019-threads-modes-personas-architecture.md](../decisions/0019-threads-modes-personas-architecture.md), [0030-operational-modes-and-plan-mode.md](../decisions/0030-operational-modes-and-plan-mode.md), [0032-operational-mode-in-agent-config-and-defaults.md](../decisions/0032-operational-mode-in-agent-config-and-defaults.md), [threads_modes_personas.md](./threads_modes_personas.md).
- **Linked Invariants**: [INV-028](./invariants.md#inv-028-mode-transition-thread-spawning-boundary).

### REQ-026: Exact Turn-Level Session Branching and Lineage Provenance
- **Description**: Users must be able to branch off any completed assistant message in a session ($S_1$) to create a new parallel session ($S_2$) under the same parent agent. $S_2$ must inherit the conversation history up to the end of that specific turn, create Git branch `session/{new_id}` originating from that exact turn's commit, and open a new Gitea Sync PR to `main`. $S_2$ must record its origin in `provenance` and surface a one-click navigation link to $S_1$ in the UI, while $S_1$ remains unaffected. The system must track cumulative branch lineage across recursive branching cascades ($S_1 \to S_2 \to S_3$), rendering inline provenance separators at each historical branch point. Branching is also permitted from `KILLED` and `FAILED` sessions to provide a clean manual retry protocol. Furthermore:
  - **Tool-Execution Branching & Inference Retry**: Users can branch immediately after completed tool calls in an assistant turn (`retry_inference=True`), which slices event history right after the tool results (`TOOL_CALL_RESULT`), copies checkpoint state, and triggers background turn inference in the child session.
  - **User Message Branching**: Clicking branch on a user message branches from the latest prior assistant bubble and immediately dispatches the user message prompt into the newly spawned session (or creates a fresh session if no prior assistant bubble exists).
- **Rationale**: Enables unconstrained experimentation and native manual retry from known good states without modifying earlier session trajectories.
- **Provenance**: [0022-branching-out-and-session-lifecycle.md](../decisions/0022-branching-out-and-session-lifecycle.md).
- **Linked Invariants**: [INV-030](./invariants.md#inv-030-session-branching-turn-isolation--provenance-tracking).

### REQ-027: Terminal Session Lifecycle States and Teardown Guard
- **Description**: Sessions must be governed by an explicit `SessionStatus` lifecycle state (`ACTIVE`, `KILLED`, `FAILED`). Transitioning to `KILLED` (manual user action) or `FAILED` (unhandled execution exception or timeout) must permanently lock the session against further message inputs or thread creation, tear down running background tasks and OpenSandbox container backends, and close any active Gitea Sync PR. Terminal sessions remain readable and branchable for retry. Killing a session during active tool execution must append interrupted `TOOL_CALL_RESULT` events (`is_error=True`) and a `RUN_ERROR` event to ensure tool calls do not remain in WIP state, set thread status to `ERROR`, and ensure the composer send button returns to disabled non-spinner status. The kill action must not be available for sessions that are already errored.
- **Rationale**: Prevents corruption from continuation on broken state and ensures immediate container and PR resource reclamation.
- **Provenance**: [0022-branching-out-and-session-lifecycle.md](../decisions/0022-branching-out-and-session-lifecycle.md).
- **Linked Invariants**: [INV-029](./invariants.md#inv-029-session-terminal-immutability--resource-teardown).

### REQ-028: Automated Continuous Integration via GitHub Actions
- **Description**: The repository must maintain an automated continuous integration pipeline in `.github/workflows/ci.yml` running on every commit (push and pull request). The workflow must enforce Python code formatting (`ruff format --check`), linting (`ruff check`), strict type checking (`mypy`), frontend TypeScript compilation and Vite bundling (`npm run build` in `ui/`), and dual parallel pytest execution on Linux (`ubuntu-latest`): one Docker-enabled runner exercising Gitea container persistence, and one fast in-memory runner (`SEAMUS_TEST_IN_MEMORY=true`) verifying unit isolation. Cross-platform support for macOS and Windows runners is tracked as technical debt.
- **Rationale**: Eliminates manual verification friction, prevents regressions, and guarantees that formatting, typing, testing, and UI compilation invariants are verified continuously on push and pull requests.
- **Provenance**: [0023-github-actions-ci-pipeline.md](../decisions/0023-github-actions-ci-pipeline.md).
- **Linked Invariants**: [INV-002](./invariants.md#inv-002-zero-tooling-check-failures).

### REQ-029: Task Planning, Progress Tracking, and TodoList Middleware Integration
- **Description**: The harness must integrate `TodoListMiddleware` into DeepAgent instantiation across all model providers. Agents must be equipped with the `write_todos` tool to decompose complex tasks into explicit steps and track progress in `PlanningState` (`pending`, `in_progress`, `completed`). Task planning guidelines (`WRITE_TODOS_SYSTEM_PROMPT`) must be appended cleanly to the dynamic LM-XML system prompt generated by `DynamicSystemPromptMiddleware`. The active todo task list and tool schema must be exposed via the Agent Inspector backend and rendered in a dedicated UI tab.
- **Rationale**: Equips autonomous agents with structured task decomposition and real-time state tracking, prevents context wandering on multi-step workflows, and provides operators with full visibility into the agent's internal progress.
- **Provenance**: [0025-todo-list-middleware.md](../decisions/0025-todo-list-middleware.md).
- **Linked Invariants**: [INV-033](./invariants.md#inv-033-configurable-todo-planning-and-system-prompt-composition).

### REQ-032: UI URL State Synchronization, Live Refresh, and Verbose Error Diagnostics
- **Description**: The Web UI must default to a 1:2 sidebar-to-chat split ratio (`0.3333`), provide both structured Form and Raw JSON editing modes in `ConfigModal`, synchronize the active agent, session, thread, and main panel tab with URL query parameters (`?agent=...&session=...&thread=...&tab=...`), automatically refresh the Changes diff view and sidebar entity tree during and after active execution turns, and present unhandled execution errors in an expandable diagnostic panel backed by `error_type` and `traceback` fields in `RUN_ERROR` events.
- **Rationale**: Eliminates manual refresh and raw JSON configuration friction, enables shareable deep links and browser history navigation, and provides immediate in-UI failure diagnostics.
- **Provenance**: [0028-ui-ux-ergonomics-and-url-state.md](../decisions/0028-ui-ux-ergonomics-and-url-state.md).
- **Linked Invariants**: [INV-039](./invariants.md#inv-039-verbose-run_error-event-persistence--ui-state-synchronization).

### REQ-033: Adaptive Card Questionnaire Artifacts, Hierarchical Storage, and Bundled Platform Skills
- **Description**: The harness must support Microsoft Adaptive Cards (v1.5) renderable artifacts persisted under `<session_dir>/artifacts/`, mounted read-only into OpenSandbox as `/artifacts/`, and committed to Git on session branches. Files must resolve via a 3-tier hierarchy (`/artifacts/<class>/<name>/<file>` -> `/artifacts/<class>/<file>` -> `/artifacts/<file>`), with closure verified strictly via instance-level `closed.json` or `submission.json`. The `ask` tool must batch question invocations during an inference turn into `/artifacts/questionnaires/<uuid>/card.json`, supporting single- and multi-choice selections (`Input.ChoiceSet`), write-in fields (`Input.Text`), cardinality constraints, and rejecting duplicate question IDs immediately. When an open blocking artifact exists (`cadence=blocking`), standard user chat input must be blocked (HTTP 409). Submitting an artifact writes canonical `submission.json` and `closed.json`, synthesizes a tool call `read_artifact_submission(<uuid>)` with `{data: ...}`, and resumes agent execution. Calling `read_artifact_submission` in the same turn that created the questionnaire is disallowed. In the Changes diff tab, artifacts must be represented as real git diffs of `card.json` and `submission.json` with segmented diff/rendered view toggles. Platform skills must be bundled at `src/seamus/skills/bundled/` and mounted read-only at `/skills/bundled` with highest precedence.
- **Rationale**: Enables agents to collect structured human feedback, design choices, or plan approvals via rich declarative UI components while maintaining strict sandbox isolation and Git provenance.
- **Provenance**: [0029-SUPERSEDED-a2ui-questionnaire-artifacts.md](../decisions/0029-SUPERSEDED-a2ui-questionnaire-artifacts.md), [0031-migrate-a2ui-to-adaptive-cards.md](../decisions/0031-migrate-a2ui-to-adaptive-cards.md), [adaptive_cards.md](./adaptive_cards.md).
- **Linked Invariants**: [INV-040](./invariants.md#inv-040-hierarchical-artifact-resolution-read-only-sandboxing-and-blocking-conversation-cadence).

### REQ-034: Operational Modes, Multi-Phase Plan Lifecycle, Tabbed Plan Artifacts, and Recursion Limit
- **Description**: The harness must formalize operational execution modes with `chat` and `plan` (with phases `discuss`, `make`, `execute`), dynamic tool provisioning (`ask`, `make_plan`, `update_plan`, `edit_plan`, `discard`), non-blocking tabbed plan artifacts rendered as Adaptive Cards alongside Changes, read-only workspace sandboxing with read-write `/workspace/notes` (`data/notes`) during planning, empty thread reuse upon mode switches or thread creation, left-aligned mode/phase thread badges (`<icon><label><ID/name>`), and elevated LangGraph recursion limit (`DEFAULT_RECURSION_LIMIT = 250`, overridable via `SEAMUS_RECURSION_LIMIT`) to support long autonomous thinking and tool sequences.
- **Rationale**: Protects production workspaces from unreviewed changes during plan formulation, structures complex goals into phased planning with interactive Adaptive Card plan surfaces, avoids orphaned empty threads, and prevents premature recursion errors on lengthy agent reasoning.
- **Provenance**: [0019-threads-modes-personas-architecture.md](../decisions/0019-threads-modes-personas-architecture.md), [0030-operational-modes-and-plan-mode.md](../decisions/0030-operational-modes-and-plan-mode.md), [0031-migrate-a2ui-to-adaptive-cards.md](../decisions/0031-migrate-a2ui-to-adaptive-cards.md), [threads_modes_personas.md](./threads_modes_personas.md), [adaptive_cards.md](./adaptive_cards.md).
- **Linked Invariants**: [INV-005](./invariants.md#inv-005-single-open-thread-invariant), [INV-028](./invariants.md#inv-028-mode-transition-thread-spawning-boundary), [INV-041](./invariants.md#inv-041-operational-mode-mount-policy-non-blocking-tabbed-plans-and-recursion-limit).

## Cross-References
- [backlog.md](./backlog.md)
- [invariants.md](./invariants.md)
- [threads_modes_personas.md](./threads_modes_personas.md)
- [adaptive_cards.md](./adaptive_cards.md)
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
- [0018-dynamic-system-prompt-architecture.md](../decisions/0018-dynamic-system-prompt-architecture.md)
- [0019-threads-modes-personas-architecture.md](../decisions/0019-threads-modes-personas-architecture.md)
- [0022-branching-out-and-session-lifecycle.md](../decisions/0022-branching-out-and-session-lifecycle.md)
- [0023-github-actions-ci-pipeline.md](../decisions/0023-github-actions-ci-pipeline.md)
- [0024-anthropic-skills-and-system-settings.md](../decisions/0024-anthropic-skills-and-system-settings.md)
- [0025-todo-list-middleware.md](../decisions/0025-todo-list-middleware.md)
- [0027-skills-config-project-rules-and-inspector.md](../decisions/0027-skills-config-project-rules-and-inspector.md)
- [0028-ui-ux-ergonomics-and-url-state.md](../decisions/0028-ui-ux-ergonomics-and-url-state.md)
- [0030-operational-modes-and-plan-mode.md](../decisions/0030-operational-modes-and-plan-mode.md)
- [0031-migrate-a2ui-to-adaptive-cards.md](../decisions/0031-migrate-a2ui-to-adaptive-cards.md)
- [0032-operational-mode-in-agent-config-and-defaults.md](../decisions/0032-operational-mode-in-agent-config-and-defaults.md)
