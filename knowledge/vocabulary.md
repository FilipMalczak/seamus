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
- `chat`: Conversational dialogue and direct code editing posture; `/workspace` is mounted read-write and notes is an unconstrained directory. Exposes `make_questionnaire` and `wait_for_click`.
- `plan`: Multi-phase planning mode comprising three distinct execution phases, each operating in an isolated thread boundary:
  - `discuss`: Workspace exploration and requirements gathering with `/workspace` mounted read-write. The agent is free to organize notes and specifications in any workspace directory without restriction. Exposes `make_questionnaire`, `make_form`, `plan()`, `wait_for_click`, and `discard()`. Calling `plan()` transitions to Make. The agent is strictly constrained from implementing code or writing the plan artifact during Discuss.
  - `make`: Synthesizes workspace notes and codebase findings into a session-local Plan artifact (`exposition="tabbed"`, `blocking=false`) with `/workspace` mounted read-only. Exposes `make_plan`, `wait_for_click`, and `discard()`. Advancing to Execute is driven by user clicking the "Proceed" button on the Plan tab.
  - `execute`: Implements and verifies the approved plan with `/workspace` mounted read-write and `/workspace/notes` mounted read-only. Exposes `discard()`.
- `act`: Direct task execution; follows commands and performs edits immediately without upfront planning cycles.
- `analyse`: Read-only workspace investigation; inspects code, runs queries, and answers questions without mutating persistent files.
- `routing` (planned): Uses a classifier model or tool-wrapped LLM to triage user input and dispatch to an appropriate operational mode.

### Thread
A sub-conversation segment within a session representing a discrete execution phase and mode boundary. Only the most recently created thread in a session is open; earlier threads are closed. A thread records AG-UI streaming events, tracks execution status, and executes within a specific operational mode. Switching operational modes closes the active thread and spawns a fresh thread.

### Slug (Name)
A human-readable, URL-safe identifier formatted as lowercase words separated by hyphens (e.g. `foo-bar-baz`, regex: `^[a-z0-9]+(?:-[a-z0-9]+)*$`). Slugs can be assigned to agents, sessions, and threads as alternative identifiers to UUIDs.

### Daemon
A lightweight, non-agentic, one-shot LLM utility executing a plain `Instructions: ... Input: ... Output:` prefill prompt without tools, conversational history, or multi-turn agentic loops. Configured per-agent under `agent_config.daemons`.

### Naming Daemon
A specialized daemon service generating concise, descriptive slugs:
- **Thread Naming Daemon**: Synthesizes a thread slug from user and assistant exchanges (including created artifacts and actions) while avoiding occupied slugs in the session.
- **Session Naming Daemon**: Synthesizes an overarching session slug from the constituent thread slugs while avoiding occupied session slugs under the agent.

### Full Exchange
A completed conversational interaction spanning from the start of a user input (or unblocking artifact action) to either the end of an assistant text response (`TextMessageEndEvent`) or the moment an artifact blocks the conversation (`manifest.blocking = True`). Rounds down so in-progress turns are excluded.

### Geometric Stepback Schedule
An execution schedule where triggers fire at full exchange counts $N \in \{2^k - 1 \mid k \ge 1\} = \{1, 3, 7, 15, 31, \dots\}$, doubling the step interval between consecutive daemon runs.

### Parallel Slug Model
The architecture storing both user-defined slugs (`custom_name`) and daemon-generated slugs (`daemon_name`) in parallel on `Thread` and `Session` entities. The effective `name` prioritizes `custom_name`, while daemon naming continues running in the background to provide instant fallback if the user clears their custom slug.

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
A structured, declarative UI surface or deliverable component generated by or for the agent, persisted under `<session_workspace>/artifacts/<family>/<uuid>/`, mounted into OpenSandbox containers at `/artifacts` strictly read-only (`readOnly=True`), and committed to Git on session branches.

### A2UI
Adaptive Agent User Interface; a declarative UI specification (v0.9) structuring user interface lifecycles and component hierarchies. In Seamus, the A2UI basic component schema is used as the canonical declarative UI representation for artifacts (`body.json`), with the runtime event stream generated dynamically in-memory for the web renderer. See the [upstream A2UI specification](https://github.com/a2ui-project/a2ui) and [artifacts.md](./artifacts.md).

### Questionnaire
A specialized interactive artifact (`family="questionnaires"`, `exposition="embedded"`, `blocking=true`) presented inline in the chat conversation to collect answers, preferences, or choices via structured chips and inputs. Created atomically via `make_questionnaire`. See [artifacts.md](./artifacts.md).

### Form
A specialized interactive artifact (`family="forms"`, `exposition="tabbed"`, `blocking=false`) presented in a dedicated sidebar tab to collect multi-field inputs or structured configuration options without blocking conversational dialogue. Created atomically via `make_form`. See [artifacts.md](./artifacts.md).

### Plan Artifact
A specialized declarative Markdown document artifact (`family="plans"`, `exposition="tabbed"`, `blocking=false`, `commentable=true`) representing a session-level implementation plan. Rendered in a dedicated tab to the right of `Changes` in the Web UI with a "Proceed" button that advances the session from `plan/make` to `plan/execute` and an inline commenting system for section-level review. Created atomically via `make_plan`. See [artifacts.md](./artifacts.md) and [0030-operational-modes-and-plan-mode.md](../decisions/0030-operational-modes-and-plan-mode.md).

### Bundled Skill
A core harness platform skill maintained directly in repository source (`src/seamus/skills/bundled/`), mounted into OpenSandbox at `/skills/bundled` with highest precedence over session and system skills, and surfaced in the Agent Inspector.

### Secret Reference
A symbolic string interpolation expression (`${secret('/path')}` or `${secret(path='/path', field='value')}`) embedded inside configuration fields (`InferenceConfig`, `AgentConfig`, `ConfigTemplate`). Evaluated strictly in memory against the OpenBao KV v2 vault (`secret/`) so cleartext credentials are never persisted to disk or Git. See [0041-openbao-secrets-vault-integration.md](../decisions/0041-openbao-secrets-vault-integration.md).

### Exploded Secret Reference
The canonical, version-pinned form of a secret reference (`${secret(path='/path', field='value', version=N)}`) written exclusively to on-disk `agent/config/config.json` during checkpoint commits to record the exact OpenBao secret version active prior to that checkpoint while keeping live in-memory session configs unversioned. See [0041-openbao-secrets-vault-integration.md](../decisions/0041-openbao-secrets-vault-integration.md).

### External Repository
A user-configured remote Git repository mounted into an agent session's OpenSandbox environment under `/projects/{mount_name}`. Unlike the agent repository (`agent-{agent_id}`), external repositories represent third-party or existing codebases where the agent can run normal Git commands (`git status`, `git commit`, `git diff`) without polluting or coupling the project's semantic history to Seamus harness internals.

### Dual-Index Checkpoint
An automated filesystem snapshot mechanism that stages the working tree into an isolated, out-of-tree Git index (`.seamus_indexes/{attachment_id}.idx`) via `GIT_INDEX_FILE` and creates snapshot commits pushed to Gitea (`refs/seamus/checkpoints/...`). Dual-index checkpointing ensures that Seamus snapshots capture all modified and untracked files (respecting `.gitignore`) without altering the agent's active `.git/index`, `HEAD`, or working tree.

### Project Repository (Internal)
A dedicated, internal Gitea repository (`project-{project_id}`) mirrored from a remote Git URL, holding the project's upstream branches, session working branches (`session/{session_id}`), and durable Seamus checkpoint references.

### Project Attachment ID
A unique identifier (`uuid4().hex`) distinguishing a specific repository attachment in a session's configuration (`ExternalRepositoryConfig.id`) from the underlying project identity (`project_id = sha256(canonical_url)[:12]`), allowing independent mount configurations and collision-free index storage.

### Local Model Provider (Ollama)
An inference backend running entirely locally (either via the Docker Compose `ollama` service or on the host machine) that does not require external cloud API keys and enables private, offline execution of open-weights models (`InferenceFormat.OLLAMA`).

### Active Model Execution Management
The harness responsibility of explicitly verifying daemon responsiveness via HTTP healthchecks, checking model availability, and pre-loading models into GPU/CPU memory (`POST /api/generate`)—including automated model pulling (`POST /api/pull`) when missing—prior to initializing LangChain execution, ensuring local models are immediately operational.

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
- [0031-SUPERSEDED-migrate-a2ui-to-adaptive-cards.md](../decisions/0031-SUPERSEDED-migrate-a2ui-to-adaptive-cards.md)
- [0034-mature-a2ui-artifacts-model.md](../decisions/0034-mature-a2ui-artifacts-model.md)
- [0041-openbao-secrets-vault-integration.md](../decisions/0041-openbao-secrets-vault-integration.md)
- [0042-mount-external-git-repositories.md](../decisions/0042-mount-external-git-repositories.md)
- [0044-interactive-web-terminal.md](../decisions/0044-interactive-web-terminal.md)
- [0045-ollama-local-model-provider.md](../decisions/0045-ollama-local-model-provider.md)
- [artifacts.md](./artifacts.md)
- [threads_modes_personas.md](./threads_modes_personas.md)
- [architecture.md](./architecture.md)
- [persistence.md](./persistence.md)
- [abstractions.md](./abstractions.md)
- [backlog.md](./backlog.md)
