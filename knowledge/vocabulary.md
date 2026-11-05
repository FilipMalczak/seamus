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

### Persona
An extensible archetype configuring an agent's baseline identity, domain specialization, expertise, demeanor, and available tool palette (with immediate near-term focus on `Coder`, and long-term support for custom personas). Switching and inheritance rules across sessions remain TBD.

### Session (Conversation)
A distinct conversational interaction context with an agent. Each session maintains an isolated copy of configuration derived from its parent agent, holds a dedicated DeepAgent instance, and consists of one or more sequential threads.

### Session Status
The lifecycle posture of a session entity:
- `ACTIVE`: Normal operational state; accepts user turns and runs tools.
- `KILLED`: Permanently terminated via manual user action; rejects new inputs and tears down container/PR resources.
- `FAILED`: Permanently terminated via unhandled runner exception or timeout; rejects new inputs and tears down container/PR resources.

### Session Branching & Provenance
The mechanism and lineage metadata tracking the creation of a child session from a completed assistant message in a parent session. The child session inherits conversational history and Git repository state up to the exact commit of that turn, while recording `parent_session_id`, `parent_message_id`, and `branched_at` for one-click navigation.

### Operational Mode
The active execution posture and behavioral style governing an agent during a thread turn within an open, extensible set of modes:
- `chat`: Conversational dialogue and direct code editing posture; `/workspace` is mounted read-write and notes is an unconstrained directory. Exposes `ask` and `read_artifact_submission`.
- `plan`: Multi-phase planning mode comprising three distinct execution phases, each operating in an isolated thread boundary:
  - `discuss`: Read-only exploration of `/workspace` with `/workspace/notes` mounted read-write. Exposes `ask`, `form`, `plan()`, `read_artifact_submission`, and `discard()`. Calling `plan()` transitions to Make.
  - `make`: Synthesizes notes into a session-local Plan artifact (`exposition="tabbed"`, `cadence="nonblocking"`) with `/workspace` and `/workspace/notes` mounted read-only. Exposes `make_plan` (replaced dynamically by `update_plan` and `edit_plan` once created), `read_artifact_submission`, and `discard()`. Advancing to Execute is driven by user clicking the "Proceed" button on the Plan tab.
  - `execute`: Implements and verifies the approved plan with `/workspace` mounted read-write and `/workspace/notes` mounted read-only. Exposes `discard()`.
- `act`: Direct task execution; follows commands and performs edits immediately without upfront planning cycles.
- `analyse`: Read-only workspace investigation; inspects code, runs queries, and answers questions without mutating persistent files.
- `routing` (planned): Uses a classifier model or tool-wrapped LLM to triage user input and dispatch to an appropriate operational mode.

### Plan Artifact
A specialized declarative Markdown document artifact representing a session-level implementation plan (`exposition="tabbed"`, `cadence="nonblocking"`). Rendered in a dedicated tab to the right of `Changes` in the Web UI with a "Proceed" button that advances the session from `plan/make` to `plan/execute`. Closed when the thread is accepted or discarded.

### Thread
A sub-conversation segment within a session representing a discrete execution phase and mode boundary. Only the most recently created thread in a session is open; earlier threads are closed. A thread records AG-UI streaming events, tracks execution status, and executes within a specific operational mode. Switching operational modes closes the active thread and spawns a fresh thread.

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

### Execution Sandbox (`OpenSandbox`)
An isolated container environment managed by a locally hosted `opensandbox-server` and bridged to DeepAgent via `langchain-sandbox-opensandbox` (`SeamusOpenSandboxBackend`). All agent file operations and shell commands execute inside the sandbox container.

### Operational Directory (`/workspace`)
The mount path inside an agent's execution sandbox container where the session's Git-tracked `data/` directory is mounted. Files inside `/workspace` are version-controlled and persisted across checkpoints; all paths outside `/workspace` in the sandbox container are transient.

### Agent Inspector
An introspection subsystem (accessible via the `GET .../inspect` endpoint and the UI `[Inspector]` tab) surfacing the full runtime manifest of an agent as of its latest inference run: decomposed system prompt layers, registered tool parameter schemas, execution backend bindings, inference configuration with credential masking, Gitea branch/commit provenance, and message trajectory.

### Composite System Prompt
The effective prompt received by the language model assembled dynamically per-inference in structured LM-XML from base scaffolding (`build_scaffold_prompt`), dynamic runtime context (timestamps, workspace path, session/agent identifiers), and user-configured custom instructions.

### LM-XML
Language Model XML; an opinionated, predictable serialization format mapping Python data structures and Pydantic models to human- and model-readable XML tags without attributes (except list item indexing), ensuring deterministic structural parsing by language models.

### Sync PR
An automated Gitea pull request opened from a session branch (`session/{session_id}`) targeting the repository's base branch (`main`). Created upon session workspace initialization and renewed after each thread acceptance.

### Thread Acceptance
The explicit human-in-the-loop lifecycle transition triggered by the top bar "Accept" action. Closes the active thread, merges the session's active Sync PR into `main`, spawns a fresh thread on the same session branch, and opens a new Sync PR to `main`.

### Tool Call Lifecycle States
The deterministic execution phases of an invoked agent tool: `Pending` (arguments preparing / streaming), `WIP` (tool executing within backend sandbox), `Done` (execution finished successfully with output result), and `Failed` (tool execution errored).

### Artifact
A structured, declarative UI surface or deliverable component generated by or for the agent, persisted under `<session_workspace>/artifacts/`, mounted into OpenSandbox containers at `/artifacts` strictly read-only (`readOnly=True`), and committed to Git on session branches.

### A2UI
Agent-to-User Interface; an open declarative UI specification (v0.9) structuring user interface lifecycles as a sequence of discrete events: `createSurface`, `updateComponents`, `updateDataModel`, and `deleteSurface`.

### Questionnaire
A specialized interactive A2UI artifact presented to the user to collect answers, preferences, or choices via structured chips and text inputs. Batched during an inference turn via `ask` and rendered with a blocking conversation cadence (`cadence=blocking`).

### Bundled Skill
A core harness platform skill maintained directly in repository source (`src/seamus/skills/bundled/`), mounted into OpenSandbox at `/skills/bundled` with highest precedence over session and system skills, and surfaced in the Agent Inspector.

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
- [0019-threads-modes-personas-architecture.md](../decisions/0019-threads-modes-personas-architecture.md)
- [0029-a2ui-questionnaire-artifacts.md](../decisions/0029-a2ui-questionnaire-artifacts.md)
- [threads_modes_personas.md](./threads_modes_personas.md)
- [architecture.md](./architecture.md)
- [abstractions.md](./abstractions.md)
- [backlog.md](./backlog.md)
