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
- `AgentConfig`: Agent-level settings (inference configuration and model name). Provides `is_complete()` and copy/derive utilities.
- `ConfigTemplateStore`: In-memory container for the service-wide singleton template, initialized from environment variables with fallback defaults.

### `seamus.domain` (`src/seamus/domain`)
- Core business entities independent of web or storage frameworks.
- `AgentStatus`: Enumeration of thread states (`AWAITING_USER`, `AWAITING_LLM`, `EXECUTING_TOOL`, `ERROR`).
- `Thread`: Models conversation thread state, open/closed flag, creation and touched timestamps, and past AG-UI event records.
- `Session`: Models an ongoing conversation with an agent, holding an isolated `AgentConfig`, a dedicated runner, and child threads.
- `Agent`: Models an agent entity holding a complete `AgentConfig` and child sessions.
- `Resolution`: Identifier resolution functions mapping UUID or slug strings to entities within their scope.

### `seamus.harness` (`src/seamus/harness`)
- Execution engine, sandbox integration, and state storage.
- `ReasoningChatOpenAI`: `ChatOpenAI` subclass extracting OpenAI-compatible and OpenRouter reasoning fields (`reasoning`, `reasoning_content`, `reasoning_details`) into `additional_kwargs["reasoning_content"]`.
- `SeamusLangGraphAgent`: `LangGraphAgent` subclass preserving full checkpoint message history in `langgraph_default_merge_state` so `gen_ai.prompt.messages` remains a prefix of `gen_ai.completion.messages`.
- `SandboxSettings`: Runtime configuration for connecting to `opensandbox-server` and configuring sandbox container image, timeouts, operational directory (`/workspace`), and shared workspace volume.
- `get_or_create_sandbox_api_key`: Autogenerates and retrieves the internal runtime-managed API key for `opensandbox-server` authentication without exposing secrets to users.
- `build_sandbox_system_prompt`: Generates system prompt instructions informing the agent that `/workspace` is its Git-tracked operational directory and all paths outside it are transient.
- `SeamusOpenSandboxBackend`: `OpenSandboxBackend` (`langchain_opensandbox`) subclass providing lazy per-session `SandboxSync` container provisioning and mounting only `<session_workspace>/data` at `/workspace` inside the sandbox container.
- `SessionAgentRunner`: Encapsulates DeepAgent graph instantiation (with `SeamusOpenSandboxBackend`, `build_sandbox_system_prompt`, and `GitCheckpointSaver`), input handling, and event lifecycle mapping (including `REASONING_*` events).
- `AgentInspectReport`: Data model capturing identity, Gitea branch provenance, model & inference settings, decomposed system prompts (scaffold vs. custom), tool argument schemas, execution status, and trajectory history.
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
- `GiteaClient`: REST API client wrapping `httpx` to manage Gitea repositories, branches, raw file access, and Pull Request lifecycle (`create_pull_request`, `get_pull_request`, `list_pull_requests`, `approve_pull_request`, `merge_pull_request`).
- `GitWorkspaceManager`: Local Git repository orchestrator handling repository initialization on `main`, session working tree cloning on `session/{session_id}`, whole-directory configuration commits (`config:` prefix on `agent/config/**`), thread state updates (`state:` prefix on `agent/state/**`), checkpoint commits (`checkpoint:` prefix staging `data/` and `agent/state/**`), and Sync PR lifecycle management (`open_sync_pr`, `get_active_sync_pr`, `merge_sync_pr`).
- `GitCheckpointSaver`: Subclass of `MemorySaver` (and wrapping LangGraph `BaseCheckpointSaver`) intercepting `put`, `aput`, and writes to persist graph checkpoint state, human-readable messages, and automatically commit all modified files in `data/` and `agent/state/` to Gitea.
- `PersistenceSettings`: Runtime configuration specifying Gitea URL, credentials, and local workspace directory.

### Web UI Presentation Subsystem (`ui/src/`)
- `MarkdownRenderer`: Reusable Markdown rendering component wrapping `react-markdown` with `remark-gfm`. Provides custom renderers for fenced code blocks (with language label bar and copy-to-clipboard action), tables (with horizontal overflow wrapper), and anchor links (`target="_blank"` with `rel="noopener noreferrer"`). Supports `variant="user" | "assistant"` for bubble contrast.
- `MessageItem`: Renders individual conversational message bubbles, reasoning/thought process expandable drawers, tool call traces, and embeds `MarkdownRenderer` for message text.
- `Sidebar`: Navigation sidebar managing hierarchical tree nodes (Agents, Sessions, Threads) with inline renaming, operational status pills, and external system links footer without manual thread creation triggers.
- `ChatArea`: Conversation viewport orchestrating SSE stream binding, message listing, auto-scroll, thread status banners, top bar "Accept" action button with tick icon, and composer textarea with auto-focus.
- `AgentInspector`: Tabbed agent inspection console surfacing decomposed system prompts (composite, scaffold, custom) with Markdown rendering and copy action, tool inventory with expandable JSON parameter schemas, inference runtime parameters, message trajectory, and workspace file listing.

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
- [architecture.md](./architecture.md)
- [backlog.md](./backlog.md)
- [conventions.md](./conventions.md)
