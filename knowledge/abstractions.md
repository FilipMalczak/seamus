# Abstractions

Interfaces, protocols, abstract base classes, implementations, package boundaries, and extension points.

## Package Boundaries

### `seamus` (`src/seamus`)
- The main package entry point.
- Exports public version `__version__`.
- All modules must be typed and covered by PEP 561 marker `py.typed`.

### `ui` (`ui`)
- React 19 single-page application.
- `api/client`: Typed async HTTP and SSE streaming client for `/api/v-alpha/`.
- `components/Sidebar`: Hierarchical tree component displaying agents, sessions, and threads.
- `components/ChatArea`: Conversational UI consuming live and replayed AG-UI events.
- `components/ConfigModal`: Interactive in-browser JSON editor for config templates and entity configs.

### `seamus.config` (`src/seamus/config`)
- Configuration abstractions and stores.
- `InferenceFormat`: Supported inference protocol shapes (e.g. `openai`).
- `InferenceConfig`: Provider settings (format, base URL, optional API key).
- `TodoImplementation`: Supported planning/todo list implementations (`none`, `deepagents`).
- `SkillsImplementation`: Supported skills discovery and disclosure middleware implementations (`none`, `deepagents`).
- `AgentConfig`: Agent and session configuration model (inference settings, model name, optional system prompt, `todo_implementation`, and `skills_implementation`, both defaulting to `deepagents`). Provides `is_complete()`, `validate_complete()`, and `copy_with_overrides()` for inheritance.
- `SystemSettings`: System-wide configuration model (`skill_directories: list[str]`) not scoped to any agent or session.
- `ConfigTemplateStore`: Persistent container for the service-wide singleton `AgentConfig` template, backed by Gitea repository `system` with first-run defaults.
- `SystemSettingsStore`: Persistent container for service-wide `SystemSettings`, backed by Gitea repository `system` with first-run defaults.

### `seamus.domain` (`src/seamus/domain`)
- Core business entities independent of web or storage frameworks.
- `AgentStatus`: Enumeration of thread states (`AWAITING_USER`, `AWAITING_LLM`, `EXECUTING_TOOL`, `ERROR`).
- `SessionStatus`: Enumeration of session lifecycle states (`ACTIVE`, `KILLED`, `FAILED`).
- `SessionBranchProvenance`: Data model recording branching lineage (`parent_session_id`, `parent_message_id`, `parent_session_name`, `branched_at`).
- `Thread`: Models conversation thread state, open/closed flag, creation and touched timestamps, and past AG-UI event records.
- `Session`: Models an ongoing conversation with an agent, holding an isolated `AgentConfig`, lifecycle `status`, optional `provenance` (immediate parent), cumulative `lineage` (multi-level branch provenance chain), a dedicated runner, and child threads.
- `Agent`: Models an agent entity holding a complete `AgentConfig` and child sessions.
- `Resolution`: Identifier resolution functions mapping UUID or slug strings to entities within their scope.

### `seamus.harness` (`src/seamus/harness`)
- Execution engine, sandbox integration, and state storage.
- `ReasoningChatOpenAI`: `ChatOpenAI` subclass extracting OpenAI-compatible and OpenRouter reasoning fields (`reasoning`, `reasoning_content`, `reasoning_details`) into `additional_kwargs["reasoning_content"]`.
- `SeamusLangGraphAgent`: `LangGraphAgent` subclass preserving full checkpoint message history in `langgraph_default_merge_state` so `gen_ai.prompt.messages` remains a prefix of `gen_ai.completion.messages`.
- `SandboxSettings`: Runtime configuration for connecting to `opensandbox-server` and configuring sandbox container image, timeouts, operational directory (`/workspace`), and shared workspace volume.
- `get_or_create_sandbox_api_key`: Autogenerates and retrieves the internal runtime-managed API key for `opensandbox-server` authentication without exposing secrets to users.
- `build_scaffold_prompt` / `build_sandbox_system_prompt`: Generates structured XML system prompt instructions (serialized via `lmxml`) informing the agent of its identity, `/workspace` operational persistence boundaries, engineering discipline, tool rules, and communication style.
- `build_effective_system_prompt`: Assembles the complete LM-XML system prompt combining the base scaffold, dynamic turn context, and user-configured custom instructions.
- `DynamicSystemPromptMiddleware`: LangChain/DeepAgents middleware intercepting model requests to dynamically update `system_message` on each inference turn.
- `TodoListMiddleware` / `SeamusTodoListMiddleware`: Middleware providing the `write_todos` tool, tracking task states (`pending`, `in_progress`, `completed`) in `PlanningState`, appending task management guidance to the dynamic system prompt, and providing resilient schema normalization (`ResilientWriteTodosInput`) for common LLM key/state variations. Instantiated conditionally when `session.config.todo_implementation == TodoImplementation.DEEPAGENTS`.
- `SeamusOpenSandboxBackend`: `OpenSandboxBackend` (`langchain_opensandbox`) subclass providing lazy per-session `SandboxSync` container provisioning, mounting `<session_workspace>/data` at `/workspace` (read-write), and mounting configured system-wide skill directories as strictly read-only (`readOnly=True`) volumes at in-sandbox paths `/skills/system/{idx}`. Implements `get_skill_sources()` to supply DeepAgents with appropriately prioritized in-sandbox skill sources (`system[last] -> ... -> system[0] -> /workspace/.skills -> /workspace/skills`).
- `SessionAgentRunner`: Encapsulates DeepAgent graph instantiation (with `SeamusOpenSandboxBackend`, `DynamicSystemPromptMiddleware`, conditional `TodoListMiddleware`, conditional Anthropic skills integration via `SkillsMiddleware` controlled by `skills_implementation`, and `GitCheckpointSaver`), input handling, event lifecycle mapping (including `REASONING_*` events), and dynamic graph recompilation via `reload_config(session)`.
- `RunnerRegistry`: Maintains active `SessionAgentRunner` instances keyed by session ID with `reload_session_runner(session)` for instant configuration synchronization upon session updates.
- `AgentInspectReport`: Data model capturing identity, Gitea branch provenance, model & inference settings, decomposed system prompts (composite and scaffold including active `TodoListMiddleware` and `SkillsMiddleware` prompt sections, plus custom instructions), tool argument schemas, active todos (`todos: list[TodoInspectItem]`), discovered skills (`skills: list[SkillInspectInfo]` with `host_path` for system-mounted skills), execution status, and trajectory history.
- `build_agent_inspect_report`: Harness inspection service extracting semi-live agent state from active `SessionAgentRunner` instances or persisted Gitea branch state.
- `EventBroadcaster`: Fan-out pub-sub queue mechanism for multiplexing real-time AG-UI SSE events to multiple active thread consumers.
- `HarnessStore`: In-memory repository managing agents, sessions, and threads with scope-bound slug uniqueness.

### `seamus.server` (`src/seamus/server`)
- Web framework and protocol mapping.
- `create_app`: Factory assembling FastAPI app, CORS middleware, and APIRouters under `/api/v-alpha/`. Optionally mounts built `ui/dist` directory for standalone web serving.
- Routes: Modular endpoint packages for config templates, agents, sessions, threads, and system metadata (`routes/system.py`).
- Schemas: Pydantic request and response models enforcing API contracts (including `SystemInfoResponse` and `SystemLogfireInfo`) and masking secrets where appropriate.

### `seamus.telemetry` (`src/seamus/telemetry.py`)
- Logfire configuration and OpenTelemetry environment management.
- `setup_telemetry`: Initializes Logfire respecting `LOGFIRE_SEND_TO_LOGFIRE`, custom scrubbing preserving `session` identifiers, and sets LangChain/LangGraph OTel export environment variables (`LANGSMITH_OTEL_ENABLED=true`, etc.).
- `is_logfire_enabled`: Evaluates whether telemetry export to Logfire is actively enabled.
- `get_logfire_service_name`: Retrieves the active or configured service name for trace identification.
- `instrument_fastapi`: Hooks Logfire request tracing into FastAPI applications with configurable route exclusion (`excluded_urls`, filtering `/health`).

### Persistence Subsystem (`src/seamus/persistence/`)
- `GiteaClient`: REST API client wrapping `httpx` to manage Gitea repositories, branches, repository merge capabilities (`allow_manual_merge`, `autodetect_manual_merge`), raw file access, and Pull Request lifecycle (`create_pull_request`, `get_pull_request`, `get_pull_request_diff`, `list_pull_requests`, `approve_pull_request`, `merge_pull_request`).
- `GitWorkspaceManager`: Local Git repository orchestrator handling repository initialization on `main`, session working tree cloning on `session/{session_id}`, whole-directory configuration commits (`config:` prefix on `agent/config/**`), thread state updates (`state:` prefix on `agent/state/**`), checkpoint commits (`checkpoint:` prefix staging `data/` and `agent/state/**`), dedicated `system` Git repository orchestration (persisting `settings.json` and `config-template.json`), and data-scoped Sync PR lifecycle management (`open_sync_pr`, `get_active_sync_pr`, `get_sync_pr_diff`, `merge_sync_pr`). Managed as a global singleton via `get_workspace_manager()` and resettable via `reset_workspace_manager()`.
- `GitCheckpointSaver`: Subclass of `MemorySaver` (and wrapping LangGraph `BaseCheckpointSaver`) intercepting `put`, `aput`, and writes to persist graph checkpoint state, human-readable messages, and automatically commit all modified files in `data/` and `agent/state/` to Gitea. Supports `copy_thread(source_thread_id, target_thread_id)` to clone checkpoint memory, writes, and blobs between threads during branching.
- `PersistenceSettings`: Runtime configuration specifying Gitea URL, credentials, and local workspace directory.

### Web UI Presentation Subsystem (`ui/src/`)
- `MarkdownRenderer`: Reusable Markdown rendering component wrapping `react-markdown` with `remark-gfm`. Provides custom renderers for fenced code blocks (with language label bar and copy-to-clipboard action), tables (with horizontal overflow wrapper), and anchor links (`target="_blank"` with `rel="noopener noreferrer"`). Supports `variant="user" | "assistant"` for bubble contrast.
- `MessageItem`: Renders individual conversational message bubbles, reasoning/thought process expandable drawers, tool call traces, and embeds `MarkdownRenderer` for message text.
- `ToolCallItem`: Renders collapsible tool call execution cards with visual lifecycle status badges (`Pending`, `WIP`, `Done`, `Failed`), formatted input arguments (parsed JSON or raw string), and execution result outputs.
- `useThreadStream`: Custom React hook orchestrating SSE stream consumption, real-time message accumulation, structured error diagnostic capture (`StreamErrorDetails` with `message`, `errorType`, `traceback`), and AG-UI event reduction (`TOOL_CALL_START`, `TOOL_CALL_ARGS`, `TOOL_CALL_END`, `TOOL_CALL_RESULT`, `REASONING_*`, `TEXT_MESSAGE_*`, `MESSAGES_SNAPSHOT`) into structured `ChatMessage` and `ToolCallRecord` models.
- `Sidebar`: Navigation sidebar managing hierarchical tree nodes (Agents, Sessions, Threads) with inline renaming, operational status pills, and external system links footer without manual thread creation triggers.
- `ChatArea`: Conversation viewport orchestrating SSE stream binding, message listing, auto-scroll, thread status banners, expandable diagnostic error panel (`chat-error-panel` with error type badge, copy action, and stack trace viewer), and composer textarea with auto-focus.
- `AgentInspector`: Tabbed agent inspection console surfacing decomposed system prompts (composite, scaffold, custom) with Markdown rendering and copy action, tool inventory with expandable JSON parameter schemas, inference runtime parameters, message trajectory, active task list (`todos`), and workspace file listing.
- `ChangesViewer`: Tabbed session changes view rendering the active Sync PR unified diff using `@pierre/diffs` with unified/split mode toggle, hierarchical Tree and flat List file navigation sidebar with status badges and diff stats, per-file collapsible diff cards, external Gitea PR link, manual and automatic live turn-transition/polling refresh, and the relocated "Accept" button.
- `ConfigModal`: Modal editor for agent and session configuration supporting both a structured Form view (model presets + custom identifier, inference format, base URL presets, API key toggle/clear, middleware implementation selectors, and system prompt) and a Raw JSON editor with syntax validation and formatting.
- `SettingsModal`: Modal editor for system settings (managing `skill_directories` via path list and raw JSON with a prominent warning against system-level skills).
- `A2uiArtifactRenderer`: Front-end component rendering A2UI v0.9 surfaces (`@a2ui/react` and `@a2ui/web_core`) within chat message bubbles, handling form action dispatching and disabled state for closed artifacts.

### Artifacts Subsystem (`seamus.domain.artifacts`, `seamus.harness.artifacts`)
- `ArtifactManifest`: Pydantic model (`exposition: Literal["embedded", "tabbed"]`, `cadence: Literal["blocking", "nonblocking"]`).
- `ArtifactInfo`: Pydantic model describing an artifact instance (`kind`, `name`, `manifest`, `is_closed`, `surface`, `components`, `data`).
- `ArtifactResolver`: File resolver traversing the 3-tier directory hierarchy (`/artifacts/<kind>/<name>/<file>` -> `/artifacts/<kind>/<file>` -> `/artifacts/<file>`) and checking instance-scoped `deleteSurface.json` for closure.
- `QuestionnaireBuilder`: Builder constructing A2UI v0.9 `updateComponents` structures from batched `QuestionItem` inputs.
- `ask`: Agent tool batching questionnaire questions during an inference turn.
- `read_artifact_submission`: Agent tool and synthetic tool call returning `{data: ...}` from canonical `updateDataModel.json`.

## Design Principles
- **Explicit over Implicit**: Prefer concrete, simple classes and protocols rather than speculative abstraction layers.
- **Separation of Concerns**: Keep framework/harness mechanics separate from application and agent domain code.
- **Type Annotations**: Public functions, methods, and classes must carry explicit type annotations.

## Cross-References
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
- [0024-anthropic-skills-and-system-settings.md](../decisions/0024-anthropic-skills-and-system-settings.md)
- [0025-todo-list-middleware.md](../decisions/0025-todo-list-middleware.md)
- [0026-in-sandbox-skill-mount-paths.md](../decisions/0026-in-sandbox-skill-mount-paths.md)
- [0027-skills-config-project-rules-and-inspector.md](../decisions/0027-skills-config-project-rules-and-inspector.md)
- [0028-ui-ux-ergonomics-and-url-state.md](../decisions/0028-ui-ux-ergonomics-and-url-state.md)
- [0029-a2ui-questionnaire-artifacts.md](../decisions/0029-a2ui-questionnaire-artifacts.md)
- [architecture.md](./architecture.md)
- [backlog.md](./backlog.md)
- [conventions.md](./conventions.md)
