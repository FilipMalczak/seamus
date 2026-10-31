# Backlog

Persistent record of work intentionally left outstanding across the project, maintained in accordance with [AGENTS.md](../AGENTS.md).

## Deferred

### Sandboxed Shell Execution and Execution Boundaries
- **Description**: Agent tool execution is currently confined to filesystem operations within `<session_workspace>/data/` via `FilesystemBackend(virtual_mode=True)`. General shell execution (e.g. arbitrary command execution) and dedicated sandboxed container boundaries for agent actions were deliberately postponed.
- **Why Deferred**: Scoped filesystem access provided a simple and sufficient boundary for early Gitea-backed persistence without introducing container-in-container or heavy execution sandbox complexity.
- **Revisit Trigger**: When extending agent tool capabilities to include shell commands, build tools, or untrusted code execution.
- **Provenance**: [0008-git-persistence.md](../decisions/0008-git-persistence.md#8-deferred-tasks), [INV-017](./invariants.md#inv-017-git-tracked-agent-workspace--config-boundary).

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

## TODO

### Dynamic Model Catalog and Dropdowns in UI Configuration Modals
- **Description**: The in-browser `ConfigModal` currently requires raw JSON editing for all configuration fields. Add structured input fields or dropdowns for supported model names and inference formats while preserving the raw JSON editing tab.
- **Rationale**: Reduces syntax errors and configuration friction when configuring agents and sessions.
- **Provenance**: [0003-react-web-ui.md](../decisions/0003-react-web-ui.md), [abstractions.md](./abstractions.md#ui-ui).

### Automated Integration Tests for Gitea Docker Compose Stack
- **Description**: Existing test suites verify unit logic and persistence mechanics using mock clients and temporary Git directories. Add automated end-to-end integration tests that run against the live `docker-compose` environment (`backend`, `frontend`, `gitea`, `postgres`).
- **Rationale**: Validates actual HTTP interactions, Gitea API responses, and container volume persistence in CI/CD pipelines.
- **Provenance**: [0008-git-persistence.md](../decisions/0008-git-persistence.md), [conventions.md](./conventions.md#container-orchestration--launch-conventions).

### Session Branch Merge and Pull Request Workflow
- **Description**: Agents currently commit state and workspace changes to isolated `session/{session_id}` branches. Add API endpoints and UI controls allowing users to review diffs, open pull requests, and merge/squash completed session work back into the agent `main` branch.
- **Rationale**: Enables human-in-the-loop approval and consolidation of agent deliverables into the agent baseline repository.
- **Provenance**: [0008-git-persistence.md](../decisions/0008-git-persistence.md#2-repository--branch-layout), [vocabulary.md](./vocabulary.md#session-branch).

