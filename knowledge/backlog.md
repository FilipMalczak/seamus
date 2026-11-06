# Backlog

Persistent record of work intentionally left outstanding across the project, maintained in accordance with [AGENTS.md](../AGENTS.md).

> Current high-level trajectory is: skills -> artifacts -> modes (plan as the first new mode)
> The idea is that for plan mode I need to present plan somehow; 
> to do so I can use A2UI artifacts, which I already planned, as they can be used for closed questions or any kind of user survey - and then to any other custom use case the agent might find; maybe researcher will have some use here?
> anyway, A2UI components are nontrivial, so we'll need to explain how to build these; no point in sending an explanation longer than the system prompt with every inference, so we'll want to offload A2UI components as a skill


## Deferred

### Alternative Button Action Level Notations in Artifact Manifests
- **Description**: Experiment with consolidated or level-based notations for manifest button configurations (e.g. `someLevelName = data | unblocking | closing`) rather than discrete orthogonal boolean flags (`unblocking: bool`, `closing: bool`).
- **Why Deferred**: Independent boolean flags (`unblocking: bool = False`, `closing: bool = False`) are explicit, orthogonal, and simple to validate in early iterations.
- **Revisit Trigger**: When authoring experience reveals repetitive button configuration patterns across custom artifacts.
- **Provenance**: [0034-mature-a2ui-artifacts-model.md](../decisions/0034-mature-a2ui-artifacts-model.md), [artifacts.md](./artifacts.md).

### Surface Event Name in `wait_for_click` Output and Context Dispatch
- **Description**: Incorporate the declarative action event name (e.g. `action.event.name` from `body.json`) into the `ClickResult` returned by `wait_for_click`, persisted interaction files, and synthetic unblocking messages.
- **Why Deferred**: Interaction dispatch currently relies on button ID and evaluated context payload; event name is ignored in initial persistence to keep state transitions minimal.
- **Revisit Trigger**: When multiple buttons dispatch distinct event names sharing identical IDs or when backend event routing requires semantic event classification.
- **Provenance**: [0034-mature-a2ui-artifacts-model.md](../decisions/0034-mature-a2ui-artifacts-model.md), [artifacts.md](./artifacts.md).

### Synthetic Tool Call Injection for Blocking Artifact Unblocks
- **Description**: Investigate synthetic tool call injection (e.g. injecting a synthetic `wait_for_click` tool call and tool result pair) into the model's message trajectory instead of injecting a synthetic user message (`<SYNTHETIC MESSAGE INDICATOR>`) when an agent finishes a blocking turn without calling `wait_for_click`.
- **Why Deferred**: Synthetic user messages avoid manipulating tool call history in provider-specific LLM adapters, but synthetic tool call injection might feel more natural to the model's tool-use reasoning loop.
- **Revisit Trigger**: When evaluating model adherence and conversational flow across various LLM providers (Anthropic, OpenAI, Gemini) during blocking artifact unblocks.
- **Provenance**: [0034-mature-a2ui-artifacts-model.md](../decisions/0034-mature-a2ui-artifacts-model.md), [artifacts.md](./artifacts.md).

### Fine-Grained Arity Controls for Questionnaire Inquiry Tools
- **Description**: Expand selection constraints for `make_questionnaire` (and future inquiry tools) from boolean `multiple_choice: bool` to fine-grained arity bounds: `arity: int | tuple[int, int | Literal["*"]]` (e.g. `1` for single choice, `(1, "*")` for at least one choice, `(0, "*")` for optional multiple selection, `(2, 4)` for a bounded range).
- **Why Deferred**: Boolean `multiple_choice` matches standard `ChoiceSet` primitives cleanly without requiring custom client-side validation logic or complex input validators.
- **Revisit Trigger**: When UI input validators support custom min/max arity bounds or when complex survey forms require mandatory zero-or-more / range constraints.
- **Provenance**: [0034-mature-a2ui-artifacts-model.md](../decisions/0034-mature-a2ui-artifacts-model.md), [artifacts.md](./artifacts.md).

### Tabbed Artifact Exposition and Non-Blocking Cadence Lifecycles
- **Description**: Expand artifact exposition support from `exposition=embedded` to include `exposition=tabbed` (rendering artifacts in dedicated inspector-like tabs rather than inline in chat bubbles). Formalize the lifecycle and closing rules for non-blocking artifacts (`blocking=false`) upon submission or timeout.
- **Why Deferred**: Focused initially on embedded questionnaires with blocking cadence to validate the core pipeline and synthetic tool dispatch before expanding tabbed workflows.
- **Revisit Trigger**: When introducing planning or multi-view artifacts that require dedicated panel real estate or optional non-blocking surveys.
- **Provenance**: [0034-mature-a2ui-artifacts-model.md](../decisions/0034-mature-a2ui-artifacts-model.md), [artifacts.md](./artifacts.md).

### Custom Interactive Artifact Authoring
- **Description**: Provide advanced agent workflows and templates for authoring custom multi-surface A2UI interactive artifacts via `make_artifact` with arbitrary button hierarchies and state models under `/artifacts/custom/`.
- **Why Deferred**: Prioritized specialized, validated artifact families (questionnaires, forms, plans) to establish disk structure and rendering contracts before opening raw artifact creation.
- **Revisit Trigger**: When introducing custom agent generative UI authoring workflows.
- **Provenance**: [0034-mature-a2ui-artifacts-model.md](../decisions/0034-mature-a2ui-artifacts-model.md), [artifacts.md](./artifacts.md).

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

### Session Branching Interaction with Session-Local Non-Blocking Artifacts and Multi-Repo Git Mounts
- **Current Problem**: Session branching (`branch_session`) copies thread checkpoint history and Git commits from a specific parent assistant turn. However, non-blocking artifacts (such as `plan`) and session-level directories (such as notes and specs in `/workspace`) are session-scoped and encompass multi-turn, multi-phase exchanges. In addition, when future multi-repository mounts are introduced, multiple Git repositories must remain synchronized across branches, phases, and thread checkpoints. We need to rethink and review how session branching, session-local non-blocking artifacts, and multi-repo Git mounts interact safely without orphaned artifacts, desynchronized working trees, or broken plan lineage.
- **Improvement**: Formally model artifact provenance and multi-repo checkpoint synchronization in `branch_session`, ensuring child branched sessions cleanly copy or fork active plan artifacts and multi-mount Git states without conflicting with the parent session.
- **Provenance**: [0030-operational-modes-and-plan-mode.md](../decisions/0030-operational-modes-and-plan-mode.md), `src/seamus/harness/runner.py`, `src/seamus/persistence/workspace.py`.

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

### Testing and Verification of Session Termination and Branching Lifecycle
- > Lost in agentic translation: I originally meant manual testing, but it makes more sense to automate these tests
- **Current Problem**: Session killing (stopping ongoing model execution) and thread branching from historical checkpoints were introduced in [0022-branching-out-and-session-lifecycle.md](../decisions/0022-branching-out-and-session-lifecycle.md). The lifecycle mechanics were only lightly tested; edge cases around subprocess signals, container process cleanup, checkpoint consistency during mid-stream stops, and Gitea branch consistency during rapid branching remain undertested and may harbor latent bugs.
- **Improvement**: Write comprehensive unit and integration tests exercising mid-turn cancellation, sandbox cleanup, thread termination status propagation, and branching edge cases.
- **Provenance**: [0022-branching-out-and-session-lifecycle.md](../decisions/0022-branching-out-and-session-lifecycle.md).

### Review and Rethink Error Reporting Architecture and Semantics
- **Current Problem**: Error reporting across the harness stack is unclear and fragmented. Errors originating from tool execution (e.g. argument validation or duplicate question IDs in `ask`), sandbox execution, runner loops, and SSE event streaming (`RUN_ERROR` vs `TOOL_CALL_RESULT` with `is_error=True`) lack a clear taxonomy, consistent propagation rules, and transparent visibility in both agent reasoning context and frontend user feedback.
- **Improvement**: Review and redesign error reporting systematically: define distinct error categories (recoverable tool feedback intended for model correction vs fatal harness/system faults), establish consistent propagation through SSE events and thread status, and provide clear, actionable error indicators in the web UI.
- **Provenance**: `src/seamus/harness/runner.py`, [0031-SUPERSEDED-migrate-a2ui-to-adaptive-cards.md](../decisions/0031-SUPERSEDED-migrate-a2ui-to-adaptive-cards.md), [architecture.md](./architecture.md).

## TODO

### Polymorphic Input Request Specification for Predefined Artifact Builders
- **Description**: Rephrase atomic inquiry builders from `make_questionnaire(questions: list[Question])` to generalized polymorphic builders `make_...(items: list[InputRequest]) -> ...`, where `InputRequest = SingleChoiceQuestion | MultipleChoiceQuestion | OpenQuestion | ColorChoice | DateChoice | ...` (or alternatively modeling the `answers` property of `Question` as an extensible enum/union of input widgets).
- **Rationale**: Predefined artifact builders should accommodate a broader palette of input widgets (color pickers, date pickers, freeform text boxes, file uploads) beyond simple single/multiple-choice questions while preserving atomic generation.
- **Provenance**: [0034-mature-a2ui-artifacts-model.md](../decisions/0034-mature-a2ui-artifacts-model.md), [artifacts.md](./artifacts.md).

### Review and Audit Plan Mode Implementation
- **Description**: Conduct a thorough review and audit of the Plan mode and planner implementation (`PlanBuilder`, prompt composition, `make_plan` tool lifecycle, phase transitions, and UI presentation). In particular, evaluate whether the current A2UI structure and tool mechanics provide optimal model steerability, assess how user comments and section-level revisions should be incorporated, and review whether the prompt instructions and sandbox handoff (`/artifacts/plans/<id>/plan.md`) cleanly support execution across long tasks.
- **Rationale**: Plan mode was quickly composed across multiple iterations (initial mode scaffolding, Adaptive Cards migration, and A2UI decoupling). A dedicated review pass will consolidate lessons learned, eliminate residual rough edges, and prepare the foundation for rich plan commenting and section-level revisions.
- **Provenance**: [0030-operational-modes-and-plan-mode.md](../decisions/0030-operational-modes-and-plan-mode.md), [0034-mature-a2ui-artifacts-model.md](../decisions/0034-mature-a2ui-artifacts-model.md), [0033-decouple-plans-and-submissions-from-a2ui.md](../decisions/0033-decouple-plans-and-submissions-from-a2ui.md), `src/seamus/harness/artifacts.py`, `src/seamus/harness/prompt.py`.

### Steerable Model Implementation for Local Manual Testing
- **Description**: Introduce a steerable model provider for local development and manual testing. The steerable model allows developers to script, step through, or interactively inject specific model responses, text chunks, and tool calls (such as `make_questionnaire` inquiries, custom A2UI artifacts, or specific error states) into active sessions without incurring live LLM API costs or dealing with non-deterministic completions.
- **Rationale**: Greatly streamlines local manual verification of UI features (like interactive A2UI questionnaires, diff viewers, and error handling) and reduces turnaround time for frontend and harness developers.
- **Provenance**: `src/seamus/harness/runner.py`, `tests/test_runner.py`, [0034-mature-a2ui-artifacts-model.md](../decisions/0034-mature-a2ui-artifacts-model.md).

### Native LM-XML Skills System with Load/Unload Skill Tools
- **Description**: Replace the reliance on LangChain DeepAgents' built-in `SkillsMiddleware` with a first-party, native Seamus skills implementation. The native system will be built directly on `lmxml` dynamic prompt structures (integrating seamlessly with `DynamicSystemPromptMiddleware`) and explicit `load_skill` / `unload_skill` agent tools to disclose, activate, and deactivate skill instructions and associated tools on demand rather than relying on automatic middleware inspection and implicit prompt appending.
- **Rationale**: DeepAgents' `SkillsMiddleware` operates as an external abstraction with rigid prompt formatting, strict PyYAML frontmatter parsing (which silently drops real-world skills with unquoted inline structures like colons or braces in descriptions, such as `bevy-assets`), and implicit disclosure rules. A native implementation based on `lmxml` dynamisms, relaxed/resilient YAML frontmatter parsing, and explicit `load_skill` / `unload_skill` tools will align directly with Seamus's structured XML system prompt architecture, provide tighter control over context window budgeting and prompt cache breakpoints, and avoid middleware ordering or prompt overriding frictions.
- **Provenance**: [0024-anthropic-skills-and-system-settings.md](../decisions/0024-anthropic-skills-and-system-settings.md), [0018-dynamic-system-prompt-architecture.md](../decisions/0018-dynamic-system-prompt-architecture.md), [0026-in-sandbox-skill-mount-paths.md](../decisions/0026-in-sandbox-skill-mount-paths.md).

### Operational Execution Modes and Thread Transition Triggers (act, analyse, routing)
- **Description**: Following the initial implementation of `chat` and `plan` modes in [0030-operational-modes-and-plan-mode.md](../decisions/0030-operational-modes-and-plan-mode.md), expand the operational mode set to include:
  1. `act`: Direct task execution; executes user commands and edits promptly without upfront planning cycles.
  2. `analyse`: Read-only workspace investigation; answers questions and analyzes code without modifying persistent files.
  3. `routing`: Uses a classifier model (such as Jev or an LLM wrapped in dedicated tools) to triage user input and dispatch to an appropriate operational mode.
  Switching between operational modes closes non-empty threads and opens a fresh thread (reusing empty initial threads).
- **Rationale**: Aligns agent behavior with specific user intents while using threads as deterministic boundaries between planning, discussion, analysis, and execution.
- **Provenance**: [0019-threads-modes-personas-architecture.md](../decisions/0019-threads-modes-personas-architecture.md), [0030-operational-modes-and-plan-mode.md](../decisions/0030-operational-modes-and-plan-mode.md), [threads_modes_personas.md](./threads_modes_personas.md), [REQ-025](./requirements.md#req-025-operational-modes-and-thread-transition-triggers), [INV-028](./invariants.md#inv-028-mode-transition-thread-spawning-boundary).

### Configuration Synchronization (Template-to-Agent and Agent-to-Session)
- **Description**: Implement mechanisms to synchronize configurations across entity hierarchies:
  1. Template to Agent: Allow updating an agent's `config` from its base `ConfigTemplate`, propagating newly added settings, models, or defaults while preserving agent-specific overrides.
  2. Agent to Session: Provide an explicit sync or inheritance mechanism to propagate updated agent configurations down to existing active sessions, and ensure newly spawned sessions accurately reflect the latest agent configuration state.
- **Rationale**: Agents and sessions currently take snapshot copies of configs during creation. When a template or agent configuration is updated, existing downstream entities remain on stale configuration snapshots with no automated or selective synchronization path.
- **Provenance**: `src/seamus/config/models.py`, `src/seamus/domain/entities.py`, `src/seamus/server/routes/config.py`.

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
- **Description**: Enhance `DynamicSystemPromptMiddleware` to inspect the agent workspace (via configurable rule globs such as `AGENTS.md` and `.seamus/rules/**/*.md`) prior to model turns, injecting project-specific guidelines into a dedicated `<project_rules>` XML tag.
- **Note**: DeepAgents' built-in `AGENTS.md` support looks awkward for project rules because it is actually implemented as `MemoryMiddleware` (`<agent_memory>` + `<memory_guidelines>` instructing the agent to treat rule files as mutable agent memory and proactively rewrite them). We will likely want to go with a native Seamus implementation that loads configured rule files directly into the LM-XML system prompt.
- **Rationale**: Keeps the agent automatically synchronized with repository-level conventions and rule files without requiring session re-initialization or conflating static project rules with mutable agent memory.
- **Provenance**: [0018-dynamic-system-prompt-architecture.md](../decisions/0018-dynamic-system-prompt-architecture.md), [0027-skills-config-project-rules-and-inspector.md](../decisions/0027-skills-config-project-rules-and-inspector.md).

### Thorough Security Review of Containerized OpenSandbox Server & Docker Socket Configuration
- **Description**: Perform an in-depth security review and hardening pass on the containerized `opensandbox-server` deployment (`opensandbox/Dockerfile`, `opensandbox/sandbox.toml`, and `docker-compose.yml`). Review the security implications of mounting `/var/run/docker.sock`, tighten `allowed_host_paths` in `[storage]`, evaluate Docker socket proxies or rootless/gVisor (`runsc`)/Kata isolation runtimes (`[secure_runtime]`), review container capability drops/seccomp/AppArmor profiles, and audit sandbox network egress policies and port range exposure.
- **Rationale**: Mounting `/var/run/docker.sock` and provisioning sibling containers grants privileged daemon control to the sandbox server; hardening these boundaries is critical before untrusted or multi-tenant workloads run in sandboxes.
- **Provenance**: [0010-opensandbox-filesystem-sandboxing.md](../decisions/0010-opensandbox-filesystem-sandboxing.md#5-containerized-local-opensandbox-server-opensandbox-docker-composeyml-runsh), [architecture.md](./architecture.md#component-boundaries).

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

### Session-Level UI View and Unified Thread Feed [HIGH PRIO]
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

### Minimalistic Dashboard View for Agents and Sessions
- **Description**: Implement an alternative, lightweight "Dashboard" view alongside the rich developer/IDE-like navigation tree and inspector:
  1. Plain agent grid: Displays all configured agents as a clean, uncluttered card grid.
  2. Session grid: Selecting an agent transitions to a grid of its sessions. Each session card displays rows showing a `(...)`-collapsed preview of the last couple task/thread names.
  3. Seamless view transitions: Provides a quick, distraction-free conversational interface for goal-oriented interaction, with prominent links to navigate into the "hydrated" developer/IDE view when in-depth runtime inspection or advanced configuration is required.
- **Rationale**: Accommodates both lightweight conversational workflows focused on getting tasks done and deep engineering/debugging sessions requiring full inspectability.
- **Provenance**: [0003-react-web-ui.md](../decisions/0003-react-web-ui.md), [architecture.md](./architecture.md#system-overview).

## Not formalized

- a way to attach to button (in artifact) both data from inputs and comments [low]
- comments need to be saved in artifact state, not just "review" append log [low]
- Workspace needs .gitignore; we need to explain to the agent that that file controls what is persistent and what might disappear at any moment
- proceed/submit buttons disappear from render after closing the artifact [low]
- test that if we kill the system during run, then agent auto-restarts after system restart [mid/high]
- once the harness opens a new thread, we should auto-switch there (if we're in the thread from which we switched)
- session view (its already above, but it has high prio)
- "branch" icon should be more granular and to the right of bubbles (instead of below); review branching in general - icons placement is bit misleading
- review and rethink what should happen with artifacts on accept
- when sending messages is disabled (due to artifact blocking or just agent processing), it should only disable the button and Enter handler; the text field should still be editable (for the sake of preparing a message while agent works)
- in prompt operating_environment -> filesystem_persistence/execution_sandbox it sounds like the installed stuff is also ephemeric (it is, but its a bug)
- when we open new thread, we should include a bunch of messages from previous thread [mid/high] [I expect a lot out of this]; make the overlap numbers configurable
- "sync config" (template -> agent <-> session)
- for the hundreth time, remove 20b default
- custom sandbox images as part of config; bundle dedicated one w/ seamus [mid/high]
- multiple mounted repos; this will require us to figure out squashing strategies and how to track which commit corresponds to which across repos [high, but complicated]
- logfire spans are not grouping agents/sessions/threads as I hoped; besides, GETs pollute the view a lot; besides #2, maybe we could go for embedded span viewer in compse stack?


- default implementation selection: decide on system-wide defaults for `todo_implementation` and `skills_implementation` once alternative/native implementations are stabilized


- way, waaaaay forward: disablability of more layers and components; 
  - for sure context compaction, I dont like it
  - disabling specific artifacts (generic are always allowed, in which case we need to mount custom examples directory, which might be a good idea anyway)

- rethink styling and generally UI colors and shapes
  
