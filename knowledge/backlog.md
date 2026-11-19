# Backlog

Persistent record of work intentionally left outstanding across the project, maintained in accordance with [AGENTS.md](../AGENTS.md).

## Core harness features

### Updates to knowledge docs

Some knowledge docs got misaligned over multiple iterations of agentic development.
Notably, some vocabulary entries are imprecise, modes/personas\[/threads] is slightly incorrect in the future examples, etc.
The issues are not catastrophic yet, but they might escalate soon. We should get ahead of this train - decision log and knowledge docs are integral part of the product (ANY user should be able to modify Seamus to own needs, either by hand or via an agent; that's one of core principles that we are yet to finalize writing).

### Operational Execution Modes and Thread Transition Triggers (act, analyse, routing)
- **Description**: Following the initial implementation of `chat` and `plan` modes in [0030-operational-modes-and-plan-mode.md](../decisions/0030-operational-modes-and-plan-mode.md), expand the operational mode set to include:
  1. `act`: Direct task execution; executes user commands and edits promptly without upfront planning cycles.
  2. `analyse`: Read-only workspace investigation; answers questions and analyzes code without modifying persistent files.
  3. `routing`: Uses a classifier model (such as Jev or an LLM wrapped in dedicated tools) to triage user input and dispatch to an appropriate operational mode.
  Switching between operational modes closes non-empty threads and opens a fresh thread (reusing empty initial threads).
- **Rationale**: Aligns agent behavior with specific user intents while using threads as deterministic boundaries between planning, discussion, analysis, and execution.
- **Provenance**: [0019-threads-modes-personas-architecture.md](../decisions/0019-threads-modes-personas-architecture.md), [0030-operational-modes-and-plan-mode.md](../decisions/0030-operational-modes-and-plan-mode.md), [threads_modes_personas.md](./threads_modes_personas.md), [REQ-025](./requirements.md#req-025-operational-modes-and-thread-transition-triggers), [INV-028](./invariants.md#inv-028-mode-transition-thread-spawning-boundary).


### Pluggable Agent Personas (Coder, Office Worker, Designer, etc.)
- **Description**: Support an extensible architecture for agent personas, with immediate near-term focus on the `Coder` persona to support self-hosting / dogfooding development (developing Seamus with Seamus), while supporting custom persona registration in the long term. Personas establish baseline `<identity>`, domain instructions, and specialized tool suites/backends (exact rules for persona switching/inheritance across sessions remain TBD).
- **Rationale**: Expands Seamus from a purely code-focused assistant into a versatile multi-domain autonomous harness while prioritizing autonomous coding for Seamus self-development.
- **Current State**: `AgentConfig.persona` (default `"coder"`) and `build_persona_identity` / `build_effective_system_prompt(persona=...)` are implemented; `tests/test_personas.py` covers the default Coder identity, custom instructions, and configurable persona selection (5 passing unit tests). Full pluggable persona registration and runtime switching rules remain future work.
- **Provenance**: [0019-threads-modes-personas-architecture.md](../decisions/0019-threads-modes-personas-architecture.md), [threads_modes_personas.md](./threads_modes_personas.md), [REQ-024](./requirements.md#req-024-agent-personas-and-baseline-archetypes), `tests/test_personas.py`.


### Subagent Architecture: Prompts, Sandbox Isolation, and UI Representation
- **Description**: Investigate and define Seamus subagent integration using DeepAgents subagents (`SubAgentMiddleware` / `AsyncSubAgent`). Specifically determine:
  1. System prompt composition: whether subagents inherit parent workspace rules and engineering discipline or use specialized task prompts.
  2. Execution isolation: whether subagents operate in the parent session's container workspace or spin up isolated workspace subtrees/ephemeral containers.
  3. UI visualization: design how delegated subagent runs, parallel executions, and returns are rendered in the SPA (e.g., collapsible child execution cards within the chat bubble or dedicated sub-threads).
- **Rationale**: Delegation to specialized subagents is central to autonomous harness scaling; clear execution boundaries and user visibility must be established before enabling subagents.
- **Provenance**: `src/seamus/harness/runner.py`, `deepagents.middleware.subagents`, [abstractions.md](./abstractions.md).



### Minimalistic Dashboard View for Agents and Sessions
- **Description**: Implement an alternative, lightweight "Dashboard" view alongside the rich developer/IDE-like navigation tree and inspector:
  1. Plain agent grid: Displays all configured agents as a clean, uncluttered card grid.
  2. Session grid: Selecting an agent transitions to a grid of its sessions. Each session card displays rows showing a `(...)`-collapsed preview of the last couple task/thread names.
  3. Seamless view transitions: Provides a quick, distraction-free conversational interface for goal-oriented interaction, with prominent links to navigate into the "hydrated" developer/IDE view when in-depth runtime inspection or advanced configuration is required.
- **Rationale**: Accommodates both lightweight conversational workflows focused on getting tasks done and deep engineering/debugging sessions requiring full inspectability.
- **Provenance**: [0003-react-web-ui.md](../decisions/0003-react-web-ui.md), [architecture.md](./architecture.md#system-overview).


## Deferred

### Agent Slug Sync to Gitea Organization Full Name
- **Description**: When a slug or custom name is assigned to an agent (by user edit or automated daemon), update the Gitea organization's full name (`full_name`) to match that slug, while retaining the immutable `agent-{agent_id.hex}` org username.
- **Why Deferred**: Core persistence functions using the immutable `agent-{agent_id.hex}` identifier. Org display name synchronization is a cosmetic metadata enhancement on the Gitea UI.
- **Revisit Trigger**: When agent slug editing or automated daemon slug assignment is hooked up to external companion link naming and Gitea profile visibility.
- **Provenance**: [0068-organization-and-session-gitea-layers.md](../decisions/0068-organization-and-session-gitea-layers.md), `src/seamus/persistence/workspace.py`.

### Teams and Branch Protection within Agent Organizations
- **Description**: Create dedicated teams (e.g., `owners`, `agents`, `reviewers`) and configure branch/PR protection rules within each agent's Gitea organization (`agent-{agent_id.hex}`). This closely connects with dedicated Gitea user accounts per agent/persona.
- **Why Deferred**: Seamus operates with a single configured Gitea service user. Multi-user RBAC and branch protection require dedicated Gitea credential management.
- **Revisit Trigger**: When multi-agent collaboration, fine-grained access control, or strict branch protection policies on `agent` and `session-*` repos are implemented.
- **Provenance**: [0068-organization-and-session-gitea-layers.md](../decisions/0068-organization-and-session-gitea-layers.md).

### Project Sync for Mounted External Repositories
- **Description**: Add a project sync workflow for external mounted repositories that: (1) triggers a manual pull mirror sync from upstream to `mirrors/project-{name}-{hash}`, (2) pulls new commits from mirror to the session-specific fork (`agent-{hex}/project-{name}-{hash}-{session_hash}`), and (3) pulls from the fork into the sandbox working copy `/projects/{mount_name}`.
- **Why Deferred**: Background automatic pull mirror syncs (`mirror_interval: "10m"`) keep mirrors up to date without manual intervention. On-demand sync requires triggering Gitea mirror sync API (`/repos/{owner}/{repo}/mirror-sync`) followed by Git fetch/merge between mirror and fork.
- **Revisit Trigger**: When an agent or user explicitly requests fetching the latest upstream commits into an active session working copy mid-session.
- **Provenance**: [0068-organization-and-session-gitea-layers.md](../decisions/0068-organization-and-session-gitea-layers.md), `src/seamus/persistence/external_repo.py`.

### Unarchiving Features for Agents and Sessions
- **Description**: Support reversing archived agents and sessions (unarchiving in Gitea by renaming `archived-agent-...` back to `agent-...` or clearing `archived: false` on session repositories and mount forks, and re-hydrating into active store).
- **Why Deferred**: Archival currently focuses on cleanly hiding finished or dead projects and freeing resources without destroying history; unarchiving requires a dedicated archive-browser UI and restore workflow.
- **Revisit Trigger**: When users require browsing, inspecting, or restoring historical archived projects from the UI.
- **Provenance**: [0069-archive-and-delete-lifecycle.md](../decisions/0069-archive-and-delete-lifecycle.md), `src/seamus/harness/store.py`, `src/seamus/persistence/client.py`.

### Granular Deletion and Archival Permissions
- **Description**: Provide fine-grained control over archive and delete capabilities in system settings (e.g. allowing session deletion while forbidding agent deletion, or adding an explicit toggle for archiving).
- **Why Deferred**: The global `enable_delete` boolean in `SystemSettings` sufficiently prevents accidental hard deletion across all entities for single-operator workflows.
- **Revisit Trigger**: When multi-user roles, operator guardrails, or more granular repository governance policies are needed.
- **Provenance**: [0069-archive-and-delete-lifecycle.md](../decisions/0069-archive-and-delete-lifecycle.md), `src/seamus/config/settings.py`.

### Backend Enforcement of `enable_delete` Setting on DELETE Endpoints
- **Description**: If the system settings flag `enable_delete` is `false`, calling any HTTP `DELETE` endpoint (`DELETE /api/v-alpha/agent/{id}` or `DELETE /api/v-alpha/agent/{id}/session/{id}`) should be rejected with an HTTP 400 Bad Request error rather than executing the deletion. Currently, `enable_delete` gates UI button visibility in the navigation tree, but the backend endpoints remain reachable directly via API.
- **Why Deferred**: In a single-operator environment, the client-side UI gate and confirmation dialogs prevent accidental deletion. Direct unauthorized curl/API requests represent a low probability outside malicious or rogue clients.
- **Revisit Trigger**: When hardening security boundaries for multi-user or exposed environments.
- **Priority**: Medium priority (high impact if triggered accidentally via API, low chance of happening outside of malicious users).
- **Provenance**: [0069-archive-and-delete-lifecycle.md](../decisions/0069-archive-and-delete-lifecycle.md), `src/seamus/server/routes/agents.py`, `src/seamus/server/routes/sessions.py`.

### Agent Work and Time Tracking Across Repositories
- **Description**: Provide work and time tracking where the agent (or harness telemetry) tracks and reports how much active working/execution time was spent in specific repositories. Leverage Gitea's native time-tracking APIs (`/repos/{owner}/{repo}/issues/{index}/times`) and PR/issue integration to associate agent labor and turn iterations with repository deliverables and milestones.
- **Why Deferred**: Core harness execution and repository persistence prioritize accurate deliverable snapshotting and sandboxing. Time metrics and Gitea time tracking integration represent an auxiliary project management and accounting layer.
- **Revisit Trigger**: When multi-agent cost accounting, task-level time audits, or project progress tracking across mounted repositories is required.
- **Provenance**: [0068-organization-and-session-gitea-layers.md](../decisions/0068-organization-and-session-gitea-layers.md), `src/seamus/persistence/client.py`.

### Optional Persistence of Steerable Model Queues
- **Description**: Optionally persist steerable model response queues (for example under `<session_workspace>/data/steerable/<instance_id>.json`, committed alongside session state) so that a scripted session survives a backend restart and its queue becomes visible in the Changes diff view. The queue is currently held in memory in the process-wide steerable registry only, so a restart discards it and the session must be re-armed. The Inspector's queue export/import covers the manual case (download a queue as JSON, upload it into another session), but not automatic, session-scoped persistence.
- **Why Deferred**: The queue is a live steering surface for the current process. Persisting it would require resolving the same multi-worker consistency caveats the in-memory store already carries (see the technical-debt entry on in-memory store state isolation), and Git-backed persistence would commit what is essentially scratch state into the session history.
- **Revisit Trigger**: When scripted sessions need to survive backend restarts, or when the same scripted scenario must be replayed across processes. The end-to-end suite added in [0057-e2e-test-suite.md](../decisions/0057-e2e-test-suite.md) runs in-process and therefore does not require persistence; cross-process replay remains the open case.
- **Provenance**: [0056-steerable-model-provider.md](../decisions/0056-steerable-model-provider.md), [0057-e2e-test-suite.md](../decisions/0057-e2e-test-suite.md), `src/seamus/harness/steerable.py`.

### Automated Plan Cleanup & Task Pruning Tool
- **Description**: Add a specialized planning maintenance tool (e.g. `clean_todo_plan` / `prune_todos`) that automatically garbage-collects completed subtrees, purges abandoned tasks, and compacts the active task tree to conserve context tokens in long multi-turn sessions.
- **Why Deferred**: The core planning toolset (`create_todo_item`, `edit_todo_item`, `delete_todo_item`) fully supports explicit task management and deletion. Automated pruning and garbage-collection policies require additional heuristics to ensure users and agents do not lose necessary audit context mid-session.
- **Revisit Trigger**: When long, complex execution sessions with extensive task breakdowns produce bloated `<plan>` prompt sections that exceed token budgets.
- **Provenance**: [0049-native-lmxml-todo-planning.md](../decisions/0049-native-lmxml-todo-planning.md).

### Session-Level Task Plans vs. Thread-Scoped Plans
- **Description**: Investigate promoting hierarchical task plans from thread-scoped collections (`thread.todos`) to session-level entities (`session.todos` or dedicated plan entity).
- **Why Deferred**: Scoping todos to the thread aligns with `active_skills` and keeps thread contexts clean across operational mode changes. Cross-thread plan sharing requires formal migration and synchronization protocols.
- **Revisit Trigger**: When multi-thread workflows (such as switching from `plan` mode to `act` mode across thread boundaries) frequently require continuing the same structured todo checklist without re-creating it.
- **Provenance**: [0049-native-lmxml-todo-planning.md](../decisions/0049-native-lmxml-todo-planning.md), [0019-threads-modes-personas-architecture.md](../decisions/0019-threads-modes-personas-architecture.md).

### Daemon Manifest Normalization, Generic Event Filters, and Custom Selection Strategies
- **Description**: Extracting and normalizing daemon manifests, defining arbitrary trigger event types and filter pipelines, and supporting customizable daemon execution selection strategies beyond the initial geometric step-off ($2^k - 1$).
- **Why Deferred**: One-shot daemons are currently scoped specifically to thread and session naming using fixed geometric stepback and user-turn boundaries, keeping the engine minimal and focused.
- **Revisit Trigger**: When additional background daemon capabilities are introduced (e.g. summarization, tag extraction, memory compaction) requiring varied trigger events and custom scheduling algorithms.
- **Provenance**: [0046-daemons-naming.md](../decisions/0046-daemons-naming.md).

### GPU Passthrough Acceleration for Containerized Ollama
- **Description**: Add GPU acceleration support (e.g. NVIDIA Container Toolkit `--gpus all` directives in `docker-compose.yml` or ROCm runtime for AMD) and direct host socket bridging for Ollama inference in Seamus.
- **Why Deferred**: Running Ollama in CPU mode via containerized `ollama/ollama:latest` on the internal Docker network provides out-of-the-box local inference without requiring host GPU drivers, CUDA setups, or NVIDIA Container Toolkit installation.
- **Revisit Trigger**: When executing larger parameter models (e.g. 20B+) or when users require hardware-accelerated local inference for reduced turn latency.
- **Provenance**: [0045-ollama-local-model-provider.md](../decisions/0045-ollama-local-model-provider.md), `docker-compose.yml`.

### Multi-Thread Conversational History Inclusion Strategy
- **Description**: Expand thread history overlap beyond the immediate predecessor thread (`currentSession.threads[-1].messages[-n:]`) to a multi-thread sliding window budget across all historical session threads. For example, budgeting up to 20 messages total from prior threads across arbitrary thread boundaries (e.g., 10 from $T_1$, 7 from $T_2$, 3 from $T_3$ when initializing $T_4$).
- **Why Deferred**: Seeding the last $N$ messages from the immediate preceding thread is simple, deterministic, and sufficient for the initial implementation before building multi-thread aggregation and token budgeting algorithms.
- **Revisit Trigger**: When multi-phase sessions span several short threads (e.g. rapid mode toggling or brief review threads) where context from older threads is lost with single-predecessor overlap.
- **Provenance**: [0019-threads-modes-personas-architecture.md](../decisions/0019-threads-modes-personas-architecture.md), `knowledge/backlog.md`.

### Alternative Button Action Level Notations in Artifact Manifests
- **Description**: Experiment with consolidated or level-based notations for manifest button configurations (e.g. `someLevelName = data | unblocking | closing`) rather than discrete orthogonal boolean flags (`unblocking: bool`, `closing: bool`).
- **Why Deferred**: Independent boolean flags (`unblocking: bool = False`, `closing: bool = False`) are explicit, orthogonal, and simple to validate in early iterations.
- **Revisit Trigger**: When authoring experience reveals repetitive button configuration patterns across custom artifacts.
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

### Custom Interactive Artifact Authoring
- **Description**: Provide advanced agent workflows and templates for authoring custom multi-surface A2UI interactive artifacts via `make_artifact` with arbitrary button hierarchies and state models under `/artifacts/custom/`. Note: pre-render surface validation (`validate_a2ui_surface`) was established in [0037-validate-a2ui-surface-render-on-make-artifact.md](../decisions/0037-validate-a2ui-surface-render-on-make-artifact.md), root container auto-synthesis with static structure warnings in [0038-a2ui-root-component-and-incomplete-structure-warning.md](../decisions/0038-a2ui-root-component-and-incomplete-structure-warning.md), and loose normalization with mutation log feedback in [0039-loose-artifact-normalization-and-mutation-log.md](../decisions/0039-loose-artifact-normalization-and-mutation-log.md).
- **Why Deferred**: Prioritized specialized, validated artifact families (questionnaires, forms, plans) to establish disk structure and rendering contracts before opening raw artifact creation.
- **Revisit Trigger**: When introducing custom agent generative UI authoring workflows.
- **Provenance**: [0034-mature-a2ui-artifacts-model.md](../decisions/0034-mature-a2ui-artifacts-model.md), [0037-validate-a2ui-surface-render-on-make-artifact.md](../decisions/0037-validate-a2ui-surface-render-on-make-artifact.md), [0038-a2ui-root-component-and-incomplete-structure-warning.md](../decisions/0038-a2ui-root-component-and-incomplete-structure-warning.md), [0039-loose-artifact-normalization-and-mutation-log.md](../decisions/0039-loose-artifact-normalization-and-mutation-log.md), [artifacts.md](./artifacts.md).

### Pushing External Repository Semantic Commits Back to Remote Upstream
- **Description**: Provide an explicit mechanism, command, or agent tool for pushing semantic commits created on `/projects/{mount_name}` back to the remote upstream repository (e.g., creating feature branches and opening pull requests on GitHub or GitLab).
- **Why Deferred**: External repositories are currently cloned and checkpointed into internal Gitea storage (`project-{project_id}`). Upstream push integration requires managing push credentials and remote PR lifecycle management.
- **Revisit Trigger**: When agents are tasked with publishing completed features directly to remote upstream hosts.
- **Provenance**: [0042-mount-external-git-repositories.md](../decisions/0042-mount-external-git-repositories.md).

### Extended Manual Testing of External Git Mounts (Especially Multiple Concurrent Mounts)
- **Description**: Conduct comprehensive manual end-to-end testing of external repository mounting across edge cases:
  1. Multiple concurrent mounts in a single session (including naming collisions producing `_0`, `_1` suffixes).
  2. Large upstream repositories (multi-gigabyte histories, binary objects, deeply nested directory structures).
  3. Concurrent sessions sharing the same underlying Gitea mirror repository (`project-{project_id}`).
  4. Dynamic unmounting, remounting, and branch reconfiguration mid-session.
  5. Multi-repo checkpointing performance and atomic rollback if one repository fails to snapshot.
- **Why Deferred**: Core dual-index snapshotting, URL derivation, Gitea mirroring, and single-mount execution were verified through automated unit tests (`tests/test_external_repos.py`) and single-repo manual verification. Extended manual scenarios require setting up multiple mock/real remote repositories with varying commit topologies and stress-testing container I/O.
- **Revisit Trigger**: Before running production agents tasked with complex, multi-repository monorepo or microservice refactorings.
- **Provenance**: [0042-mount-external-git-repositories.md](../decisions/0042-mount-external-git-repositories.md), `tests/test_external_repos.py`.

### Granular Gitea Commit Authors, Organizations, and Team Ownership
- **Description**: All Git repositories created in Gitea are owned by the system service user `seamus`, and automated commits use the single author identity `Seamus Agent <agent@seamus.local>`. Per-agent, per-session, or per-user commit authors, organizations, and team permissions were postponed.
- **Why Deferred**: Kept persistence initialization and API interaction simple and single-tenant for early development.
- **Revisit Trigger**: When introducing multi-tenant support, team access controls, or distinct audit identities per agent or human turn.
- **Provenance**: [0008-git-persistence.md](../decisions/0008-git-persistence.md#8-deferred-tasks), [vocabulary.md](./vocabulary.md#agent-repository).

### Gitea Repository Branch Protection Rules
- **Description**: Configure branch protection rules on all agent and system Git repositories in Gitea to restrict direct pushes to session and main branches. Workspaces are not a freely accessible content base; all modifications must be authorized (such as administrator intervention or verified agent turns).
- **Why Deferred**: Core Git workflow, Sync PR lifecycle, and auto-pull mechanics were established first.
- **Revisit Trigger**: When multi-user authorization and branch governance are implemented.
- **Provenance**: [0008-git-persistence.md](../decisions/0008-git-persistence.md), [0026-in-sandbox-skill-mount-paths.md](../decisions/0026-in-sandbox-skill-mount-paths.md), [INV-036](./invariants.md#inv-036-purposeful-workspace-synchronization--auto-pull).

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

### Model Context Protocol (MCP) Client and Subprocess Server Integration
- **Description**: Add MCP client capabilities to Seamus agents.
  > [!IMPORTANT]
  > MCP support requires not only connecting over remote HTTP/SSE transports to external services, but orchestrating local stdio subprocess servers, managing server process lifecycles and environment variables, and configuring scoped local filesystem access boundaries safely.
- **Why Deferred**: Native tools, OpenSandbox container execution, and bundled skills cover current capabilities cleanly; protocol integration and local stdio process orchestration add substantial runtime surface.
- **Revisit Trigger**: When external tools or data sources required by Seamus agents are exposed primarily as MCP servers, or when users request running local stdio-based MCP servers alongside agent sandboxes.
- **Provenance**: `src/seamus/harness/runner.py`, `knowledge/backlog.md`.

### Modular Disablement of Harness Layers and Components
- **Description**: Provide fine-grained switches to disable specific harness subsystems (e.g. context compaction, specific artifact types) while retaining generic capabilities. Note: artifacts subsystem disablement (`artifacts_implementation = none | seamus`) was implemented in [0055-artifacts-implementation-toggle.md](../decisions/0055-artifacts-implementation-toggle.md) and [REQ-050](./requirements.md#req-050-configurable-artifacts-implementation-toggle--gating-guard).
- **Why Deferred**: Subsystems currently have unified configuration toggles; granular layer-by-layer disablement requires deep modularization.
- **Revisit Trigger**: When custom deployment profiles require stripping down harness capabilities to minimal subsets.
- **Provenance**: `knowledge/backlog.md`.

## Technical debt

### Ambiguity in Git Credentials Selection for Gitea Mirrors vs. Per-Agent Config
- **Current Problem**: Gitea pull mirrors in the system-wide `mirrors` organization may require Git credentials to mirror private upstream repositories. Currently, `credentials_ref` is configured per agent / session in `ExternalRepositoryConfig`. However, mirrors are system-wide downstream copies shared across multiple agents. It is therefore ambiguous which agent's credentials should be used when provisioning or syncing the system-wide mirror, or how credentials should be updated if multiple agents configure the same upstream repository with different or rotating credentials.
- **Improvement**: Evolve toward a structured, harness-level credentials store where Seamus tracks which credentials to use for specific external systems, Git hosts, and domains, rather than injecting per-agent secret references directly into individual repository configurations.
- **Provenance**: [0068-organization-and-session-gitea-layers.md](../decisions/0068-organization-and-session-gitea-layers.md), `src/seamus/persistence/external_repo.py`, `src/seamus/config/models.py`.

### Thorough Security Review and Hardening of MVP OpenBao Secrets Integration
- **Current Problem**: The initial OpenBao integration is an MVP design: `openbao-init` initializes a single-share unseal key and root token stored in the shared `openbao-auth` volume (`/var/run/seamus-openbao`), the backend authenticates using this root token, and `/api/v-alpha/vault/token` exposes the login token to the UI for convenience.
- **Improvement**: Conduct a comprehensive security review and hardening pass on the OpenBao integration: replace root token usage in the backend with scoped AppRole/token policies, evaluate auto-unseal mechanisms or KMS integration instead of plaintext unseal key storage on a Docker volume, restrict token exposure endpoints, enable TLS, and audit secret interpolation boundaries so resolved secrets cannot be exfiltrated via prompt injection or error logs.
- **Provenance**: [0041-openbao-secrets-vault-integration.md](../decisions/0041-openbao-secrets-vault-integration.md), `openbao/init.sh`, `src/seamus/vault/`, `src/seamus/server/routes/vault.py`.

### Session Branching Interaction with Session-Local Non-Blocking Artifacts and Multi-Repo Git Mounts
- **Current Problem**: Session branching (`branch_session`) copies thread checkpoint history and Git commits from a specific parent assistant turn. However, non-blocking artifacts (such as `plan`) and session-level directories (such as notes and specs in `/workspace`) are session-scoped and encompass multi-turn, multi-phase exchanges. In addition, when future multi-repository mounts are introduced, multiple Git repositories must remain synchronized across branches, phases, and thread checkpoints. We need to rethink and review how session branching, session-local non-blocking artifacts, and multi-repo Git mounts interact safely without orphaned artifacts, desynchronized working trees, or broken plan lineage.
- **Improvement**: Formally model artifact provenance and multi-repo checkpoint synchronization in `branch_session`, ensuring child branched sessions cleanly copy or fork active plan artifacts and multi-mount Git states without conflicting with the parent session.
- **Provenance**: [0030-operational-modes-and-plan-mode.md](../decisions/0030-operational-modes-and-plan-mode.md), `src/seamus/harness/runner.py`, `src/seamus/persistence/workspace.py`.

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
- **Current State**: Largely addressed by [0057-e2e-test-suite.md](../decisions/0057-e2e-test-suite.md). `tests/e2e/test_session_lifecycle.py` now covers sandbox teardown on kill, rejection of further input on a terminal session, mode-switch rejection on a terminal session, branch-before/branch-after slicing, multi-level lineage chains, mode/phase preservation across branches, and thread acceptance spawning a successor. *Mid-turn* cancellation is covered at unit level by `tests/test_session_branching_and_lifecycle.py::test_kill_session_mid_tool_cleans_up_and_errors` and `::test_kill_session_while_thinking_cleans_up_and_errors`, which assert the interrupted `TOOL_CALL_RESULT` (`is_error=True`) and the `RUN_ERROR` event described in [INV-029](./invariants.md#inv-029-session-terminal-immutability--resource-teardown). What remains uncovered is mid-turn cancellation *through the HTTP surface* (the e2e suite kills a session between turns, not during an in-flight tool call) and Gitea branch consistency during rapid branching.
- **Provenance**: [0022-branching-out-and-session-lifecycle.md](../decisions/0022-branching-out-and-session-lifecycle.md), [0057-e2e-test-suite.md](../decisions/0057-e2e-test-suite.md), `tests/e2e/test_session_lifecycle.py`.

### Rigorous and Detailed Automated Testing Matrix for Granular Bidirectional Session Branching
- **Current Problem**: While initial unit tests cover basic granular branching slice points (`before` / `after` across user messages, system events, bot messages, thinking, and tool groups) in `tests/test_session_branching_and_lifecycle.py`, branching mechanics remain fragile and undertested under real-world usage. Edge cases around multi-level cascading branches ($S_1 \to S_2 \to S_3$), rapid branching during active LLM/tool execution, complex multi-part message histories, Git commit alignment across dirty/uncommitted workspaces, mode/phase continuity across deep branch trees, and UI indicator rendering across varied sequence topologies are not yet exhaustively covered by automated integration tests.
- **Improvement**: Build a comprehensive, heavy automated test matrix exercising granular bidirectional session branching:
  1. Multi-level nested branching chains with mixed `before` and `after` operations verifying event slices, lineage preservation, and provenance tracking.
  2. Branching during active stream generation and mid-turn execution, verifying cancellation, thread status resolution (`AWAITING_USER` vs `AWAITING_LLM`), and sandbox consistency.
  3. Git workspace and Gitea PR synchronization across branched sessions with dirty working directories, external repository mounts, and custom commit topologies.
  4. End-to-end UI component testing for `MessageItem`, `ChatArea`, and `BubbleBranchActions` covering braced tool groups, odd/even call distributions, indicator line placements, and sequence index recalculations.
- **Current State**: Items 1 and 4 are addressed by [0057-e2e-test-suite.md](../decisions/0057-e2e-test-suite.md): `tests/e2e/test_session_lifecycle.py` covers multi-level lineage chains and mode/phase continuity across branches, and `ui/tests/messageItem.test.mjs` covers `BubbleBranchActions`, `BranchProvenanceSeparator`, `ToolGroupProvenanceIndicator`, and `SyntheticMessageBlock` rendering. Items 2 and 3 remain open — branching during active stream generation and Git/Gitea synchronisation across branched sessions with dirty working directories and external repository mounts are still untested end to end.
- **Provenance**: [0054-granular-bidirectional-session-branching.md](../decisions/0054-granular-bidirectional-session-branching.md), [0057-e2e-test-suite.md](../decisions/0057-e2e-test-suite.md), `src/seamus/harness/store.py`, `ui/src/components/MessageItem.tsx`, `ui/src/components/ChatArea.tsx`.

### Review and Rethink Error Reporting Architecture and Semantics
- **Current Problem**: Error reporting across the harness stack is unclear and fragmented. Errors originating from tool execution (e.g. argument validation or duplicate question IDs in `ask`), sandbox execution, runner loops, and SSE event streaming (`RUN_ERROR` vs `TOOL_CALL_RESULT` with `is_error=True`) lack a clear taxonomy, consistent propagation rules, and transparent visibility in both agent reasoning context and frontend user feedback.
- **Improvement**: Review and redesign error reporting systematically: define distinct error categories (recoverable tool feedback intended for model correction vs fatal harness/system faults), establish consistent propagation through SSE events and thread status, and provide clear, actionable error indicators in the web UI.
- **Current State**: `tests/e2e/test_error_diagnostics.py` covers `RUN_ERROR` recording, `error_type` and `traceback` persistence and SSE streaming, and `ERROR` status transitions end-to-end (5 passing tests). The broader taxonomy review across recoverable tool feedback vs fatal faults remains open.
- **Provenance**: `src/seamus/harness/runner.py`, [0031-SUPERSEDED-migrate-a2ui-to-adaptive-cards.md](../decisions/0031-SUPERSEDED-migrate-a2ui-to-adaptive-cards.md), [architecture.md](./architecture.md), `tests/e2e/test_error_diagnostics.py`.

### Artifact Lifecycle and Retention During Thread Acceptance
- **Current Problem**: Accepting a thread (`accept_thread`) explicitly closes `session.active_plan_id`, but other artifacts (questionnaires, forms, custom artifacts) and their interaction states lack a defined lifecycle: it is unclear whether unclosed artifacts should be forcibly closed, preserved, archived, or carried over into the new thread's workspace view.
- **Improvement**: Review and define formal closing, retention, and archiving rules for all artifact families upon Sync PR acceptance and thread transition.
- **Provenance**: `src/seamus/harness/store.py`, [artifacts.md](./artifacts.md), `src/seamus/domain/artifacts.py`.

### Logfire Telemetry Span Hierarchy and HTTP Polling Noise Reduction
- **Current Problem**: Logfire telemetry traces do not properly reflect the nested hierarchy of agents, sessions, and threads as intended. Additionally, frequent HTTP GET polling requests (e.g. fetching agents trees, status, and health checks) pollute the trace view, and inspecting traces requires navigating to external SaaS dashboards rather than having an integrated local trace inspection experience.
- **Improvement**: Refine OpenTelemetry/Logfire context propagation to ensure child runner and tool spans cleanly nest under thread and session spans; exclude high-frequency polling GET endpoints in `instrument_fastapi(app, excluded_urls=...)`; and evaluate embedding a lightweight local trace/span viewer (e.g. Jaeger or OpenTelemetry UI) into the local `docker-compose` stack.
- **Provenance**: `src/seamus/telemetry.py`, `src/seamus/server/app.py`, `docker-compose.yml`.

### Persistence of Installed Sandbox Tooling and Environment State
- **Current Problem**: System packages, libraries, and tools installed by the agent during sandbox execution (e.g. via `apt`, `pip`, or `npm`) are ephemeral and discarded across container restarts. While the operational workspace files are persisted via Git, the execution environment state itself resets, breaking multi-turn agent workflows that depend on installed dependencies.
- **Improvement**: Ensure sandbox environment state and installed tooling persist across session turns and container restarts, rather than resetting to a clean base image.
- **Provenance**: `src/seamus/harness/sandbox.py`, `src/seamus/harness/prompt.py`, `opensandbox/`.

### Config Model Modularization & Grouping
- **Current Problem**: `AgentConfig` in `src/seamus/config/models.py` has grown into a flat list of diverse concerns (inference, planning, skills, search, git mounts, daemons, sandbox image, rules, thread overlap) with fragile manual copying in `copy_with_overrides`.
- **Improvement**: Refactor `AgentConfig` into cohesive sub-models (e.g. `HarnessConfig`, `EnvironmentConfig`, `PlanningConfig`) and streamline override merging.
- **Provenance**: `src/seamus/config/models.py`, `ui/src/components/ConfigModal.tsx`.

### Backward Compatibility and Migration for Historical Pre-0071 Session Event Streams
- **Current Problem**: Historical sessions generated prior to bubble aggregation standardization and paginated message slicing ([0071-paginated-chat-scroll-and-memory-limits.md](../decisions/0071-paginated-chat-scroll-and-memory-limits.md)) may have stored disparate raw event shapes or un-indexed bubble chunks in Gitea checkpoint history, causing irregular initial rendering or pagination cursor mismatch when re-opened in the modernized UI.
- **Improvement**: Add a resilient backward-compatibility fallback / migrator in `aggregate_events_to_chat_messages` that gracefully synthesizes missing IDs and part wrappers for legacy event records so historical pre-0071 sessions load cleanly without requiring fresh session re-creation.
- **Provenance**: [0071-paginated-chat-scroll-and-memory-limits.md](../decisions/0071-paginated-chat-scroll-and-memory-limits.md), `src/seamus/harness/messages.py`, `ui/src/hooks/useThreadStream.ts`.

## TODO

### Gitea Repository Feature Flags, Healthchecks, Protection Rules, and Merge Styles
- **Description**: Review and configure repository-level capabilities across the multi-layer Gitea topology:
  1. For downstream pull mirrors in the `mirrors` organization: explicitly disable the issue tracker (`has_issues=false`), time tracking (`has_track_times=false`), and wiki (`has_wiki=false`) via Gitea API.
  2. For state repositories (`agent` baseline and `session-*` session repos): review these feature flags (determine whether issues, time tracking, or wiki are beneficial for agent memory or audit trails).
  3. Repository healthchecks: evaluate setting up automated Gitea repository healthchecks and maintenance tasks (e.g. `git gc` or mirror check hooks).
  4. Rules and merge styles: review branch protection rules, push protections, and allowed merge styles (e.g. merge commit vs squash vs rebase) on `agent` and `session-*` repos to align with automated cross-fork Sync PRs and clean deliverable tracking.
- **Rationale**: Keeps mirrors clean and lightweight without confusing dormant issue trackers, while securing state repositories and ensuring predictable merge behavior during thread acceptance.
- **Provenance**: [0068-organization-and-session-gitea-layers.md](../decisions/0068-organization-and-session-gitea-layers.md), `src/seamus/persistence/client.py`, `src/seamus/persistence/workspace.py`.

### End-to-End Coverage of Real Sandbox Container Provisioning
- **Description**: The e2e suite substitutes an in-process stub for the OpenSandbox container, so real container provisioning, the `/workspace` ↔ `data/` mount, and the read-only `plan/make` mount policy are never exercised against a live container. Add a container-backed e2e job (or an opt-in test tier) that provisions a real sandbox and asserts the mount layout and write rejection.
- **Rationale**: The stub enforces the read-only rule but does not prove the production backend does. `tests/test_sandbox.py` covers the backend against a mocked OpenSandbox API, which leaves the seam between the backend and a real container untested.
- **Provenance**: [test_coverage.md](./test_coverage.md), [REQ-017](./requirements.md#req-017-containerized-opensandbox-execution--operational-directory-mount), [INV-041](./invariants.md#inv-041-operational-mode-mount-policy-non-blocking-tabbed-plans-and-recursion-limit), `src/seamus/harness/sandbox.py`.

### Extract Pure Event Reducer from `useThreadStream` for Direct Unit Testing
- **Description**: `ui/tests/chatArea.test.mjs` exercises `useThreadStream` indirectly through `ChatArea` and a scripted SSE `fetch` stub. Extract a pure state-reduction function for AG-UI event sequences (streaming deltas, tool calls, reasoning chunks, `RUN_ERROR`, reconnects, and malformed frames) out of `ui/src/hooks/useThreadStream.ts` and cover every transition directly in `ui/tests/`.
- **Rationale**: Recorded during [0058-coverage-baseline-and-tiering.md](../decisions/0058-coverage-baseline-and-tiering.md) when production refactors were kept out of scope; separating pure reduction from React hook wiring enables deterministic edge-case testing.
- **Provenance**: [0058-coverage-baseline-and-tiering.md](../decisions/0058-coverage-baseline-and-tiering.md), [test_coverage.md](./test_coverage.md), `ui/src/hooks/useThreadStream.ts`, [REQ-032](./requirements.md#req-032-ui-url-state-synchronization-live-refresh-and-verbose-error-diagnostics).

### Tool Card Header Layout and Label Overflow in Agent Inspector
- **Description**: Fix formatting and wrapping of semantic tool labels in the Agent Inspector tool cards (`AgentInspector.tsx` and `App.css`). Ensure multiple labels wrap gracefully within the card header boundary without overflowing into the card padding or overlapping the "View Schema" toggle button.
- **Rationale**: When multiple labels (e.g. `artifacts`, `harness`, `seamus`, `a2ui`) are attached to a tool card, flex header content can overflow beyond the header boundary on standard card widths.
- **Provenance**: `ui/src/components/AgentInspector.tsx`, `ui/src/App.css`.

### Agent Runtime Warnings Panel in Web UI
- **Description**: Add a runtime warnings panel or banner in the Web UI (and Agent Inspector) capturing and displaying non-fatal operational diagnostics. Candidate diagnostics include:
  1. Context discovery skips: files matched by `rules_patterns` that were skipped due to exceeding maximum size limits (e.g. > 1 MB) or failing UTF-8 binary decoding.
  2. Skill parser errors: malformed YAML frontmatter or unreadable `SKILL.md` documents.
  3. Secret resolution issues: missing or unreadable OpenBao symbolic secret references.
  4. Collision warnings: shadowed skills and project mount path collisions.
- **Rationale**: Currently non-fatal discovery and runtime issues are logged to server stderr/debug logs, which makes it hard for users in the browser to diagnose why a specific rule or skill was omitted.
- **Provenance**: [0047-discovered-context-and-project-skills.md](../decisions/0047-discovered-context-and-project-skills.md), `src/seamus/harness/prompt.py`.

### Polymorphic Input Request Specification for Predefined Artifact Builders
- **Description**: Rephrase atomic inquiry builders from `make_questionnaire(questions: list[Question])` to generalized polymorphic builders `make_...(items: list[InputRequest]) -> ...`, where `InputRequest = SingleChoiceQuestion | MultipleChoiceQuestion | OpenQuestion | ColorChoice | DateChoice | ...` (or alternatively modeling the `answers` property of `Question` as an extensible enum/union of input widgets).
- **Rationale**: Predefined artifact builders should accommodate a broader palette of input widgets (color pickers, date pickers, freeform text boxes, file uploads) beyond simple single/multiple-choice questions while preserving atomic generation.
- **Provenance**: [0034-mature-a2ui-artifacts-model.md](../decisions/0034-mature-a2ui-artifacts-model.md), [artifacts.md](./artifacts.md).

### A2UI Text Heading Variants Support (`h1`–`h5`) vs Normalization
- **Description**: `make_artifact` surface validation and normalization currently reject heading variants such as `variant: "h2"` / `"h3"` on `Text` components and rewrite them to `variant: "body"` with markdown heading syntax (`## ...`), despite `a2ui_components/SKILL.md` documenting `h1` through `h5` as valid. Align the A2UI validation schema, component normalization, and skill documentation so agents and builders can reliably author proper section headings without unexpected rewrites.
- **Rationale**: Agents attempting to structure complex multi-section forms or custom surfaces using standard A2UI heading variants encounter silent rewrites or validation friction. Harmonizing the schema and renderer ensures predictable typography and component declarations.
- **Provenance**: `src/seamus/harness/artifacts.py`, `src/seamus/skills/bundled/a2ui_components/SKILL.md`, [artifacts.md](./artifacts.md).

### Review and Audit Plan Mode Implementation
- **Description**: Conduct a thorough review and audit of the Plan mode and planner implementation (`PlanBuilder`, prompt composition, `make_plan` tool lifecycle, phase transitions, and UI presentation). In particular, evaluate whether the current A2UI structure and tool mechanics provide optimal model steerability, assess how user comments and section-level revisions should be incorporated, and review whether the prompt instructions and sandbox handoff (`/artifacts/plans/<id>/plan.md`) cleanly support execution across long tasks.
- **Rationale**: Plan mode was quickly composed across multiple iterations (initial mode scaffolding, Adaptive Cards migration, and A2UI decoupling). A dedicated review pass will consolidate lessons learned, eliminate residual rough edges, and prepare the foundation for rich plan commenting and section-level revisions.
- **Provenance**: [0030-operational-modes-and-plan-mode.md](../decisions/0030-operational-modes-and-plan-mode.md), [0034-mature-a2ui-artifacts-model.md](../decisions/0034-mature-a2ui-artifacts-model.md), [0033-decouple-plans-and-submissions-from-a2ui.md](../decisions/0033-decouple-plans-and-submissions-from-a2ui.md), `src/seamus/harness/artifacts.py`, `src/seamus/harness/prompt.py`.

### Configuration Synchronization (Template-to-Agent and Agent-to-Session)
- **Description**: Implement mechanisms to synchronize configurations across entity hierarchies:
  1. Template to Agent: Allow updating an agent's `config` from its base `ConfigTemplate`, propagating newly added settings, models, or defaults while preserving agent-specific overrides.
  2. Agent to Session: Provide an explicit sync or inheritance mechanism to propagate updated agent configurations down to existing active sessions, and ensure newly spawned sessions accurately reflect the latest agent configuration state.
- **Rationale**: Agents and sessions currently take snapshot copies of configs during creation. When a template or agent configuration is updated, existing downstream entities remain on stale configuration snapshots with no automated or selective synchronization path.
- **Provenance**: `src/seamus/config/models.py`, `src/seamus/domain/entities.py`, `src/seamus/server/routes/config.py`.


### Agent Artifacts Protocol and Dedicated UI Viewer Panel
- **Description**: Introduce an Artifacts abstraction for persistent, high-density outputs (plans, reports, architecture diagrams, code diffs, standalone scripts). Establish:
  1. Persistence: storage under `/workspace/.seamus/artifacts/` or extraction from structured tool calls / checkpoints.
  2. UI Experience: a dedicated Artifacts tab or split-pane viewer alongside Chat, Changes, and Inspector, supporting Markdown rendering, syntax highlighting, and export.
- **Rationale**: Keeps chat conversations clean and scannable while giving persistent, dedicated visibility to substantial engineering deliverables.
- **Provenance**: `ui/src/components/`, [abstractions.md](./abstractions.md), [architecture.md](./architecture.md).

### Thorough Security Review of Containerized OpenSandbox Server & Docker Socket Configuration
- **Description**: Perform an in-depth security review and hardening pass on the containerized `opensandbox-server` deployment (`opensandbox/Dockerfile`, `opensandbox/sandbox.toml`, and `docker-compose.yml`). Review the security implications of mounting `/var/run/docker.sock`, tighten `allowed_host_paths` in `[storage]`, evaluate Docker socket proxies or rootless/gVisor (`runsc`)/Kata isolation runtimes (`[secure_runtime]`), review container capability drops/seccomp/AppArmor profiles, and audit sandbox network egress policies and port range exposure.
- **Rationale**: Mounting `/var/run/docker.sock` and provisioning sibling containers grants privileged daemon control to the sandbox server; hardening these boundaries is critical before untrusted or multi-tenant workloads run in sandboxes.
- **Provenance**: [0010-opensandbox-filesystem-sandboxing.md](../decisions/0010-opensandbox-filesystem-sandboxing.md#5-containerized-local-opensandbox-server-opensandbox-docker-composeyml-runsh), [architecture.md](./architecture.md#component-boundaries).


### Automated Integration Tests for Gitea Docker Compose Stack
- **Description**: Existing test suites verify unit logic and persistence mechanics using mock clients and temporary Git directories. Add automated end-to-end integration tests that run against the live `docker-compose` environment (`backend`, `frontend`, `gitea`, `postgres`).
- **Rationale**: Validates actual HTTP interactions, Gitea API responses, and container volume persistence in CI/CD pipelines.
- **Provenance**: [0008-git-persistence.md](../decisions/0008-git-persistence.md), [conventions.md](./conventions.md#container-orchestration--launch-conventions).

### Robust Testing and Usability Hardening for Ollama Integration
- **Description**: Conduct comprehensive automated and manual testing of Ollama integration across realistic workloads, focusing on both edge-case reliability and developer usability:
  1. **Usability & UX**:
     - Provide visual UI indicators/progress states during slow model loading or downloading phases so users understand cold-start latency (especially for CPU execution of multi-gigabyte models like `gemma4:e4b`).
     - Surface clearer model download progress or timeout warnings in the UI instead of generic stream delays.
     - Explore dynamic enumeration and auto-completion of downloaded models directly by querying Ollama's `/api/tags` endpoint in the UI configuration modal.
  2. **Reliability & Edge Cases**:
     - Test behavior when Ollama runs out of memory (OOM), model loading times out, or the host/container daemon is killed mid-stream.
     - Test switching between cloud providers (e.g. OpenAI/OpenRouter) and local Ollama within the same session or across branched sessions.
     - Verify auto-pull behavior under network interruptions or invalid model tags.
     - Test concurrent sessions/threads hitting the local Ollama instance simultaneously and verify request queuing and CPU contention.
- **Rationale**: While baseline containerized execution, candidate endpoint probing, model pre-loading, and auto-pull work correctly, local inference introduces unique latencies and resource constraints. Usability enhancements and thorough test coverage will ensure seamless day-to-day developer workflows.
- **Provenance**: [0045-ollama-local-model-provider.md](../decisions/0045-ollama-local-model-provider.md), `src/seamus/harness/runner.py`, `ui/src/components/ConfigModal.tsx`.

### Full Auto-Restart and Execution Recovery on System Startup
- **Description**: Automatically detect in-flight or interrupted agent sessions upon harness server restart/startup, recovering execution from the latest checkpoint and auto-resuming the agent's run loop.
- **Rationale**: If the host or server container is restarted or killed mid-turn, active runs currently stall without resuming, requiring manual user intervention.
- **Provenance**: `src/seamus/harness/store.py`, `src/seamus/harness/runner.py`, `src/seamus/server/app.py`.

### Steerable Wait Timeout Editing in the Inspector
- **Description**: Expose the per-instance steerable `wait_timeout` in the Agent Inspector's "Steerable" section, next to the empty-queue strategy selector and the default-response field. The `PATCH .../strategy` route already accepts `wait_timeout`, and the API client already forwards it; only the Inspector control is missing, so the timeout is currently configuration-only.
- **Rationale**: The `wait` strategy blocks a model turn until a response is queued. With the timeout fixed at configuration time, a developer who steps away mid-turn cannot extend the wait from the UI, and the turn fails at an arbitrary point of the scenario.
- **Provenance**: [0056-steerable-model-provider.md](../decisions/0056-steerable-model-provider.md), `src/seamus/server/routes/sessions.py`, `ui/src/api/client.ts`, `ui/src/components/SteerableInspector.tsx`.

### Type-Specific Renderers in Session Changes Diff View
- **Description**: Extend the "Rendered" view mode in the Changes tab to support type-specific visual rendering: render A2UI `body.json` as live UI components, `manifest.json` as UI plus state inspection, and `.md` files as formatted markdown.
- **Rationale**: Diff inspections for UI surfaces and structured documentation are much more productive when viewed in their rendered form rather than raw JSON/Markdown diffs.
- **Provenance**: `ui/src/components/ChangesView.tsx`, [0015-session-changes-diff-tab.md](../decisions/0015-session-changes-diff-tab.md).

### Holistic Contextual Grounding for Plan Review Comments
- **Description**: When delivering user plan review feedback back to the agent in Plan/Make phase, structure the injected prompt to instruct the agent to evaluate line-anchored comments within the context of the entire implementation plan and architectural intent, rather than making myopic isolated edits.
- **Rationale**: Agents tend to fixate on the exact quoted snippet in review comments and disregard the surrounding plan structure.
- **Provenance**: `spike-plan-comments`, `src/seamus/harness/runner.py`.

### Plan Artifact Presentation & A2UI Surface Rendering Overhaul
- **Description**: Redesign the visual layout, typography, and component structure used when rendering implementation plans and translating the internal plan entity into A2UI surfaces, making plan reviews visually engaging and ergonomic.
- **Rationale**: The current plan artifact presentation is visually raw, unpolished, and difficult to scan during detailed architectural reviews.
- **Provenance**: `ui/src/components/PlanArtifactViewer.tsx`, `src/seamus/harness/artifacts.py`, [0030-operational-modes-and-plan-mode.md](../decisions/0030-operational-modes-and-plan-mode.md).

### Comprehensive Web UI Design System and CSS Architecture Overhaul
- **Description**: Undertake a comprehensive design review of the Web UI: harmonize color schemes, borders, elevations, component proportions, typography, and simplify the monolithic CSS layout in `App.css`.
- **Rationale**: Features and controls were added incrementally across dozens of spikes and tasks, resulting in visual drift and disjointed component styling.
- **Provenance**: `ui/src/App.css`, `ui/src/components/`.

### OpenRouter Session Telemetry, Generation ID Tracking, and Per-Turn Cost Accounting
- **Description**: Capture OpenRouter generation IDs from response envelopes, propagate session tracking metadata/headers to group requests on OpenRouter dashboards, and surface cumulative token usage and cost accounting in chat bubble inspection.
- **Rationale**: Enables accurate cost accounting and observability across multi-turn agent runs.
- **Provenance**: `src/seamus/harness/runner.py`, `ui/src/components/MessageItem.tsx`.

### Session Health Scoring and Automated Thrashing Safeguard
- **Description**: Track a dynamic session health score that decays on repeated tool errors or rapid identical tool calls and recovers over successful turns; pause execution and prompt the operator if health falls below an operational threshold. While fatal unhandled exceptions and persistent retry loops are managed by the Autocontinue Daemon ([0070-autocontinue-daemon.md](../decisions/0070-autocontinue-daemon.md)), this safeguard monitors in-turn non-fatal tool error spirals before an unhandled crash occurs.
- **Rationale**: Prevents agents from getting stuck in tight failure loops that consume tokens without making progress.
- **Provenance**: `src/seamus/harness/runner.py`, `src/seamus/telemetry.py`, [0070-autocontinue-daemon.md](../decisions/0070-autocontinue-daemon.md).

### Alternative Formatting and Presentation Formats in `answers.md`
- **Description**: Explore and evaluate alternative markdown representations for structured questionnaire and form responses in `answers.md`. In particular, test displaying multiple-choice sets and checkbox options explicitly showing both affirmative and negative selections (e.g. `<option label>: yes/no` or markdown task list checkmarks `- [x] <option>` / `- [ ] <option>`), tabular answer matrices, or grouped question sections.
- **Rationale**: The current format lists only selected options under blockquotes (`> <picked label>`). While concise, explicit boolean indicators (`<choice>: yes` vs `<choice>: no` or checkboxes) make it immediately clear to readers and LLMs which options were actively declined versus simply unselected.
- **Provenance**: [0053-artifact-event-snapshots-and-static-context.md](../decisions/0053-artifact-event-snapshots-and-static-context.md), `src/seamus/harness/artifacts.py`.

### Comprehensive Manual and Automated Testing of Autoretry / Autocontinue Daemon
- **Description**: Perform end-to-end manual and automated testing of the Autoretry / Autocontinue Daemon across a matrix of real-world and simulated error cases: transient network timeouts, rate limit spikes (429), fatal syntax/code execution exceptions, credit/quota exhaustion, and persistent multi-turn error loops. Verify the daemon input prompt structure, bubble boundary detection across diverse conversational trajectories (reasoning blocks, complex multi-tool calls, artifacts), branching recovery latency, and UI state consistency in the live environment.
- **Rationale**: While steerable unit and E2E simulation tests verify the core decision logic and bubble branching, real-world testing against actual LLM providers and live container environments ensures prompt effectiveness, model alignment across smaller daemon models (e.g. gpt-oss-20b vs gpt-oss-120b), and seamless human operator experience during automatic recoveries.
- **Provenance**: [0070-autocontinue-daemon.md](../decisions/0070-autocontinue-daemon.md), [0072-steerable-model-error-fixtures.md](../decisions/0072-steerable-model-error-fixtures.md), `src/seamus/harness/daemons/autocontinue.py`, `tests/e2e/test_autocontinue_daemon.py`.

## Not formalized

- pipeline fails on some swagger-related e2e tests??? [HIGHish]
- enhance the instructions to make sure that agent parallelizes tests and that it assumes master to be working properly

- deep-seamus variant of skills and todos: An intentional hybrid architecture combining DeepAgents execution and middleware mechanics with Seamus LMXML structured prompt composition (rather than raw markdown appending or vanilla prompt injection), intentionally kept outstanding.
- instructional documentation (as in "to achieve this do this")
- text field (the one for user message) is annoyingly small
- still some bullshit about branching indicator moving with new bubbles
- instruct the agent to prepare walkthrough artifact after implementation
- track errors (including failed tools) across sessions and agents, together with used model and other environmental factors; use to prepare hints for future usage, gauge model/task quality, etc
- another daemon that observes the inference message stream and calls todo-related tools for the agent after every nth message to keep the local plan up to date
- manual and automated testing of autoretry daemon


Way ahead:
- integrate with backlog.md or smth like that (in parallel to todo stack? as a separate todo impl?)
- add multimodality support

