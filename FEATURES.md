# Seamus: Features & Capabilities

> **A deep agent harness that I fully own and can customize.**

Seamus is an open, self-hosted, deep agent execution harness and developer workspace. Engineered from the ground up for total developer ownership, Seamus frees you from opaque cloud agent silos, proprietary platforms, and insecure local scripts. Every component—from multi-container sandbox execution and Git-native checkpoint persistence to interactive adaptive UI surfaces and zero-leak secrets management—is transparent, inspectable, and under your absolute control.

---

## Table of Contents

1. [At a Glance](#at-a-glance)
   - [Why Seamus? The Value Proposition](#why-seamus-the-value-proposition)
   - [Architectural Highlights](#architectural-highlights)
   - [Competitive Matrix](#competitive-matrix)
2. [Deep-Dive Feature Breakdown](#deep-dive-feature-breakdown)
   - [1. Agent, Session & Thread Architecture](#1-agent-session--thread-architecture)
   - [2. Multi-Container Execution & Filesystem Sandboxing](#2-multi-container-execution--filesystem-sandboxing)
   - [3. Git-Native Persistence, Checkpointing & Provenance](#3-git-native-persistence-checkpointing--provenance)
   - [4. Operational Modes & Structured Plan Lifecycle](#4-operational-modes--structured-plan-lifecycle)
   - [5. Adaptive UI (A2UI v1.0) & Dynamic Artifacts](#5-adaptive-ui-a2ui-v10--dynamic-artifacts)
   - [6. Anthropic Skills System & Precedence Engine](#6-anthropic-skills-system--precedence-engine)
   - [7. Enterprise Secrets Vault (OpenBao KV v2)](#7-enterprise-secrets-vault-openbao-kv-v2)
   - [8. Developer Web UI & Workspace Ergonomics](#8-developer-web-ui--workspace-ergonomics)
   - [9. DeepAgent Runtime Introspection & Inspector](#9-deepagent-runtime-introspection--inspector)
   - [10. Telemetry & Observability (Pydantic Logfire & OpenTelemetry)](#10-telemetry--observability-pydantic-logfire--opentelemetry)
   - [11. 1-Click Zero-Friction Stack Launch](#11-1-click-zero-friction-stack-launch)
   - [12. Local Model Inference & Active Ollama Lifecycle Management](#12-local-model-inference--active-ollama-lifecycle-management)
   - [13. Non-Agentic Daemons & Automated Naming](#13-non-agentic-daemons--automated-naming)
3. [Every Goddamn Flag (Exhaustive Configuration & Reference Manual)](#every-goddamn-flag-exhaustive-configuration--reference-manual)
   - [CLI Flags & Scripts (`run.sh`)](#cli-flags--scripts-runsh)
   - [Complete Environment Variables Reference](#complete-environment-variables-reference)
   - [Agent & Inference Configuration Schema (`AgentConfig` & `InferenceConfig`)](#agent--inference-configuration-schema-agentconfig--inferenceconfig)
   - [System Settings Schema (`SystemSettings`)](#system-settings-schema-systemsettings)
   - [Docker Compose Topology, Ports & Volumes](#docker-compose-topology-ports--volumes)
   - [Sandbox Filesystem Mount Paths](#sandbox-filesystem-mount-paths)
   - [Harness Tools Palette & Lifecycle Transitions](#harness-tools-palette--lifecycle-transitions)
   - [REST API Endpoints Reference (`/api/v-alpha/`)](#rest-api-endpoints-reference-apiv-alpha)

---

## At a Glance

### Why Seamus? The Value Proposition

| Core Problem in Modern AI Agents | The Seamus Solution |
| :--- | :--- |
| **Black-box hosted agent clouds** lock your data, prompt techniques, and agent workflows inside proprietary vendor platforms. | **100% self-hosted & developer-owned.** Run on your own Linux machine or private cluster. Full source access across the entire stack. |
| **Unsafe local execution** lets agents run arbitrary bash commands and mutate files directly on your workstation. | **Heavyweight container sandboxing (OpenSandbox + Docker).** Agents execute strictly inside isolated disposable Linux containers with granular read-write/read-only mount policies. |
| **Volatile, ephemeral memory** that vanishes on crash, with no audit trail or rollback capability. | **Git-native persistence (Gitea + GitCheckpointSaver).** Every turn, tool call, checkpoint, and file mutation is an immutable Git commit with branches, commit logs, and Sync Pull Requests. |
| **Uncontrolled runaway coding loops** where agents start editing critical code before understanding the task or architecture. | **Rigorous three-phase Plan Mode (`discuss` &rarr; `make` &rarr; `execute`).** Enforces exploration, notes authoring, read-only plan synthesis, and explicit human-in-the-loop review before code mutation. |
| **Flat, unformatted text chat** incapable of collecting structured answers or presenting interactive forms. | **Adaptive UI (A2UI v1.0).** Agents render interactive questionnaires that block until answered, tabbed configuration forms, and dedicated Plan tabs with inline section comments and Proceed gates. |
| **Leaked API keys and plaintext secrets** committed to git repositories, logged in traces, or saved in disk files. | **Integrated OpenBao Secrets Vault (KV v2).** Symbolic `${secret('/path')}` references, strictly in-memory resolution, zero disk secrets, and version-pinned snapshotting in checkpoint commits. |
| **Static, rigid agent configurations** that cannot be extended with modular capabilities. | **Anthropic Skills Standard (`SKILL.md`).** Drop in modular skills with a multi-tiered priority engine spanning bundled, session, background, and system directories. |
| **Opaque reasoning and invisible prompts** making it impossible to debug hallucinations or bad tool calls. | **DeepAgent Inspector.** Deconstructs composite LM-XML system prompts into layered cards, exposes registered JSON tool schemas, tracks active todos, and surfaces live diffs. |

### Architectural Highlights

```
+------------------------------------------------------------------------------------+
|                                    React 19 SPA                                    |
|   [Hierarchical Sidebar] <---> [Multi-Thread Chat & A2UI] <---> [Changes Diff Tab] |
|   [DeepAgent Inspector]  <---> [In-Browser Modal & Raw JSON Config Editor]         |
+------------------------------------------------------------------------------------+
                                         │ (HTTP REST & Real-Time SSE Streams)
                                         ▼
+------------------------------------------------------------------------------------+
|                                 FastAPI Backend                                    |
|   • Singleton ConfigTemplate & SystemSettingsStore                                 |
|   • SessionAgentRunner (DeepAgent Runtime + ReasoningChatOpenAI)                   |
|   • OpenBao Secrets Vault Client & Symbolic Expression Interpolator                |
|   • AG-UI Event Broadcaster (Pub-Sub & History Replay)                            |
|   • DynamicSystemPromptMiddleware (Structured LM-XML Scaffold)                     |
+------------------------------------------------------------------------------------+
                   │                                             │
                   ▼                                             ▼
+-------------------------------------+       +--------------------------------------+
|       OpenSandbox Execution         |       |      Git Persistence & State         |
|  • Containerized execution sandbox  |       |  • Gitea Git Server (Port 3001)      |
|  • Mounts /workspace (data/)        |       |  • Repository per Agent (agent-{id}) |
|  • Mounts /artifacts (read-only)    |       |  • Branch per Session (session/{id}) |
|  • Mounts /skills/bundled (ro)      |       |  • Automated GitCheckpointSaver      |
|  • Mounts system skills (ro)        |       |  • Automated Sync PR Lifecycle       |
|  • Dynamic mode mount policies      |       |  • Zero database in harness backend  |
+-------------------------------------+       +--------------------------------------+
                   │                                             │
                   ▼                                             ▼
+-------------------------------------+       +--------------------------------------+
|          OpenBao Secrets            |       |         Observability Stack          |
|  • OpenBao KV v2 Engine             |       |  • Pydantic Logfire Tracing          |
|  • Token & Key Management           |       |  • OpenTelemetry Native Exporters    |
|  • Version-pinned snapshots         |       |  • Sensitive Credential Scrubbing    |
+-------------------------------------+       +--------------------------------------+
```

### Competitive Matrix

| Feature | Generic Python Frameworks (LangChain vanilla, CrewAI, AutoGen) | Cloud Coding Agents (Cursor, Claude Code, Windsurf) | Seamus Deep Agent Harness |
| :--- | :---: | :---: | :---: |
| **Self-Hosted Ownership** | Partial (requires custom wiring) | No (Vendor Cloud) | **Yes (100% owned & self-hosted)** |
| **Execution Sandboxing** | None (runs directly on host) | Local Process / Cloud VM | **Docker Container (OpenSandbox)** |
| **Persistence Engine** | SQLite / Vector DB / In-memory | Proprietary Cloud DB | **Native Git Repository (Gitea)** |
| **State Rollback & Audit** | Difficult / Manual | Opaque Cloud History | **Git Commits & Branch Provenance** |
| **Workflow Discipline** | Single loop / Freeform | Uncontrolled coding loop | **Phased Plan Mode (`discuss` &rarr; `make` &rarr; `execute`)** |
| **Interactive UI Artifacts** | Text only | Basic diff views | **A2UI v1.0 (Questionnaires, Forms, Plans)** |
| **Secrets Management** | Plaintext `.env` files | Proprietary Cloud Vault | **OpenBao KV v2 + Symbolic References** |
| **Skill Extensibility** | Custom python functions | Proprietary extensions | **Anthropic Skills Standard (`SKILL.md`)** |
| **Inspection & Debugging** | Print statements / loggers | Minimal | **DeepAgent Inspector + LM-XML Prompts** |
| **One-Click Local Launch** | Multi-step manual setup | N/A (Desktop app) | **Automated `./run.sh` Stack Orchestration** |

---

## Deep-Dive Feature Breakdown

### 1. Agent, Session & Thread Architecture

Seamus organizes work into a clean three-tiered entity hierarchy:

- **Agent**: An autonomous software identity configured with a baseline **Persona** (such as `Coder`), inference configuration, custom system prompts, and tools. Each agent owns a dedicated Git repository (`agent-{agent_id}`) on Gitea.
- **Session (Conversation)**: An isolated operational task and conversational context. A session clones its parent agent's configuration and creates an isolated Git branch (`session/{session_id}`). Sessions support full lifecycle states (`ACTIVE`, `KILLED`, `FAILED`) and **Granular Bidirectional Session Branching**, allowing you to fork a new child session from any historical point (user message, system event, bot message, bot reasoning, or tool call) either *before* or *after* the item with commit-level provenance.
- **Thread**: A sequential execution segment within a session representing a discrete operational mode or plan phase. Only the most recent thread in a session is open; earlier threads are sealed. Mode switches automatically close the active thread and spawn a fresh thread, reusing empty threads to eliminate clutter.
- **Dual Identifier Resolution**: Every Agent, Session, and Thread can be addressed by its canonical UUID or by an ergonomic, human-readable, URL-safe slug (e.g. `agent/frontend-bot/session/auth-refactor/thread/discuss-requirements`).

### 2. Multi-Container Execution & Filesystem Sandboxing

Never trust an LLM to run arbitrary commands on your host workstation. Seamus delegates all execution to **OpenSandbox**:

- **Strict Container Isolation**: Agents execute inside containerized Linux environments (default `seamus-sandbox:latest` based on Ubuntu 24.04 with Python 3, Astral `uv`, Node.js, npm, Git, and build essentials; fully customizable per agent/session via `sandbox_image` or globally via `OPENSANDBOX_IMAGE`). Commands outside the sandbox cannot touch host files or networks.
- **Sandboxed Operational Directory (`/workspace`)**: The agent's persistent workspace is mounted at `/workspace`, mapped directly to the session's Git-tracked `data/` directory. Files created or modified inside `/workspace` are tracked, committed, and version-controlled. Everything outside `/workspace` inside the container is transient.
- **Mounted External Git Repositories (`/projects/{name}`)**: Arbitrary user-configured Git repositories are mounted under `/projects/{name}`. Each directory contains a fully functional Git working copy with `.git/`, allowing agents to run `git status`, `git diff`, `git add`, `git commit`, and `git branch` directly inside the container without modifying the host or commingling project code with agent harness internals.
- **Dynamic Mount Policies**: Mount permissions adapt dynamically according to the active mode and plan phase:
  - In `chat` and `plan/discuss`: `/workspace` is mounted read-write.
  - In `plan/make`: `/workspace` is mounted strictly **read-only**, preventing unauthorized code mutations while authoring the plan.
  - In `plan/execute`: `/workspace` is read-write, while `/workspace/notes` is mounted read-only to safeguard historical research.
- **Per-Command Timeouts & TTL**: Configurable per-command execution timeout (default: 300s) and container lifetime TTL (default: 3600s).

### 3. Git-Native Persistence, Checkpointing & Provenance

Seamus eliminates complex relational databases for harness state. Gitea is the single source of truth:

- **Automated Checkpoint Commits**: Whenever the LangGraph checkpointer saves state, Seamus commits all new, modified, or deleted files under `data/` and `agent/state/` with commit prefix `checkpoint:`. Turn completions commit with prefix `state:`.
- **Stateless Harness Hydration**: On server startup, Seamus queries Gitea's API and reconstructs all in-memory agents, sessions, and threads directly from Git branches. No SQL database migrations or lost state.
- **Gitea Sync Pull Requests**: Upon session creation, an automated Sync PR is opened from `session/{session_id}` targeting `main`. The PR status and live deliverable diff are tracked in real-time.
- **Atomic Thread Acceptance**: Clicking "Accept" in the top bar merges the session's deliverables into `main`, closes the active thread, spawns a fresh thread, and opens a renewed Sync PR.
- **Deliverable Isolation**: Git commits strictly distinguish between agent state metadata (`agent/config/`, `agent/state/`) and actual code deliverables (`data/`). Sync PR merges exclusively target `data/`.
- **Dual-Index External Repository Checkpointing**: Mounted external repositories are snapshotted automatically into internal Gitea repositories (`project-{project_id}`) under `refs/seamus/checkpoints/...` before each agent repository commit. Using Git's alternate index mechanism (`GIT_INDEX_FILE`), Seamus captures full working-tree snapshots without altering the agent's staged `.git/index`, `HEAD`, or branch history. Session branching restores exact historical states (`semantic_head`, `staged_tree`, and `snapshot_tree`).

### 4. Operational Modes & Structured Plan Lifecycle

Prevent premature code churn with Seamus's opinionated operational mode engine:

```mermaid
stateDiagram-v2
    [*] --> Chat: Direct Dialogue
    [*] --> Plan_Discuss: Systematic Task
    
    state Chat {
        [*] --> Chat_Active: /workspace Read-Write
    }
    
    state Plan_Mode {
        Plan_Discuss --> Plan_Make: Agent calls plan()
        note right of Plan_Discuss
            /workspace: Read-Write
            Explore code, ask questions,
            author notes in /workspace/notes.
            NO code implementation.
        end note
        
        Plan_Make --> Plan_Execute: User clicks "Proceed"
        note right of Plan_Make
            /workspace: READ-ONLY
            Synthesize notes into
            Markdown Plan artifact.
            User reviews & adds inline comments.
        end note
        
        note right of Plan_Execute
            /workspace: Read-Write
            /workspace/notes: Read-Only
            Implement & verify code.
        end note
    }
```

- **Chat Mode (`chat`)**: Unconstrained conversational dialogue and immediate code editing. Useful for quick fixes, queries, and interactive debugging.
- **Plan Mode (`plan`)**: A structured three-phase pipeline:
  1. **Discuss (`plan/discuss`)**: The agent reads the codebase, gathers requirements, interviews the user via blocking questionnaires (`make_questionnaire`) or non-blocking forms (`make_form`), and records architectural findings in `/workspace/notes`. Code modification is strictly forbidden. When ready, the agent calls `plan()` to advance to Make.
  2. **Make (`plan/make`)**: The workspace is locked to **read-only**. The agent authors and refines the session's Markdown Plan artifact via `make_plan`. The user reviews the rendered plan in a dedicated UI tab, adds section-level comments, and clicks **Proceed** to authorize execution.
  3. **Execute (`plan/execute`)**: With the plan approved, the workspace is unlocked to read-write (with `/workspace/notes` preserved as read-only). The agent implements and verifies the deliverables.
- **Escape Hatch (`discard()`)**: The user or agent can abort the plan workflow at any time, cleaning up active plan artifacts.

### 5. Adaptive UI (A2UI v1.0) & Dynamic Artifacts

Move beyond text chat. Seamus implements the open **A2UI (Adaptive Agent User Interface) v1.0** standard to render dynamic, interactive components directly in the browser:

- **Direct Filesystem Persistence**: Artifacts are stored under `<session_workspace>/artifacts/<family>/<uuid>/`, capturing `manifest.json`, `body.json`, pretty-printed `state.json` (recording `state.last_event`), untrimmed event logs (`/interactions/<button_id>.jsonl`), and auxiliary `answers.md` for question-centric artifacts.
- **Automatic Input Snapshots & Static Context**: Interactive buttons automatically capture a value snapshot of all interactive input widgets across the surface into event `data` on click without requiring manual context definitions. Dynamic context pointers (`{path: ...}`) on button actions are disallowed and automatically dropped during normalization with educational mutation logs, while non-dynamic static context (such as `{approved: true}`) is preserved.
- **Embedded Questionnaires (`make_questionnaire`)**: Rendered directly in the chat stream with `blocking=true`. The agent calls `wait_for_click`, pausing execution until the user selects chips, radio options, or fills in text inputs. Answers and context are summarized automatically into `answers.md`.
- **Tabbed Forms (`make_form`)**: Non-blocking forms rendered in dedicated workspace tabs for complex configuration input while the agent continues background tasks.
- **Interactive Implementation Plans (`make_plan`)**: Markdown-rendered plan artifacts with section-level inline commenting, approval indicators, and the interactive **Proceed** action.
- **Auto-Repair & Normalization**: The harness includes automatic component tree normalization (`normalize_a2ui_components`), button declaration auto-synthesis, pre-render surface validation, and structural warning checks to ensure invalid LLM UI JSON never breaks the frontend.
- **Strict UAX #31 Compliance & Reference Remapping**: Component IDs strictly adhere to Unicode Standard Annex #31 (`c_id.isidentifier()`). Hyphenated identifiers and illegal characters are automatically sanitized into snake_case (`submit_btn`, `review_btn`, `proceed_btn`) with all child, trigger, content, and action context references remapped dynamically.
- **Negative Constraint on Redundant Options**: Harness prompts and bundled skills strictly instruct agents never to author explicit "Other" or "Custom" choices when `write_in=True` is enabled on questionnaires, as the A2UI renderer automatically supplies the necessary freeform text input.

### 6. Native LM-XML Skills System & Precedence Engine

Extend your agents using the open [Anthropic Agent Skills standard](https://docs.langchain.com/oss/python/deepagents/skills). Skills are self-contained directories with a `SKILL.md` file featuring YAML frontmatter:

- **Native LM-XML Progressive Disclosure**: Available skills are rendered directly into the dynamic LM-XML system prompt (`<skills><available_skills>...</available_skills></skills>`), allowing the agent to discover capabilities without polluting the context window.
- **Explicit Context Lifecycle (`load_skill` & `unload_skill`)**: The agent explicitly loads full skill instructions into its dynamic prompt using `load_skill(name=...)` when needed, and unloads them with `unload_skill(name=...)` once the workflow is completed to conserve context tokens.
- **Cross-Phase Skill Retention**: Essential active skills (e.g. `artifacts`) can be designated for retention across thread boundaries and Plan Mode phase transitions (`discuss` -> `make` -> `execute`) via `retained_skills`, maintaining capability continuity while shedding exploratory skills.
- **Dynamic Tool Gating**: Tools declared in a skill's `allowed_tools` metadata are gated until the skill is loaded via `load_skill`.
- **Resilient Frontmatter Parsing**: Fault-tolerant parsing handles unquoted colons, JSON-like braces, folded multiline descriptions, and inline tool arrays without silently dropping real-world skills.
- **Multi-Tiered Precedence Engine (INV-035)**: Skills are resolved through an implementation-agnostic hierarchy where higher tiers override lower tiers on naming collisions:
  1. **Bundled Platform Skills** (`/skills/bundled`): Core harness capabilities built directly into Seamus (Highest Priority).
  2. **Visible Session Skills** (`/workspace/skills`): Git-tracked skills inside the session repository.
  3. **Background Session Skills** (`/workspace/.skills`): Hidden, Git-tracked project skills.
  4. **Auxiliary Project Skills** (`/projects/<repo>/skills` and `.skills`): External repository skills.
  5. **System-Wide Host Skills** (`/skills/system/{idx}`): Host directories configured via system settings (mounted read-only).
- **In-Sandbox Mounts**: All skills are mounted into the OpenSandbox container, enabling the agent to read instructions and execute companion scripts safely.

### 7. Enterprise Secrets Vault (OpenBao KV v2)

No more API keys leaked in git commits or environment logs:

- **OpenBao KV v2 Integration**: Native integration with OpenBao (the open-source, community-driven Vault fork) backed by PostgreSQL.
- **Symbolic Secret References**: Configurations use symbolic expressions rather than raw tokens:
  - `${secret('/api-key/inference/openrouter')}`
  - `${secret(path='/api-key/custom', field='token')}`
- **Zero Cleartext on Disk or in Git**: Secret references are resolved strictly in-memory during inference. Files written to disk or pushed to Gitea repositories never contain cleartext secrets.
- **Version-Pinned Exploded Snapshots**: To guarantee reproducible execution, checkpoint commits pin the exact active secret version at the time of execution:
  - `${secret(path='/api-key/inference/openrouter', field='value', version=3)}`
- **In-Browser Vault Management**: Web UI includes a dedicated Secrets tab with token reveal toggles, expression copy-to-clipboard, and live key/value authoring.

### 8. Developer Web UI & Workspace Ergonomics

A desktop-grade React 19 single-page application built with Vite and TypeScript:

- **1:2 Ergonomic Layout Resizer**: Split layout defaulting to 1:2 (`33.33%` navigation tree / `66.67%` main panel). Features boundary clamping, double-click instant 1:2 reset, and persistent local storage sizing.
- **URL State Synchronization**: Active agent, session, thread, and workspace tab are synchronized with browser URL query parameters (`?agent=...&session=...&thread=...&tab=...`), enabling browser back/forward history navigation and shareable deep links.
- **Real-Time SSE Streaming**: Live AG-UI event streaming with token-by-token text generation, expandable reasoning blocks, and lifecycle state badges.
- **Changes Diff Viewer**: Dedicated `[Changes]` tab with hierarchical directory tree navigation, flat list view, git status badges (`[A]` Added, `[M]` Modified, `[D]` Deleted, `[R]` Renamed), diff stats (`+N / -M`), and syntax-highlighted unified diffs.
- **Interactive Web Terminal & Shell Emulator**: Dedicated `[Terminal]` tab connected directly to the active session's OpenSandbox container. Features real-time Server-Sent Events (SSE) streaming output, command history navigation (`↑`/`↓`), quick action shortcuts, process interruption (Cancel / `Ctrl+C`), and dynamic working directory tracking across commands.
- **Granular Bidirectional Chat Branching & Tool Grouping**: Every chat bubble, reasoning block, tool execution, user message, and synthetic event features contextual "Branch Before" and "Branch After" action buttons oriented toward the center of the viewport (left of user bubbles, right of assistant/system bubbles):
  - *Vertical Layout & Header Pinning*: Branch buttons are arranged vertically at constant fixed size (matching the ~32px height of a collapsed bubble). When a bubble is expanded or multi-line, "Branch Before" sticks to the top of the bubble and "Branch After" sticks to the lower border of the bottom.
  - *Tool Grouping & Visual Brace*: When a single model inference results in multiple tool calls, they are grouped with a visual brace on the left. Individual calls size to fit their content, with "Branch Before" placed directly to the right of the first tool call and "Branch After" placed directly to the right of the last tool call. Branching before restarts all tool executions in the group; branching after keeps all tool results. Single-call inferences omit the brace to minimize visual clutter.
  - *Precise Provenance Indicators & Mode Continuity*: Branched sessions preserve the parent thread's operational mode and phase (`chat`, `plan/discuss`, `plan/make`, `plan/execute`). In child sessions, the "branched before/after" provenance line is placed directly relative to the branch point: above or below target user messages, synthetic events, bot messages, or reasoning blocks; and for tool calls or braced tool groups, running underneath the tool call bubble(s) at the vertical midpoint (or between them for an even number of calls) with the provenance pill to the right when branched before, or below the tool/group when branched after.
  - *Branch Before*:
    - **User Message / System Event**: Reverts the session state to prior to the message being sent, returning to `AWAITING_USER`.
    - **Bot Message / Thinking**: Truncates history prior to the generation and re-runs inference (`AWAITING_LLM`) to generate a fresh response or reasoning block.
    - **Tool Call / Group**: Slices the thread before tool execution (before `TOOL_CALL_RESULT`) and re-executes all tools in the group in the branched session.
  - *Branch After*:
    - **User Message / System Event**: Branches with the user prompt or synthetic event intact and initiates turn inference (`AWAITING_LLM`).
    - **Bot Message**: Retains the assistant text; if the turn finished without subsequent tools, transitions cleanly to `AWAITING_USER`, otherwise continues processing.
    - **Bot Thinking**: Retains reasoning tokens and continues inference (`AWAITING_LLM`).
    - **Tool Call / Group**: Preserves all existing tool execution results from the parent session and continues processing (`AWAITING_LLM`).
- **Chat Bubble Timestamps & Autonomous Sequence Indexing**: Per-bubble localized timestamps with seconds precision (`HH:MM:SS`) and ISO tooltips on hover. When an agent produces a contiguous streak exceeding 5 bubbles (`BUBBLE_SEQUENCE_THRESHOLD`), each bubble in the sequence displays a high-contrast 1-based index badge (`#1`, `#2`, ..., `#N`) at its top-left corner, providing instant visibility into autonomous multi-step execution duration and step-by-step progress.
- **Unmasked Symbolic Secret Expressions**: Configuration and settings modal input fields automatically unmask from password to readable text when containing symbolic `${secret(...)}` expressions, keeping secret paths clearly verifiable while preserving password masking for raw strings.
- **Right-Aligned System and Daemon Events**: Background system notifications, phase shifts, and daemon events are styled and right-aligned to clearly distinguish harness logs from user inputs and assistant dialogue.
- **Interactive Markdown Renderer**: GitHub Flavored Markdown (GFM) with one-click code block copying, responsive tables, and sanitized external links.
- **Dual-Mode Config Editor**: Edit agent and session configurations using either a guided form interface (with reasoning effort selection placed adjacent to the model identifier) or a raw JSON editor with client-side syntax validation.

### 9. DeepAgent Runtime Introspection & Inspector

Inspect exactly what the language model sees and executes via the UI `[Inspector]` tab:

- **Decomposed Composite Prompt Layers**: View the exact LM-XML system prompt generated for the active turn, split cleanly into Scaffolding, Dynamic Runtime Context (paths, IDs, dates), and Custom Instructions, with one-click copy.
- **Registered Tool Schemas & Semantic Label Badges**: Interactive accordion displaying formatted JSON Schema parameter definitions for every tool exposed to the agent, augmented by semantic colored badges (`opensandbox`, `harness`, `planning`, `web`, `skills`) loaded from `tool_labeling.json` with interactive category filtering.
- **Active Todos Checklist**: Real-time inspection of active task planning items managed by DeepAgents `TodoListMiddleware`.
- **Runtime Inference Parameters**: Model identifier, base URL, sampling parameters, and masked credential references.
- **Complete Message Trajectory**: Inspect raw message payloads, token counts, and tool call results.

### 10. Telemetry & Observability (Pydantic Logfire & OpenTelemetry)

Full distributed tracing and production observability:

- **Pydantic Logfire Tracing**: Integrated tracing capturing end-to-end latency, model generation metrics, tool call executions, and HTTP API requests.
- **OpenTelemetry Standard**: Native LangChain and LangGraph OTEL instrumentation (`LANGSMITH_OTEL_ENABLED=true`, `LANGSMITH_OTEL_ONLY=true`).
- **Privacy & Credential Scrubbing**: Custom sanitizers automatically redact API tokens, secrets, and authorization headers while preserving domain structure (e.g. whitelisting `session`).
- **One-Click External Links**: Navigation tree footer features pinned deep links to your Logfire project dashboard, Gitea server home, agent repository, and active session branch.

### 11. 1-Click Zero-Friction Stack Launch

Start the entire multi-service stack with a single command:

```bash
./run.sh
```

- **Automated Health Polling**: Checks UI, backend health endpoint (`/health`), and Gitea API health, polling until all containers are fully ready.
- **Auto-Provisioning**: Provisions default Gitea administrator (`seamus`) and initializes OpenBao database tables on first launch.
- **Automatic Browser Launch**: Opens `http://localhost:3000` automatically in your system's default browser (supporting Linux `xdg-open` / `sensible-browser`, macOS `open`, and Windows/WSL `powershell.exe`).

### 12. Local Model Inference & Active Ollama Lifecycle Management

Run agents completely offline without external cloud API dependencies or recurring subscription fees:

- **First-Class Ollama Provider**: Native `InferenceFormat.OLLAMA` support with optional API key validation and built-in model presets (`gemma4:e4b`, `llama3.2:3b`, `qwen3.8:latest`).
- **Containerized Ollama Service**: Out-of-the-box `ollama` container running `ollama/ollama:latest` in CPU mode with persistent model volume `ollama-data`.
- **Intelligent Candidate Probing**: Automatically attempts candidate endpoints (`base_url`, `http://ollama:11434`, `http://host.docker.internal:11434`) when localhost is configured, bridging container and host environments seamlessly.
- **Active Model Verification & Pre-Loading**: Dispatches healthchecks and pre-loads the model into memory (`POST /api/generate`) before agent execution starts.
- **Automated Model Pulling**: When the target model is not present, automatically triggers Ollama's model pull API (`POST /api/pull` with `stream: False`) and retries the load, providing zero-configuration setup for local models.

### 13. Non-Agentic Daemons & Automated Naming

Lightweight, non-agentic one-shot LLM utilities using plain `Instructions: ... Input: ... Output:` prefill prompts on fast, cheap, or local models:

- **Automated Thread & Session Naming**: Automatically generates descriptive, URL-safe slugs for threads and sessions from conversational exchanges and constituent thread topics.
- **Deterministic Agent Naming**: Automatically generates URL-safe agent slugs upon creation using `coolname` (e.g. `sticky-grinning-skua-of-camouflage`), following the same parallel slug fallback rules as threads and sessions.
- **Geometric Stepback Scheduling**: Triggers daemon runs on full completed user/assistant exchanges at doubling intervals ($N = 2^k - 1$: $1, 3, 7, 15, \dots$), balancing fresh naming with low token consumption.
- **Parallel Slug Model**: User-assigned custom names take precedence over daemon-generated slugs while auto-naming continues running in the background, providing instantaneous fallback if the user clears their custom slug.
- **Defensive Preemptive Output Parsing**: Resiliently cleans markdown code fences, triple quotes, blockquotes, and conversational prefixes from small or local model outputs into valid slug strings.

---

## Every Goddamn Flag (Exhaustive Configuration & Reference Manual)

### CLI Flags & Scripts (`run.sh`)

The `./run.sh` script is the primary entrypoint for managing the Seamus containerized stack.

```bash
./run.sh [OPTIONS]
```

| Flag | Short | Default | Description |
| :--- | :---: | :---: | :--- |
| `--help` | `-h` | - | Displays usage instructions, available flags, and exits immediately. |
| `--restart` | `-r` | `false` | Rebuilds and recreates only application containers owned by Seamus (`backend`, `frontend`, `opensandbox`) via `docker compose up -d --build opensandbox backend frontend`. Preserves all persistent database volumes (`gitea-data`, `postgres-data`, `openbao-auth`). |
| `--clean` | `-c` | `false` | **Full stack reset.** Stops all containers, wipes Docker volumes (`seamus-workspaces`, `gitea-data`, `opensandbox-data`, `opensandbox-auth`), drops PostgreSQL tables (except OpenBao secrets vault tables `vault_kv_store` and `vault_ha_locks`), removes local workspace clones (`.seamus/workspaces`), and rebuilds everything from scratch. |
| *(None)* | - | - | **Default behavior.** Checks if services are running; if already healthy, immediately launches your browser; if not running or degraded, starts all containers via `docker compose up -d --build`, waits for health checks, provisions the default Gitea admin user, and opens the UI. |

#### Script Environment Variable Overrides

| Environment Variable | Default Value | Description |
| :--- | :--- | :--- |
| `COMPOSE_ENV_FILES` | `/dev/null` | Prevents Docker Compose from attempting shell variable interpolation on `${secret(...)}` expressions in `.env`. |
| `COMPOSE_PROJECT_NAME` | Directory name | Controls Docker Compose project name for container and volume naming prefixes. |
| `TIMEOUT_SECONDS` | `60` | Maximum time in seconds to poll service health before failing with a timeout error. |
| `POSTGRES_USER` | `gitea` | Database user for clean-reset PostgreSQL drop-table commands. |
| `POSTGRES_DB` | `gitea` | Database name for clean-reset PostgreSQL drop-table commands. |
| `SEAMUS_WORKSPACE_DIR` | `.seamus/workspaces` | Directory path wiped during a clean reset. |

---

### Complete Environment Variables Reference

Seamus reads environment variables from the host environment and your local `.env` file (copied from `.env.template`).

#### 1. Server Network & Core Settings

| Variable | Type | Default | Description |
| :--- | :---: | :--- | :--- |
| `HOST` | `string` | `0.0.0.0` | Bind IP address for the FastAPI backend application server. |
| `PORT` | `integer` | `8000` | Port for the FastAPI backend application server. |

#### 2. Model Inference & Runtime Configuration

| Variable | Type | Default | Description |
| :--- | :---: | :--- | :--- |
| `OPENROUTER_API_KEY` | `string` | `${secret('/api-key/inference/openrouter')}` | Primary API key for model inference. Can be a raw key or a symbolic OpenBao secret reference. |
| `OPEN_ROUTER_API_KEY` | `string` | `""` | Alternative fallback variable name for `OPENROUTER_API_KEY`. |
| `OPENROUTER_BASE_URL` | `string` | `https://openrouter.ai/api/v1` | Base URL for OpenAI-compatible inference endpoints. |
| `OPENROUTER_MODEL` | `string` | `openai/gpt-oss-120b` | Default model identifier passed to inference providers. |
| `MODEL_NAME` | `string` | `""` | Alternative fallback variable name for `OPENROUTER_MODEL`. |
| `DEFAULT_MODE` | `string` | `plan` | Default operational mode for new agents and sessions (`chat` or `plan`). |
| `SEAMUS_MODE` | `string` | `""` | Alternative fallback variable name for `DEFAULT_MODE`. |
| `SEAMUS_THREAD_MESSAGE_OVERLAP` | `integer` | `5` | Number of previous thread messages copied into a newly spawned thread for conversational continuity. |
| `SEAMUS_RECURSION_LIMIT` | `integer` | `250` | Maximum recursion / turn limit for LangGraph execution loops before raising a recursion exception. |

#### 3. OpenBao Secrets Vault

| Variable | Type | Default | Description |
| :--- | :---: | :--- | :--- |
| `OPENBAO_URL` | `string` | `http://localhost:8200` | Internal API URL for the OpenBao server (inside Docker: `http://openbao:8200`). |
| `OPENBAO_EXTERNAL_URL` | `string` | `http://localhost:8200` | External URL used by browsers to access the OpenBao Web UI. |
| `OPENBAO_TOKEN` | `string` | `""` | Static root or service authentication token for OpenBao. If empty, loaded from token file. |
| `OPENBAO_TOKEN_FILE` | `string` | `""` | Filesystem path to file containing OpenBao token (inside Docker: `/var/run/seamus-openbao/root_token`). |
| `OPENBAO_MOUNT` | `string` | `secret` | OpenBao KV v2 mount path where secrets are stored. |

#### 4. Git Persistence (Gitea & PostgreSQL)

| Variable | Type | Default | Description |
| :--- | :---: | :--- | :--- |
| `GITEA_URL` | `string` | `http://localhost:3001` | Internal API endpoint for Gitea (inside Docker container network: `http://gitea:3000`). |
| `GITEA_EXTERNAL_URL` | `string` | `http://localhost:3001` | External URL used by web browsers and UI deep links to access Gitea. |
| `GITEA_ADMIN_USER` | `string` | `seamus` | Administrator and service account username on Gitea. |
| `GITEA_ADMIN_PASSWORD` | `string` | `seamus-password-123` | Administrator and service account password on Gitea. |
| `GITEA_ADMIN_EMAIL` | `string` | `seamus@seamus.local` | Email address registered for Gitea administrator user. |
| `GITEA_SECRET_KEY` | `string` | `seamus-gitea-secret-key-12345` | Internal cryptographic secret key for Gitea server. |
| `POSTGRES_DB` | `string` | `gitea` | PostgreSQL database name backing Gitea and OpenBao tables. |
| `POSTGRES_USER` | `string` | `gitea` | PostgreSQL database user. |
| `POSTGRES_PASSWORD` | `string` | `gitea` | PostgreSQL database password. |
| `SEAMUS_WORKSPACE_DIR` | `string` | `.seamus/workspaces` | Host filesystem directory where local session workspace clones are stored (in Docker: `/app/workspaces`). |
| `SEAMUS_PERSISTENCE_ENABLED` | `boolean` | `true` | Enables or disables Git-backed workspace persistence and checkpoint saving. |

#### 5. OpenSandbox Container Execution

| Variable | Type | Default | Description |
| :--- | :---: | :--- | :--- |
| `OPENSANDBOX_DOMAIN` | `string` | `localhost:8080` | Hostname and port for the OpenSandbox lifecycle management server (in Docker: `opensandbox:8080`). |
| `OPENSANDBOX_PROTOCOL` | `string` | `http` | HTTP protocol scheme for OpenSandbox (`http` or `https`). |
| `OPENSANDBOX_IMAGE` | `string` | `seamus-sandbox:latest` | Default base container image instantiated for agent session execution sandboxes (Ubuntu 24.04 with Python 3, Astral `uv`, Node.js, npm, Git, and build essentials; overridable per agent/session via `sandbox_image`). |
| `OPENSANDBOX_WORKDIR` | `string` | `/workspace` | Target mount point inside the sandbox container for Git-tracked session data deliverables. |
| `OPENSANDBOX_TIMEOUT` | `integer` | `300` | Default execution timeout in seconds for individual shell commands and tool calls. |
| `OPENSANDBOX_SANDBOX_TIMEOUT` | `integer` | `3600` | Inactivity TTL in seconds before an idle sandbox container is automatically destroyed. |
| `OPENSANDBOX_WORKSPACE_VOLUME` | `string` | `""` | Named Docker volume backing `/workspace` when running backend inside Docker (`seamus-workspaces`). |
| `OPENSANDBOX_USE_SERVER_PROXY` | `boolean` | `true` | Proxies command executions through the OpenSandbox server lifecycle daemon. |
| `SEAMUS_OPENSANDBOX_KEY_FILE` | `string` | `.seamus/opensandbox/api_key` | Path to shared runtime authentication key file generated by OpenSandbox. |
| `OPENSANDBOX_SERVER_API_KEY` | `string` | `""` | Direct override for OpenSandbox server API key. |

#### 6. Observability, Telemetry & OpenTelemetry

| Variable | Type | Default | Description |
| :--- | :---: | :--- | :--- |
| `LOGFIRE_TOKEN` | `string` | `""` | Authentication token for Pydantic Logfire cloud dashboard. If unset, operates safely in local mode. |
| `LOGFIRE_SERVICE_NAME` | `string` | `seamus` | Service identifier reported in Logfire traces and span trees. |
| `LOGFIRE_ORG` | `string` | `""` | Logfire organization slug used for generating direct UI dashboard deep links. |
| `LOGFIRE_BASE_URL` | `string` | `https://logfire-eu.pydantic.dev` | Logfire cloud platform base ingestion URL. |
| `LOGFIRE_SEND_TO_LOGFIRE` | `string` | `if-token-present` | Telemetry transmission mode: `if-token-present`, `true`, or `false`. |
| `LOGFIRE_ENVIRONMENT` | `string` | `development` | Deployment environment tag attached to traces (e.g. `development`, `staging`, `production`). |
| `LANGSMITH_OTEL_ENABLED` | `boolean` | `true` | Enables OpenTelemetry-compatible tracing within LangChain and LangGraph. |
| `LANGSMITH_OTEL_ONLY` | `boolean` | `true` | Restricts LangChain tracing strictly to OpenTelemetry exporters without third-party vendor calls. |
| `LANGSMITH_TRACING` | `boolean` | `true` | Activates LangChain tracer hooks globally. |

#### 7. Skills & Filesystem Integration

| Variable | Type | Default | Description |
| :--- | :---: | :--- | :--- |
| `SEAMUS_HOST_HOME` | `string` | `$HOME` | Host machine user home directory path passed to Docker containers for resolving `~` paths. |
| `HOST_HOME` | `string` | `""` | Alternative fallback variable for `SEAMUS_HOST_HOME`. |

---

### Agent & Inference Configuration Schema (`AgentConfig` & `InferenceConfig`)

The core configuration models defined in `seamus.config.models`:

```python
class InferenceConfig(BaseModel):
    format: InferenceFormat = InferenceFormat.OPENAI
    base_url: str = "https://openrouter.ai/api/v1"
    api_key: str | None = None
    reasoning_effort: ReasoningEffort = ReasoningEffort.DEFAULT


class ExternalRepositoryConfig(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    url: str
    branch: str = "main"
    credentials_ref: str | None = None


class AgentConfig(BaseModel):
    inference: InferenceConfig = Field(default_factory=InferenceConfig)
    model_name: str = "openai/gpt-oss-120b"
    mode: str = OperationalMode.PLAN.value
    system_prompt: str | None = None
    todo_implementation: TodoImplementation = TodoImplementation.SEAMUS
    skills_implementation: SkillsImplementation = SkillsImplementation.SEAMUS
    web_search: WebSearchImplementation = WebSearchImplementation.DUCKDUCKGO
    thread_message_overlap: int = 5
    repositories: list[ExternalRepositoryConfig] = Field(default_factory=list)
    rules_patterns: list[str] = Field(default_factory=lambda: ["AGENTS.md", ".seamus/rules/**"])
    sandbox_image: str | None = None
    daemons: DaemonsConfig = Field(default_factory=DaemonsConfig)
```

#### Field Details

- `inference.format`: Format of inference API (`openai` or `ollama`).
- `inference.base_url`: Target endpoint URL for inference API requests (presets: OpenRouter, OpenAI, and local Ollama `http://localhost:11434/v1`).
- `inference.api_key`: API key or symbolic vault reference (`${secret('/path')}`). Optional when using Ollama (`ollama` format or port `11434`).
- `inference.reasoning_effort`: Reasoning token tier for reasoning models (`default`, `none`, `minimal`, `low`, `medium`, `high`, `xhigh`). `"default"` leaves provider parameters untouched.
- `rules_patterns`: Glob patterns evaluated per inference turn across `/workspace` and mounted `/projects/...`, injecting matching context files into `<discovered_context>`.
- `repositories`: List of external Git repositories mounted into `/projects/{mount_name}`.
- `daemons.naming.enabled`: Enables automated thread and session naming daemons (default: `true`).
- `daemons.naming.provider`: Optional provider configuration for naming daemons; if unset, inherits the agent's main `inference` settings.
- `daemons.naming.model`: Dedicated model identifier for naming daemons (default: `openai/gpt-oss-20b`), keeping naming costs and latency minimal.
- `model_name`: Provider model identifier (e.g. `anthropic/claude-3.5-sonnet`, `openai/gpt-4o`, `openai/gpt-oss-120b`, `llama3.2:3b`, `qwen3.8:latest`, `gemma4:e4b`). When targeting Ollama, Seamus actively verifies daemon health and loads the requested model into memory prior to execution.
- `mode`: Initial operational mode for sessions (`chat` or `plan`).
- `system_prompt`: Optional custom prompt instructions appended to the dynamic LM-XML scaffold.
- `todo_implementation`: Task list planning middleware (`seamus` [default], `deepagents`, or `none`).
- `skills_implementation`: Skills discovery and disclosure implementation (`seamus` [default], `deepagents`, or `none`).
- `web_search`: Web search and page extraction implementation (`duckduckgo` [default] or `none`). Powered by DuckDuckGo with zero API keys or external credentials required.
- `thread_message_overlap`: Number of prior thread messages retained when branching or switching modes (default: `5`).

---

### System Settings Schema (`SystemSettings`)

System-wide settings defined in `seamus.config.settings`, persisted to the `system` repository in Gitea:

```python
class SystemSettings(BaseModel):
    skill_directories: list[str] = Field(default_factory=lambda: ["~/.seamus/skills", "~/.skills"])
```

- `skill_directories`: Host directories containing system-wide Anthropic skills, mounted read-only into OpenSandbox containers at `/skills/system/{idx}`. Supports `~` and environment expansion.

---

### Docker Compose Topology, Ports & Volumes

The production stack orchestrated by `docker-compose.yml`:

| Service Name | Base Image / Build Context | Exposed Ports | Primary Responsibility |
| :--- | :--- | :---: | :--- |
| `postgres` | `postgres:16-alpine` | `5432` (internal) | PostgreSQL database storage backing Gitea and OpenBao tables. |
| `gitea` | `gitea/gitea:latest` | `3001:3000` | Git repository server, commit log, audit history, and Sync PR engine. |
| `gitea-init` | `gitea/gitea:latest` | None | One-shot initialization script ensuring default `seamus` admin user exists. |
| `openbao-db-init` | `postgres:16-alpine` | None | Provisions PostgreSQL tables (`vault_kv_store`, `vault_ha_locks`) for OpenBao. |
| `openbao` | `openbao/openbao:latest` | `8200:8200` | OpenBao KV v2 secrets vault daemon. |
| `openbao-init` | `openbao/openbao:latest` | None | Initializes OpenBao, configures KV v2 mount at `secret/`, and outputs root token. |
| `opensandbox` | `./opensandbox` (Dockerfile) | `8080` (internal) | Docker-in-Docker sandboxing engine managing isolated execution containers. |
| `backend` | `.` (Dockerfile) | `8000:8000` | FastAPI server, DeepAgent runtime, Git workspace manager, and SSE streams. |
| `frontend` | `./ui` (Dockerfile) | `3000:3000` | React 19 SPA served via Nginx reverse-proxy with SSE buffering disabled. |
| `ollama` | `ollama/ollama:latest` | `11434` (internal) | Local model inference provider running in CPU mode. |

#### Persistent Volumes

- `postgres-data`: Persists PostgreSQL database files.
- `gitea-data`: Persists Gitea configuration, repositories, and Git objects.
- `seamus-workspaces`: Shared volume between backend and OpenSandbox mounting session workspaces.
- `opensandbox-data`: Persists runtime container images and Docker storage for sandboxes.
- `opensandbox-auth`: Shared auth token file between OpenSandbox daemon and backend.
- `openbao-auth`: Shared root token directory between OpenBao init and backend.
- `ollama-data`: Persists downloaded Ollama local models across stack restarts.

---

### Sandbox Filesystem Mount Paths

Inside every OpenSandbox execution container, the filesystem is structured as follows:

| Container Path | Host / Session Source | Permissions | Purpose |
| :--- | :--- | :---: | :--- |
| `/workspace` | `<session_workspace>/data/` | **Read-Write** (or **Read-Only** in `plan/make`) | Agent code deliverables and Git-tracked workspace files. |
| `/projects/{name}` | `<session_workspace>/projects/{name}/` | **Read-Write** | Mounted external Git repositories with normal `.git/` working tree. |
| `/artifacts` | `<session_workspace>/artifacts/` | **Read-Only** (`readOnly=True`) | Persisted A2UI artifacts, questionnaires, and implementation plans. |
| `/skills/bundled` | Shared Volume (`seamus/skills/bundled/`) | **Read-Only** (`readOnly=True`) | Core platform skills provided by Seamus harness. |
| `/skills/system/{idx}` | Configured Host Directory (`~/.skills`, etc.) | **Read-Only** (`readOnly=True`) | System-wide external skills mounted from developer host. |

---

### Harness Tools Palette & Lifecycle Transitions

Harness tools are exposed dynamically based on the active operational mode and plan phase:

| Tool Name | Available In | Description |
| :--- | :--- | :--- |
| `make_artifact` | `chat`, `plan/discuss` | Low-level builder creating raw A2UI artifacts with custom component trees. |
| `make_questionnaire` | `chat`, `plan/discuss` | High-level atomic builder generating inline blocking questionnaires with chip/radio options. |
| `make_form` | `plan/discuss` | High-level atomic builder generating tabbed non-blocking input forms. |
| `make_plan` | `plan/make` (initial) | High-level atomic builder creating the session's Markdown implementation plan artifact. |
| `update_plan` | `plan/make` (revision) | Replaces the full Markdown content of an existing plan artifact. |
| `edit_plan` | `plan/make` (patch) | Performs targeted string replacement patches on an existing plan artifact. |
| `wait_for_click` | Whenever artifact tools are active | Explicitly suspends agent execution until the user clicks an artifact button or submits input. |
| `plan` | `plan/discuss` | Lifecycle transition tool advancing session from `plan/discuss` to `plan/make`. |
| `discard` | `plan/discuss`, `plan/make`, `plan/execute` | Aborts the active plan workflow and cleans up plan artifacts. |
| `write_todos` | All (when `todo_implementation="deepagents"`) | Manages the agent's task planning checklist items. |
| `create_todo_item` | All (when `todo_implementation="seamus"`) | Creates a new task or subtask item in the active plan. |
| `edit_todo_item` | All (when `todo_implementation="seamus"`) | Updates content/status or moves an existing task item (reparenting, reordering). |
| `delete_todo_item` | All (when `todo_implementation="seamus"`) | Deletes a task item and all of its subtasks. |
| `web_search` | All (when `web_search="duckduckgo"`) | Queries DuckDuckGo for top web results, returning titles, links, and snippets. |
| `fetch_web_page` | All (when `web_search="duckduckgo"`) | Fetches page content and extracts readable Markdown via DuckDuckGo extraction. |

---

### REST API Endpoints Reference (`/api/v-alpha/`)

The backend exposes a clean, typed REST API under prefix `/api/v-alpha/`:

#### Health & System

- `GET /health`: Health check endpoint verifying backend server status.
- `GET /api/v-alpha/system/info`: Returns external companion integration status (Logfire and Gitea URLs, organization names, and connection availability).
- `GET /api/v-alpha/settings`: Retrieves global `SystemSettings` (e.g. system skill directories).
- `PUT /api/v-alpha/settings`: Updates global `SystemSettings` and persists to Gitea `system` repository.
- `GET /api/v-alpha/config/template`: Retrieves the singleton service-wide `AgentConfig` template.
- `PUT /api/v-alpha/config/template`: Updates the service-wide `AgentConfig` template.

#### Agents

- `GET /api/v-alpha/agents`: Lists all agents discovered in Gitea.
- `POST /api/v-alpha/agents`: Creates a new agent with optional custom configuration and initial slug.
- `GET /api/v-alpha/agents/{agent_id}`: Retrieves specific agent details and configuration.
- `PATCH /api/v-alpha/agents/{agent_id}`: Updates agent configuration or display slug.
- `DELETE /api/v-alpha/agents/{agent_id}`: Deletes agent, removing all sessions and Gitea repositories.

#### Sessions

- `GET /api/v-alpha/agents/{agent_id}/sessions`: Lists all sessions belonging to an agent.
- `POST /api/v-alpha/agents/{agent_id}/sessions`: Spawns a new session with an isolated Git branch.
- `GET /api/v-alpha/agents/{agent_id}/sessions/{session_id}`: Retrieves session details, status, and config.
- `PATCH /api/v-alpha/agents/{agent_id}/sessions/{session_id}`: Updates session config, status, or slug.
- `DELETE /api/v-alpha/agents/{agent_id}/sessions/{session_id}`: Terminates session and cleans up containers.
- `GET /api/v-alpha/agents/{agent_id}/sessions/{session_id}/diff`: Returns live unified git diff of `data/` deliverables.
- `GET /api/v-alpha/agents/{agent_id}/sessions/{session_id}/inspect`: Surfaces complete Agent Inspector runtime manifest.
- `GET /api/v-alpha/agents/{agent_id}/sessions/{session_id}/stream`: Session-level SSE feed streaming unified multi-thread events.
- `POST /api/v-alpha/agents/{agent_id}/sessions/{session_id}/terminal/stream`: Streams shell command execution inside the session's sandbox container via SSE.
- `GET /api/v-alpha/agents/{agent_id}/sessions/{session_id}/terminal/info`: Returns active sandbox terminal status and operational directory.
- `POST /api/v-alpha/agents/{agent_id}/sessions/{session_id}/branch`: Branches a new child session from an arbitrary historical item (`target_id`, `position: "before" | "after"`, optional `item_type`), with full backward-compatibility for legacy turn branching (`message_id`, `retry_inference`).

#### Threads

- `GET /api/v-alpha/agents/{agent_id}/sessions/{session_id}/threads`: Lists all threads in a session.
- `POST /api/v-alpha/agents/{agent_id}/sessions/{session_id}/threads`: Spawns a fresh thread in a specific mode/phase.
- `GET /api/v-alpha/agents/{agent_id}/sessions/{session_id}/threads/{thread_id}`: Retrieves thread details and message history.
- `POST /api/v-alpha/agents/{agent_id}/sessions/{session_id}/threads/{thread_id}/input`: Dispatches user prompt turn to active thread.
- `POST /api/v-alpha/agents/{agent_id}/sessions/{session_id}/threads/{thread_id}/accept`: Executes human-in-the-loop thread acceptance (merges Sync PR to `main`).
- `GET /api/v-alpha/agents/{agent_id}/sessions/{session_id}/threads/{thread_id}/stream`: Thread-level SSE stream for real-time AG-UI events.

#### Artifacts

- `GET /api/v-alpha/agents/{agent_id}/sessions/{session_id}/artifacts`: Lists all artifacts in the session.
- `GET /api/v-alpha/agents/{agent_id}/sessions/{session_id}/artifacts/{family}/{uuid}`: Retrieves artifact manifest, body, and state.
- `POST /api/v-alpha/agents/{agent_id}/sessions/{session_id}/artifacts/{family}/{uuid}/click`: Dispatches button click event with accumulated form context.
- `POST /api/v-alpha/agents/{agent_id}/sessions/{session_id}/artifacts/{family}/{uuid}/submit`: Submits input responses for an artifact.
- `POST /api/v-alpha/agents/{agent_id}/sessions/{session_id}/artifacts/{family}/{uuid}/proceed`: Authorizes an implementation plan, advancing session from `plan/make` to `plan/execute`.
- `POST /api/v-alpha/agents/{agent_id}/sessions/{session_id}/artifacts/{family}/{uuid}/comments`: Records section-level inline review comments on a plan artifact.

#### Secrets Vault

- `GET /api/v-alpha/vault/secrets`: Lists all secret paths stored in OpenBao KV v2 vault.
- `POST /api/v-alpha/vault/secrets`: Writes or updates secret key/value pairs at a designated path.
- `GET /api/v-alpha/vault/token`: Returns the active OpenBao client token for authorized UI operations.
