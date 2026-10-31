# Vocabulary

Canonical terms, definitions, and conceptual distinctions used throughout Seamus.

## Core Concepts

### Agent
An autonomous or semi-autonomous software entity that perceives its environment, reasons, takes actions, and uses tools to accomplish user objectives. In the Seamus harness, an Agent holds a complete configuration and manages one or more Sessions.

### Harness
The execution environment, runtime boundaries, lifecycle control, state persistence, and tool dispatch infrastructure that surrounds and manages agents. Seamus is specifically a deep agent harness designed for full ownership and customization.

### Task
A discrete unit of work requested by a user or assigned to an agent, governed by a lifecycle, branch, and acceptance criteria.

### Run
An execution instance of an agent or harness session executing a task, consisting of prompts, tool calls, results, and state transitions.

### Config Template
A singleton, service-wide configuration baseline specifying inference details (provider format, base URL, API key) and default model. A template may be partially complete (e.g. missing an API key).

### Session (Conversation)
A distinct conversational interaction context with an agent. Each session maintains an isolated copy of configuration derived from its parent agent, holds a dedicated DeepAgent instance, and consists of one or more sequential threads.

### Thread
A sub-conversation segment within a session. Only the most recently created thread in a session is open; earlier threads are closed. A thread records AG-UI streaming events and tracks execution status.

### Slug (Name)
A human-readable, URL-safe identifier formatted as lowercase words separated by hyphens (e.g. `foo-bar-baz`, regex: `^[a-z0-9]+(?:-[a-z0-9]+)*$`). Slugs can be assigned to agents, sessions, and threads as alternative identifiers to UUIDs.

### Agent Status
The operational state of a thread's agent:
- `AWAITING_USER`: Idle, awaiting user input.
- `AWAITING_LLM`: Waiting for model inference or streaming tokens.
- `EXECUTING_TOOL`: Executing an external tool or sub-routine.
- `ERROR`: Terminated due to an unhandled failure.

### Navigation Tree
The frontend hierarchical sidebar component displaying Agents, their child Sessions, and constituent Threads with lifecycle and operational status indicators.

### JSON Config Editor
An in-browser modal interface for inspecting and updating raw JSON configurations for the singleton ConfigTemplate, Agents, and Sessions with client-side syntax validation.

### Telemetry & Spans
OpenTelemetry-compatible observability constructs powered by Pydantic Logfire:
- **Span**: A timed duration representing a single unit of execution or lifecycle operation (e.g., `agent`, `session`, `thread`). Spans contain start/end timestamps, structured attributes (`agent_id`, `session_id`, `thread_id`, `model`), and child spans.
- **Trace**: A directed acyclic tree of nested spans representing a complete end-to-end operation, such as an agent run or an HTTP request.
- **Scrubbing**: Automatic redaction of sensitive credentials and tokens; configured in Seamus to whitelist domain `session` attributes while redacting secrets.

### External System Links & Navigation Footer
Pinned shortcut interface located at the bottom of the navigation tree left panel. Houses quick-launch icons linking to external companion platforms: Logfire telemetry dashboard, Gitea Home, and contextual composite buttons for the selected Agent Git branch (`main`) and Session Git branch (`session/{session_id}`). Display is conditionally controlled based on integration availability and active selection.

### Agent Repository
A dedicated Git repository in Gitea (`agent-{agent_id}`) tracking all versioned state for an Agent. Its `main` branch stores the base configuration (`agent/config/config.json`), a state placeholder (`agent/state/.gitkeep`), and an empty workspace baseline (`data/.gitkeep`).

### Session Branch
An isolated Git branch (`session/{session_id}`) created from `main` holding the session-specific configuration in `agent/config/config.json`, thread conversation and checkpoint state in `agent/state/threads/{thread_id}/`, and agent-generated workspace files in `data/`.

### Checkpoint Commit
An automated Git commit generated whenever a LangGraph checkpointer saves state, committing all new, modified, or deleted files under `data/` and `agent/state/` with the commit message prefix `checkpoint:`. Turn-completion event updates commit with the prefix `state:`.

### Store Hydration
The startup process wherein `HarnessStore` discovers repositories and branches on Gitea to reconstruct in-memory domain entities (`Agent`, `Session`, `Thread`) without needing a direct SQL database in the harness backend.

## Cross-References
- [0001-project-initialization.md](../decisions/0001-project-initialization.md)
- [0002-harness-server-mvp.md](../decisions/0002-harness-server-mvp.md)
- [0003-react-web-ui.md](../decisions/0003-react-web-ui.md)
- [0004-inline-tree-editing-session-status.md](../decisions/0004-inline-tree-editing-session-status.md)
- [0005-logfire-integration.md](../decisions/0005-logfire-integration.md)
- [0006-external-system-links.md](../decisions/0006-external-system-links.md)
- [0007-agui-reasoning-and-trace-messages.md](../decisions/0007-agui-reasoning-and-trace-messages.md)
- [0008-git-persistence.md](../decisions/0008-git-persistence.md)
- [architecture.md](./architecture.md)
- [abstractions.md](./abstractions.md)
- [backlog.md](./backlog.md)
