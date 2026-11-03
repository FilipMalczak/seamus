# Backlog

Persistent record of work intentionally left outstanding across the project, maintained in accordance with [AGENTS.md](../AGENTS.md).

> Current high-level trajectory is: skills -> artifacts -> modes (plan as the first new mode)
> The idea is that for plan mode I need to present plan somehow; 
> to do so I can use a2ui artifacts, which I already planned, as they can  be used for closed questions or any kind of user survey - and then to any other custom use case the agent might find; maybe researcher will have some use here?
> anyway, a2ui is nontrivial, so we'll need to explain how to build these; no point in sending an explanation longer than the system prompt with every inference, so we'll want to offload a2ui as a skill


## Deferred

### Multi-Mount Repository Support and Dynamic Skill Discovery
- **Description**: When Seamus introduces support for mounting multiple repositories/projects (e.g., existing user codebases) into the agent's sandbox container, dynamically discover and track both `<mount>/skills` and `<mount>/.skills` directories present across all mounted workspaces as project-level skill sources. In accordance with the established skill precedence hierarchy, non-dotted `skills` takes precedence over dotted `.skills`, and project mounts take precedence after the operational `/workspace` but before ambient system-wide skills.
- **Why Deferred**: Requires establishing multi-mount repository architecture first; single agent repository mounting is the current model.
- **Revisit Trigger**: When multi-repository mounting is implemented in Seamus.
- **Provenance**: [0024-anthropic-skills-and-system-settings.md](../decisions/0024-anthropic-skills-and-system-settings.md), [0026-in-sandbox-skill-mount-paths.md](../decisions/0026-in-sandbox-skill-mount-paths.md).

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

### Gitea Repository Branch Protection Rules
- **Description**: Configure branch protection rules on all agent and system Git repositories in Gitea to restrict direct pushes to session and main branches. Workspaces are not a freely accessible content base; all modifications must be authorized (such as administrator intervention or verified agent turns).
- **Why Deferred**: Core Git workflow, Sync PR lifecycle, and auto-pull mechanics were established first.
- **Revisit Trigger**: When multi-user authorization and branch governance are implemented.
- **Provenance**: [0008-git-persistence.md](../decisions/0008-git-persistence.md), [0026-in-sandbox-skill-mount-paths.md](../decisions/0026-in-sandbox-skill-mount-paths.md), [INV-036](./invariants.md#inv-036-purposeful-workspace-synchronization--auto-pull).

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

### Synchronous Git Subprocess Invocations in Async Server Flows
- **Current Problem**: `GitWorkspaceManager._run_git` calls `subprocess.run(["git", ...])` synchronously. During HTTP requests (`create_agent`, `commit_agent_config`, `commit_session_config`) and checkpoint serialization (`GitCheckpointSaver`), disk I/O and remote Git pushes to Gitea block the asyncio event loop thread.
- **Improvement**: Offload Git commands to a thread pool via `asyncio.to_thread` or switch to an asynchronous subprocess runner (`asyncio.create_subprocess_exec`) to avoid blocking the server event loop during Git operations.
- **Provenance**: [0008-git-persistence.md](../decisions/0008-git-persistence.md), [architecture.md](./architecture.md#component-boundaries).

### In-Memory Store State Isolation Across Multiple Server Workers
- **Current Problem**: `HarnessStore` maintains an in-memory dictionary of agents and sessions hydrated from Gitea only at startup. Running multiple server worker processes or replicas leads to desynchronized state, as mutations in one worker process are not reflected in the memory of another.
- **Improvement**: Introduce cross-worker synchronization or transition `HarnessStore` to a read-through/write-through cache against Gitea/a persistent backing store for multi-worker deployments.
- **Provenance**: [0002-harness-server-mvp.md](../decisions/0002-harness-server-mvp.md), [0008-git-persistence.md](../decisions/0008-git-persistence.md), [architecture.md](./architecture.md#system-overview).

### Cross-Platform macOS and Windows Runner Support in CI
- **Current Problem**: The CI test suite and host environment assumptions currently only support Linux (`ubuntu-latest`). Running the test suite on macOS and Windows fails due to OS-specific path assumptions, process signal/subprocess differences, and absence of standard container runtimes on hosted runners.
- **Improvement**: Audit and resolve cross-platform compatibility issues (e.g., path normalization across Windows/macOS, process lifecycle handling, and conditional test skipping or container mocking) and re-enable macOS and Windows runners in `.github/workflows/ci.yml`.
- **Provenance**: [0023-github-actions-ci-pipeline.md](../decisions/0023-github-actions-ci-pipeline.md), [conventions.md](./conventions.md#continuous-integration-conventions).

### Plan State Recovery Across `todo_implementation` Setting Toggles
- **Current Problem**: If a session uses `todo_implementation: deepagents` and the agent generates a task plan, switching `todo_implementation` to `none` hides the plan and tools. Switching back to `deepagents` recovers the previous plan because `PlanningState` (`todos` in LangGraph checkpoints and `todos.json` in workspace) remains intact on disk. This recovery happens incidentally because we did not put effort into lifecycle state transitions across configuration toggles.
- **Improvement**: Think through and deliberately define the desired behavior when toggling between planning implementations (or to `none` and back): decide whether prior plan state should be retained, cleared, archived, or version-branched across implementation switches.
- **Provenance**: [0025-todo-list-middleware.md](../decisions/0025-todo-list-middleware.md), [invariants.md](./invariants.md#inv-033-configurable-todo-planning-and-system-prompt-composition).

### Inconsistent Semi-Live State in Agent Inspector Tools Section
- **Current Problem**: The Agent Inspector is semi-live inconsistently: when session or agent configuration changes (e.g. toggling tools or settings), the tools tab immediately updates to show tools for the newly configured runner (reflecting "next inference"), whereas other tabs (messages, todos, inference trace) reflect the state preserved in checkpoints from the "last inference".
- **Improvement**: Clearly delineate or align inspector tabs: indicate whether the inspected tool manifest represents the current runner configuration ("next turn") or the snapshot of tools active during the inspected checkpoint turn ("last inference"), or synchronize them coherently with checkpoint metadata.
- **Provenance**: [0011-agent-inspector.md](../decisions/0011-agent-inspector.md), [0025-todo-list-middleware.md](../decisions/0025-todo-list-middleware.md).

### Inspector Tool Description Multiline Whitespace Collapsing
- **Current Problem**: In `AgentInspector.tsx`, the tool card description `<p className="tool-description">{tool.description}</p>` renders tool docstrings without preserving newlines (`white-space: pre-wrap`), causing multi-paragraph tool explanations or formatted argument summaries to collapse into a single unformatted run of text.
- **Improvement**: Apply `white-space: pre-wrap` (or render with the UI Markdown component) to `.tool-description` in the inspector tools grid so formatted tool explanations remain legible.
- **Provenance**: [0011-agent-inspector.md](../decisions/0011-agent-inspector.md), `ui/src/components/AgentInspector.tsx`.

### Testing and Verification of Session Termination and Branching Lifecycle
- > Lost in agentic translation: I originally meant manual testing, but it makes more sense to automate these tests
- **Current Problem**: Session killing (stopping ongoing model execution) and thread branching from historical checkpoints were introduced in [0022-branching-out-and-session-lifecycle.md](../decisions/0022-branching-out-and-session-lifecycle.md). The lifecycle mechanics were only lightly tested; edge cases around subprocess signals, container process cleanup, checkpoint consistency during mid-stream stops, and Gitea branch consistency during rapid branching remain undertested and may harbor latent bugs.
- **Improvement**: Write comprehensive unit and integration tests exercising mid-turn cancellation, sandbox cleanup, thread termination status propagation, and branching edge cases.
- **Provenance**: [0022-branching-out-and-session-lifecycle.md](../decisions/0022-branching-out-and-session-lifecycle.md).

## TODO

### Native LM-XML Skills System with Load/Unload Skill Tools
- **Description**: Replace the reliance on LangChain DeepAgents' built-in `SkillsMiddleware` with a first-party, native Seamus skills implementation. The native system will be built directly on `lmxml` dynamic prompt structures (integrating seamlessly with `DynamicSystemPromptMiddleware`) and explicit `load_skill` / `unload_skill` agent tools to disclose, activate, and deactivate skill instructions and associated tools on demand rather than relying on automatic middleware inspection and implicit prompt appending.
- **Rationale**: DeepAgents' `SkillsMiddleware` operates as an external abstraction with rigid prompt formatting, strict PyYAML frontmatter parsing (which silently drops real-world skills with unquoted inline structures like colons or braces in descriptions, such as `bevy-assets`), and implicit disclosure rules. A native implementation based on `lmxml` dynamisms, relaxed/resilient YAML frontmatter parsing, and explicit `load_skill` / `unload_skill` tools will align directly with Seamus's structured XML system prompt architecture, provide tighter control over context window budgeting and prompt cache breakpoints, and avoid middleware ordering or prompt overriding frictions.
- **Provenance**: [0024-anthropic-skills-and-system-settings.md](../decisions/0024-anthropic-skills-and-system-settings.md), [0018-dynamic-system-prompt-architecture.md](../decisions/0018-dynamic-system-prompt-architecture.md), [0026-in-sandbox-skill-mount-paths.md](../decisions/0026-in-sandbox-skill-mount-paths.md).

### Built-In Bundled Skills for Seamus
- **Description**: Package a core suite of built-in skills bundled directly with Seamus (e.g., for creating a2ui artifacts, interactive planning surveys, code review workflows) mounted in sandboxes under `/skills/bundled`. These skills hold top-most precedence across all sessions as integral platform capabilities that cannot be overridden by session or system skills.
- **Rationale**: Built-in skills allow offloading complex tool or UI instructions (like A2UI) from the static system prompt to on-demand progressive disclosure.
- **Provenance**: [0024-anthropic-skills-and-system-settings.md](../decisions/0024-anthropic-skills-and-system-settings.md), [0018-dynamic-system-prompt-architecture.md](../decisions/0018-dynamic-system-prompt-architecture.md), [0026-in-sandbox-skill-mount-paths.md](../decisions/0026-in-sandbox-skill-mount-paths.md).

### Operational Execution Modes and Thread Transition Triggers (plan, chat, act, analyse, routing)
- **Description**: Support an open set of configurable execution modes that govern agent interaction style, prompt framing, workspace usage, and thread-spawning triggers:
  1. `plan`: Generates a structured execution plan before implementing changes. Spawns a new thread when formulating a plan, and automatically opens another new thread when transitioning from plan alignment to execution.
  2. `chat`: Conversational orientation; the workspace serves primarily as an agent scratchpad rather than the focus of production file changes.
  3. `act`: Direct task execution; executes user commands and edits promptly without upfront planning cycles.
  4. `analyse`: Read-only workspace investigation; answers questions and analyzes code without modifying persistent files.
  5. `routing` (planned): Uses a classifier model (such as Jev or an LLM wrapped in dedicated tools) to triage user input and dispatch to an appropriate operational mode.
  Switching between operational modes always closes the current thread and opens a fresh thread.
- **Rationale**: Aligns agent behavior with specific user intents while using threads as deterministic boundaries between planning, discussion, analysis, and execution.
- **Provenance**: [0019-threads-modes-personas-architecture.md](../decisions/0019-threads-modes-personas-architecture.md), [threads_modes_personas.md](./threads_modes_personas.md), [REQ-025](./requirements.md#req-025-operational-modes-and-thread-transition-triggers), [INV-028](./invariants.md#inv-028-mode-transition-thread-spawning-boundary).

### Pluggable Agent Personas (Coder, Office Worker, Designer, etc.)
- **Description**: Support an extensible architecture for agent personas, with immediate near-term focus on the `Coder` persona to support self-hosting / dogfooding development (developing Seamus with Seamus), while supporting custom persona registration in the long term. Personas establish baseline `<identity>`, domain instructions, and specialized tool suites/backends (exact rules for persona switching/inheritance across sessions remain TBD).
- **Rationale**: Expands Seamus from a purely code-focused assistant into a versatile multi-domain autonomous harness while prioritizing autonomous coding for Seamus self-development.
- **Provenance**: [0019-threads-modes-personas-architecture.md](../decisions/0019-threads-modes-personas-architecture.md), [threads_modes_personas.md](./threads_modes_personas.md), [REQ-024](./requirements.md#req-024-agent-personas-and-baseline-archetypes).

### Subagent Architecture: Prompts, Sandbox Isolation, and UI Representation
- **Description**: Investigate and define Seamus subagent integration using DeepAgents subagents (`SubAgentMiddleware` / `AsyncSubAgent`). Specifically determine:
  1. System prompt composition: whether subagents inherit parent workspace rules and engineering discipline or use specialized task prompts.
  2. Execution isolation: whether subagents operate in the parent session's container workspace or spin up isolated workspace subtrees/ephemeral containers.
  3. UI visualization: design how delegated subagent runs, parallel executions, and returns are rendered in the SPA (e.g., collapsible child execution cards within the chat bubble or dedicated sub-threads).
- **Rationale**: Delegation to specialized subagents is central to autonomous harness scaling; clear execution boundaries and user visibility must be established before enabling subagents.
- **Provenance**: `src/seamus/harness/runner.py`, `deepagents.middleware.subagents`, [abstractions.md](./abstractions.md).


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

### Thorough Security Review of Containerized OpenSandbox Server & Docker Socket Configuration
- **Description**: Perform an in-depth security review and hardening pass on the containerized `opensandbox-server` deployment (`opensandbox/Dockerfile`, `opensandbox/sandbox.toml`, and `docker-compose.yml`). Review the security implications of mounting `/var/run/docker.sock`, tighten `allowed_host_paths` in `[storage]`, evaluate Docker socket proxies or rootless/gVisor (`runsc`)/Kata isolation runtimes (`[secure_runtime]`), review container capability drops/seccomp/AppArmor profiles, and audit sandbox network egress policies and port range exposure.
- **Rationale**: Mounting `/var/run/docker.sock` and provisioning sibling containers grants privileged daemon control to the sandbox server; hardening these boundaries is critical before untrusted or multi-tenant workloads run in sandboxes.
- **Provenance**: [0010-opensandbox-filesystem-sandboxing.md](../decisions/0010-opensandbox-filesystem-sandboxing.md#5-containerized-local-opensandbox-server-opensandbox-docker-composeyml-runsh), [architecture.md](./architecture.md#component-boundaries).

### Dynamic Model Catalog and Dropdowns in UI Configuration Modals
- **Description**: The in-browser `ConfigModal` currently requires raw JSON editing for all configuration fields. Add structured input fields or dropdowns for supported model names, inference formats, and `todo_implementation` (`none`, `deepagents`) while preserving the raw JSON editing tab.
- **Rationale**: Reduces syntax errors and configuration friction when configuring agents and sessions.
- **Provenance**: [0003-react-web-ui.md](../decisions/0003-react-web-ui.md), [0025-todo-list-middleware.md](../decisions/0025-todo-list-middleware.md), [abstractions.md](./abstractions.md#ui-ui).

### Custom Planning Toolset Integration
- **Description**: Implement custom planning toolset alternatives alongside `none` and `deepagents` (e.g. customized task decomposition, plan verification, or milestone tracking), introducing corresponding `todo_implementation` enum values.
- **Rationale**: Enables dedicated, customizable task planning architectures beyond the standard DeepAgents middleware.
- **Provenance**: [0025-todo-list-middleware.md](../decisions/0025-todo-list-middleware.md), [invariants.md](./invariants.md#inv-033-configurable-todo-planning-and-system-prompt-composition).

### Automated Integration Tests for Gitea Docker Compose Stack
- **Description**: Existing test suites verify unit logic and persistence mechanics using mock clients and temporary Git directories. Add automated end-to-end integration tests that run against the live `docker-compose` environment (`backend`, `frontend`, `gitea`, `postgres`).
- **Rationale**: Validates actual HTTP interactions, Gitea API responses, and container volume persistence in CI/CD pipelines.
- **Provenance**: [0008-git-persistence.md](../decisions/0008-git-persistence.md), [conventions.md](./conventions.md#container-orchestration--launch-conventions).

### Detailed End-to-End Testing of Thread Acceptance and Sync PR Lifecycle
- **Description**: Perform in-depth end-to-end testing of the thread acceptance lifecycle and Gitea Sync PR merges across complex multi-turn trajectories, concurrent operations, and error states following the resolution of tool call rendering in [0013-tool-call-lifecycle-ui.md](../decisions/0013-tool-call-lifecycle-ui.md).
- **Rationale**: Ensures the automated Sync PR merge, thread closure, and branch synchronization are robust under realistic usage before full operational release.
- **Provenance**: [0012-sync-prs-and-thread-accept.md](../decisions/0012-sync-prs-and-thread-accept.md), [0013-tool-call-lifecycle-ui.md](../decisions/0013-tool-call-lifecycle-ui.md).

### URL should reflect what's opened in SPA
- **Description**: No matter which chat we open, the URL stays unchanged.
- **Expectation**: As we navigate the system, each agent, session, thread and tab should have separate URLs that mutate as we click around the page.
- **Rationale**: One should be able to share the link to specific place in the UI, without requiring the receipient of the link to traverse the UI manually
- **Provenance**: Manual

### UI Layout Default Proportions (1:2 Tree-to-Chat Ratio)
- **Description**: Update the default draggable split divider ratio from the current 50/50 (`0.50`) established in [0014-ui-layout-proportions-breadcrumbs.md](../decisions/0014-ui-layout-proportions-breadcrumbs.md) to a 1:2 split (~`0.333`), allocating 1/3 of the viewport width to the entity navigation sidebar and 2/3 to the primary chat and inspector panel. Retain user-customized ratio overrides in `localStorage` (`seamus_sidebar_ratio`) and double-click reset behavior.
- **Rationale**: A 1:2 ratio gives greater horizontal breathing room to conversational messages, tool call payloads, and code diffs while preserving adequate width for the navigation tree.
- **Provenance**: [0014-ui-layout-proportions-breadcrumbs.md](../decisions/0014-ui-layout-proportions-breadcrumbs.md).

### Skills Visibility and Inspection in Agent Inspector
- **Description**: Add a dedicated "Skills" view or tab within `AgentInspector` (alongside Prompt, Tools, Todos, Inference, Messages, Workspace). Display all discovered skills active for the session, showing their origin layer (workspace `/workspace/skills`, workspace dotted `/workspace/.skills`, or system `/skills/system/{idx}`), frontmatter metadata (name, description), and rendered markdown instructions.
- **Rationale**: Following the introduction of filesystem skills in [0024-anthropic-skills-and-system-settings.md](../decisions/0024-anthropic-skills-and-system-settings.md) and [0026-in-sandbox-skill-mount-paths.md](../decisions/0026-in-sandbox-skill-mount-paths.md), operators need runtime visibility into which skills are mounted, active, and accessible to the agent.
- **Provenance**: [0011-agent-inspector.md](../decisions/0011-agent-inspector.md), [0024-anthropic-skills-and-system-settings.md](../decisions/0024-anthropic-skills-and-system-settings.md), [0026-in-sandbox-skill-mount-paths.md](../decisions/0026-in-sandbox-skill-mount-paths.md).

### Verbose In-UI Unhandled Error Presentation
- **Description**: Enhance frontend error handling when an unhandled error occurs during inference or backend execution. Instead of displaying a brief generic error pill or banner, surface an expandable, detailed error panel containing the full error message, stack trace / traceback, failure context, and actionable diagnostic guidance.
- **Rationale**: When agent runs or tool calls fail unexpectedly, operators currently have to dig into server terminal logs or Logfire to diagnose the issue; rich in-UI error reporting provides immediate debugging feedback.
- **Provenance**: [0003-react-web-ui.md](../decisions/0003-react-web-ui.md), [0005-logfire-integration.md](../decisions/0005-logfire-integration.md).

### Automatic UI Polling and State Refresh for Active Runs and Changes Tab
- **Description**: Implement automatic UI refresh or polling for live state updates:
  1. Automatically update thread run status, message stream, and active tool calls without requiring manual interaction.
  2. Automatically refresh the Changes tab diff view as the agent performs filesystem modifications or when switching between turns.
- **Rationale**: Eliminates stale UI views and manual refresh friction when observing active agent executions and inspecting workspace modifications.
- **Provenance**: [0013-tool-call-lifecycle-ui.md](../decisions/0013-tool-call-lifecycle-ui.md), [0015-session-changes-diff-tab.md](../decisions/0015-session-changes-diff-tab.md), [0021-ui-chat-autoscroll-and-changes-file-filtering.md](../decisions/0021-ui-chat-autoscroll-and-changes-file-filtering.md).

### Session-Level UI View and Unified Thread Feed
- **Description**: Evolve the UI navigation model so that selecting or creating an agent lands on a primary Session view rather than requiring selection of individual threads. The session view will present an aggregated, continuous chronological feed of all past threads in the session, with the composer input serving as a direct proxy to the current active open thread.
- **Rationale**: Treating the session as the primary unit of conversational context provides a unified conversational history across sequential thread boundaries (e.g. plan -> execute transitions) while preserving threads as clean checkpoint/execution isolation boundaries.
- **Provenance**: [0019-threads-modes-personas-architecture.md](../decisions/0019-threads-modes-personas-architecture.md), [threads_modes_personas.md](./threads_modes_personas.md).

### Entity Auto-Naming and UX Daemons Architecture
- **Description**: Implement automated naming for entities across Seamus:
  1. Agents: automatically generate randomized, memorable multi-word slugs (e.g., `brave-curie-42`).
  2. Sessions and Threads: automatically generate descriptive names using a lightweight, dedicated "namer" agent configured at the agent level.
  This forms the first component of a broader "UX Daemons" initiative: lightweight, dedicated background agents that handle peripheral UX automation (entity naming, proactive todo management, branch summaries) without interfering with primary task execution.
- **Rationale**: Manually naming agents, sessions, and threads creates unnecessary friction; automated descriptive naming keeps navigation clean and organized.
- **Provenance**: [0002-harness-server-mvp.md](../decisions/0002-harness-server-mvp.md), [0019-threads-modes-personas-architecture.md](../decisions/0019-threads-modes-personas-architecture.md), [vocabulary.md](./vocabulary.md).

### Configurable Skills Implementation Setting (skills_implementation)
- **Description**: Introduce an explicit `skills_implementation` configuration setting across system defaults, agent configurations, and session overrides with supported values `none`, `deepagents` (current adapter using built-in `SkillsMiddleware`), and `native` (the planned LM-XML first-party skills system). Expose the setting in the configuration modal and dynamically reload runner middleware during session initialization and runtime updates, mirroring the pattern established for `todo_implementation`.
- **Rationale**: Gives operators explicit control over whether and how skills are exposed, supporting granular experimentation and smooth migration from DeepAgents' middleware to Seamus's native implementation.
- **Provenance**: [0024-anthropic-skills-and-system-settings.md](../decisions/0024-anthropic-skills-and-system-settings.md), [0025-todo-list-middleware.md](../decisions/0025-todo-list-middleware.md), [0026-in-sandbox-skill-mount-paths.md](../decisions/0026-in-sandbox-skill-mount-paths.md).

### Minimalistic Dashboard View for Agents and Sessions
- **Description**: Implement an alternative, lightweight "Dashboard" view alongside the rich developer/IDE-like navigation tree and inspector:
  1. Plain agent grid: Displays all configured agents as a clean, uncluttered card grid.
  2. Session grid: Selecting an agent transitions to a grid of its sessions. Each session card displays rows showing a `(...)`-collapsed preview of the last couple task/thread names.
  3. Seamless view transitions: Provides a quick, distraction-free conversational interface for goal-oriented interaction, with prominent links to navigate into the "hydrated" developer/IDE view when in-depth runtime inspection or advanced configuration is required.
- **Rationale**: Accommodates both lightweight conversational workflows focused on getting tasks done and deep engineering/debugging sessions requiring full inspectability.
- **Provenance**: [0003-react-web-ui.md](../decisions/0003-react-web-ui.md), [architecture.md](./architecture.md#system-overview).

## Not formalized

- user input variations (actively being designed):
  - user-accepted tool calls
  - artifact-based forms that the user can open and fill
  - in-message UI pieces?
  - specialized messages?
- default implementation selection: decide on system-wide defaults for `todo_implementation` and `skills_implementation` once alternative/native implementations are stabilized

