# Backlog

Persistent record of work intentionally left outstanding across the project, maintained in accordance with [AGENTS.md](../AGENTS.md).

## Deferred

### Granular Gitea Commit Authors, Organizations, and Team Ownership
- **Description**: All Git repositories created in Gitea are owned by the system service user `seamus`, and automated commits use the single author identity `Seamus Agent <agent@seamus.local>`. Per-agent, per-session, or per-user commit authors, organizations, and team permissions were postponed.
- **Why Deferred**: Kept persistence initialization and API interaction simple and single-tenant for early development.
- **Revisit Trigger**: When introducing multi-tenant support, team access controls, or distinct audit identities per agent or human turn.
- **Provenance**: [0008-git-persistence.md](../decisions/0008-git-persistence.md#8-deferred-tasks), [vocabulary.md](./vocabulary.md#agent-repository).

### Mounting Custom User-Provided Git Repositories
- **Description**: Seamus currently manages its own internal Gitea repositories per agent (`agent-{agent_id}`). Mounting or connecting existing external Git repositories (e.g., GitHub, GitLab, or preexisting host Git repos) was postponed.
- **Why Deferred**: Prioritized establishing the internal repository layout (`main`, `session/{session_id}`, `agent/state/`, `data/`) and verification mechanisms before supporting external remote topologies.
- **Revisit Trigger**: When users require agents to work directly on existing external codebases without manual file copying or importing.
- **Provenance**: [0008-git-persistence.md](../decisions/0008-git-persistence.md#8-deferred-tasks).

### Resource Archiving and Soft Deletion in API
- **Description**: The REST API prohibits `DELETE` operations across all resources to ensure non-destructive safety (`INV-007`). Archiving or soft deletion (hiding inactive agents, sessions, or threads from the active navigation views) was postponed.
- **Why Deferred**: Prioritized zero accidental data loss and predictable append-only state for early iterations.
- **Revisit Trigger**: When navigation views become cluttered by inactive entities and users need to hide or archive old sessions without deleting underlying Git histories.
- **Provenance**: [0002-harness-server-mvp.md](../decisions/0002-harness-server-mvp.md#resource-deletion-policy), [INV-007](./invariants.md#inv-007-no-resource-deletion-invariant), [REQ-007](./requirements.md#req-007-safe-non-destructive-api-surface).

### Alternative Git-Base Iconography for Sidebar Branch Navigation
- **Description**: The navigation sidebar footer uses composite buttons with an entity base icon (`Bot` or `MessageSquare`) badged with a mini `GitBranch` icon (Option A). An alternative layout with a Git base icon badged with an entity icon (Option B) was evaluated and postponed.
- **Why Deferred**: Option A provided clearer visual alignment with the selected entity context, but Option B remains a viable alternative if the badge hierarchy needs adjustment.
- **Revisit Trigger**: Revisit during future sidebar UI/UX design reviews if users report ambiguity with the current branch buttons.
- **Provenance**: [0008-git-persistence.md](../decisions/0008-git-persistence.md#6-web-ui-session-configuration-editing--external-gitea-links-ui).

### Historical Time-Travel in Agent Inspector
- **Description**: The Agent Inspector provides semi-live inspection reflecting the agent state as of the latest inference run. Historical time-travel inspection (inspecting the agent's prompts, tool schemas, and checkpoint state at an arbitrary past point in time or specific historical commit/checkpoint) was postponed.
- **Why Deferred**: Inspecting the latest inference state provides immediate observability for debugging current agent behavior. Historical time-travel is a low-priority nicety rather than an essential power feature for the initial inspector release.
- **Revisit Trigger**: When users require step-by-step historical regression debugging or auditing past tool configurations across lengthy agent trajectories.
- **Provenance**: [0011-agent-inspector.md](../decisions/0011-agent-inspector.md).

### Merge Rules on Gitea Sync PRs
- **Description**: Sync PRs from `session/{session_id}` to `main` are automatically created, approved, and merged upon user acceptance without enforced branch protection rules, required review approvals, or automated CI/CD status check validations.
- **Why Deferred**: Kept initial Sync PR synchronization and thread acceptance responsive and single-operator-friendly without blocking on multi-user review workflows or external CI runner infrastructure.
- **Revisit Trigger**: When multi-operator review requirements, automated compliance checks, or CI-based test gating are introduced for agent repository merges.
- **Provenance**: [0012-sync-prs-and-thread-accept.md](../decisions/0012-sync-prs-and-thread-accept.md), [vocabulary.md](./vocabulary.md#sync-pr).

## Technical debt

### Hardcoded Logfire Cloud Region and Organization in System Info Route
- **Current Problem**: In `src/seamus/server/routes/system.py`, the Logfire dashboard link is constructed with a hardcoded URL: `https://logfire-eu.pydantic.dev/filip-malczak/{service_name}`. This couples the service to a single cloud region and specific user account.
- **Improvement**: Parameterize the Logfire organization and cloud endpoint via environment variables (e.g. `LOGFIRE_ORG` and `LOGFIRE_BASE_URL` in `seamus.telemetry` and `.env.template`) so dashboard links adapt to arbitrary deployments.
- **Provenance**: [0006-external-system-links.md](../decisions/0006-external-system-links.md), [INV-015](./invariants.md#inv-015-external-system-link-visibility--telemetry-guard).

### Synchronous Git Subprocess Invocations in Async Server Flows
- **Current Problem**: `GitWorkspaceManager._run_git` calls `subprocess.run(["git", ...])` synchronously. During HTTP requests (`create_agent`, `commit_agent_config`, `commit_session_config`) and checkpoint serialization (`GitCheckpointSaver`), disk I/O and remote Git pushes to Gitea block the asyncio event loop thread.
- **Improvement**: Offload Git commands to a thread pool via `asyncio.to_thread` or switch to an asynchronous subprocess runner (`asyncio.create_subprocess_exec`) to avoid blocking the server event loop during Git operations.
- **Provenance**: [0008-git-persistence.md](../decisions/0008-git-persistence.md), [architecture.md](./architecture.md#component-boundaries).

### In-Memory Store State Isolation Across Multiple Server Workers
- **Current Problem**: `HarnessStore` maintains an in-memory dictionary of agents and sessions hydrated from Gitea only at startup. Running multiple server worker processes or replicas leads to desynchronized state, as mutations in one worker process are not reflected in the memory of another.
- **Improvement**: Introduce cross-worker synchronization or transition `HarnessStore` to a read-through/write-through cache against Gitea/a persistent backing store for multi-worker deployments.
- **Provenance**: [0002-harness-server-mvp.md](../decisions/0002-harness-server-mvp.md), [0008-git-persistence.md](../decisions/0008-git-persistence.md), [architecture.md](./architecture.md#system-overview).

### Prevent Logfire Scrubbing System Prompts Due to False-Positive 'auth' Match
- **Current Problem**: In Logfire telemetry spans, system prompt attributes are completely redacted with `[Scrubbed due to 'auth']`. Logfire's built-in credential regex `auth(?!ors?\b)` matches occurrences of `"authoring"` in `build_engineering_discipline()` and redacts the entire prompt.
- **Improvement**: 
  1. Update `_scrub_callback` in `src/seamus/telemetry.py` to preserve system prompt attributes and exempt false-positive substrings (such as `"authoring"`).
  2. Adjust phrasing in `build_engineering_discipline()` from `"before authoring code"` to `"before writing code"` as defensive double protection.
- **Provenance**: `src/seamus/telemetry.py`, `src/seamus/harness/prompt.py`, [0006-external-system-links.md](../decisions/0006-external-system-links.md).

## TODO

### Dual CI/CD Test Pipeline Runners (Docker-Enabled and In-Memory)
- **Description**: When configuring GitHub Actions / CI/CD pipelines, configure two distinct runner jobs: a Docker-enabled runner executing the full test suite with the ephemeral Gitea container fixture, and a fast in-memory runner executing pure unit tests.
- **Rationale**: Guarantees fast feedback for in-memory unit tests while preserving comprehensive Gitea persistence verification on Docker-capable runners.
- **Provenance**: [0017-dedicated-test-gitea.md](../decisions/0017-dedicated-test-gitea.md), [conventions.md](./conventions.md#testing-conventions).

### Operational Execution Modes and Thread Transition Triggers (plan, chat, act, analyse)
- **Description**: Support configurable execution modes that govern agent interaction style, prompt framing, workspace usage, and thread-spawning triggers:
  1. `plan`: Generates a structured execution plan before implementing changes. Spawns a new thread when formulating a plan, and automatically opens another new thread when transitioning from plan alignment to execution.
  2. `chat`: Conversational orientation; the workspace serves primarily as an agent scratchpad rather than the focus of production file changes.
  3. `act`: Direct task execution; executes user commands and edits promptly without upfront planning cycles.
  4. `analyse`: Read-only workspace investigation; answers questions and analyzes code without modifying persistent files.
  Switching between operational modes always closes the current thread and opens a fresh thread.
- **Rationale**: Aligns agent behavior with specific user intents while using threads as deterministic boundaries between planning, discussion, analysis, and execution.
- **Provenance**: [0019-threads-modes-personas-architecture.md](../decisions/0019-threads-modes-personas-architecture.md), [threads_modes_personas.md](./threads_modes_personas.md), [REQ-025](./requirements.md#req-025-operational-modes-and-thread-transition-triggers), [INV-029](./invariants.md#inv-029-mode-transition-thread-spawning-boundary).

### Pluggable Agent Personas (Coder, Office Worker, Designer, etc.)
- **Description**: Support configurable agent personas (e.g., `Coder`, `Office Worker`, `Designer`, `Data Scientist`) during agent creation. Each persona configures baseline `<identity>`, domain instructions, and specialized tool suites/backends.
- **Rationale**: Expands Seamus from a purely code-focused assistant into a versatile multi-domain autonomous harness.
- **Provenance**: [0019-threads-modes-personas-architecture.md](../decisions/0019-threads-modes-personas-architecture.md), [threads_modes_personas.md](./threads_modes_personas.md), [REQ-024](./requirements.md#req-024-agent-personas-and-baseline-archetypes), [INV-028](./invariants.md#inv-028-persona-immutability-and-inheritance).

### Subagent Architecture: Prompts, Sandbox Isolation, and UI Representation
- **Description**: Investigate and define Seamus subagent integration using DeepAgents subagents (`SubAgentMiddleware` / `AsyncSubAgent`). Specifically determine:
  1. System prompt composition: whether subagents inherit parent workspace rules and engineering discipline or use specialized task prompts.
  2. Execution isolation: whether subagents operate in the parent session's container workspace or spin up isolated workspace subtrees/ephemeral containers.
  3. UI visualization: design how delegated subagent runs, parallel executions, and returns are rendered in the SPA (e.g., collapsible child execution cards within the chat bubble or dedicated sub-threads).
- **Rationale**: Delegation to specialized subagents is central to autonomous harness scaling; clear execution boundaries and user visibility must be established before enabling subagents.
- **Provenance**: `src/seamus/harness/runner.py`, `deepagents.middleware.subagents`, [abstractions.md](./abstractions.md).

### Integrate Task Planning and Todo List Tool (TodoListMiddleware / write_todos)
- **Description**: Integrate `TodoListMiddleware` from `langchain.agents.middleware` into `create_deep_agent` in `seamus.harness.runner`. Expose the `write_todos` tool to Seamus agents, verify `PlanningState` compatibility with `GitCheckpointSaver`, and expose the active todo checklist to the frontend.
- **Rationale**: Equips agents with structured multi-step planning and tracking tools (`write_todos`), and provides users with explicit progress visibility during lengthy tasks.
- **Provenance**: `langchain.agents.middleware.TodoListMiddleware`, `deepagents.profiles.harness._openai_codex`, `src/seamus/harness/runner.py`.

### Agent Artifacts Protocol and Dedicated UI Viewer Panel
- **Description**: Introduce an Artifacts abstraction for persistent, high-density outputs (plans, reports, architecture diagrams, code diffs, standalone scripts). Establish:
  1. Persistence: storage under `/workspace/.seamus/artifacts/` or extraction from structured tool calls / checkpoints.
  2. UI Experience: a dedicated Artifacts tab or split-pane viewer alongside Chat, Changes, and Inspector, supporting Markdown rendering, syntax highlighting, and export.
- **Rationale**: Keeps chat conversations clean and scannable while giving persistent, dedicated visibility to substantial engineering deliverables.
- **Provenance**: `ui/src/components/`, [abstractions.md](./abstractions.md), [architecture.md](./architecture.md).

### Dynamic Project Rules Discovery from Workspace (.seamus/rules and AGENTS.md)
- **Description**: Enhance `DynamicSystemPromptMiddleware` to inspect the agent workspace (`/workspace/.seamus/rules` or `/workspace/AGENTS.md`) prior to model turns, injecting project-specific guidelines into a dedicated `<project_rules>` XML tag.
- **Rationale**: Keeps the agent automatically synchronized with repository-level conventions and memory files without requiring session re-initialization.
- **Provenance**: [0018-dynamic-system-prompt-architecture.md](../decisions/0018-dynamic-system-prompt-architecture.md).

### [HIGH PRIO] Stop button
- **Description**: When the agent is running (is in any other state than waiting for user), we need to be able to stop its run. In such case the conversation should not be possible to continue; we'll need to branch from the past point.
- **Requires**: Conversation branching (not tracked here yet, needs to be thought through properly)

### Thorough Security Review of Containerized OpenSandbox Server & Docker Socket Configuration
- **Description**: Perform an in-depth security review and hardening pass on the containerized `opensandbox-server` deployment (`opensandbox/Dockerfile`, `opensandbox/sandbox.toml`, and `docker-compose.yml`). Review the security implications of mounting `/var/run/docker.sock`, tighten `allowed_host_paths` in `[storage]`, evaluate Docker socket proxies or rootless/gVisor (`runsc`)/Kata isolation runtimes (`[secure_runtime]`), review container capability drops/seccomp/AppArmor profiles, and audit sandbox network egress policies and port range exposure.
- **Rationale**: Mounting `/var/run/docker.sock` and provisioning sibling containers grants privileged daemon control to the sandbox server; hardening these boundaries is critical before untrusted or multi-tenant workloads run in sandboxes.
- **Provenance**: [0010-opensandbox-filesystem-sandboxing.md](../decisions/0010-opensandbox-filesystem-sandboxing.md#5-containerized-local-opensandbox-server-opensandbox-docker-composeyml-runsh), [architecture.md](./architecture.md#component-boundaries).

### Dynamic Model Catalog and Dropdowns in UI Configuration Modals
- **Description**: The in-browser `ConfigModal` currently requires raw JSON editing for all configuration fields. Add structured input fields or dropdowns for supported model names and inference formats while preserving the raw JSON editing tab.
- **Rationale**: Reduces syntax errors and configuration friction when configuring agents and sessions.
- **Provenance**: [0003-react-web-ui.md](../decisions/0003-react-web-ui.md), [abstractions.md](./abstractions.md#ui-ui).

### Automated Integration Tests for Gitea Docker Compose Stack
- **Description**: Existing test suites verify unit logic and persistence mechanics using mock clients and temporary Git directories. Add automated end-to-end integration tests that run against the live `docker-compose` environment (`backend`, `frontend`, `gitea`, `postgres`).
- **Rationale**: Validates actual HTTP interactions, Gitea API responses, and container volume persistence in CI/CD pipelines.
- **Provenance**: [0008-git-persistence.md](../decisions/0008-git-persistence.md), [conventions.md](./conventions.md#container-orchestration--launch-conventions).

### Detailed End-to-End Testing of Thread Acceptance and Sync PR Lifecycle
- **Description**: Perform in-depth end-to-end testing of the thread acceptance lifecycle and Gitea Sync PR merges across complex multi-turn trajectories, concurrent operations, and error states following the resolution of tool call rendering in [0013-tool-call-lifecycle-ui.md](../decisions/0013-tool-call-lifecycle-ui.md).
- **Rationale**: Ensures the automated Sync PR merge, thread closure, and branch synchronization are robust under realistic usage before full operational release.
- **Provenance**: [0012-sync-prs-and-thread-accept.md](../decisions/0012-sync-prs-and-thread-accept.md), [0013-tool-call-lifecycle-ui.md](../decisions/0013-tool-call-lifecycle-ui.md).

### Visual Diff File Path Filtering in Changes Viewer
- **Description**: Add text-based path/glob search filtering in the Changes viewer sidebar to quickly filter down files in very large pull requests.
- **Rationale**: While hierarchical file tree/list navigation and per-file collapsible folding are implemented, large pull requests with dozens of files benefit from instant path filtering.
- **Provenance**: [0015-session-changes-diff-tab.md](../decisions/0015-session-changes-diff-tab.md).


### URL should reflect what's opened in SPA
- **Description**: No matter which chat we open, the URL stays unchanged.
- **Expectation**: As we navigate the system, each agent, session, thread and tab should have separate URLs that mutate as we click around the page.
- **Rationale**: One should be able to share the link to specific place in the UI, without requiring the receipient of the link to traverse the UI manually
- **Provenance**: Manual

### Scrolling the chat section is broken (bug)
- **Description**: If the last bubble in the chat is active (running tool, unfinished thinking, etc) and the thread is long enough to scroll, when we try to scroll, we get auto-scrolled to  the active bubble
- **Expectation**: User actions should take precedence over automated scrolls; TBD whether we wanna scroll down on new bubble. Consider adding "follow thread" checkbox and "scroll to bottom" button.
- **Provenance**: Manual

