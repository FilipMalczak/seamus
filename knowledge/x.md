
# Architecture & Context Document: Workspace Management, Persistence, and Sandboxing in Seamus

This document provides a comprehensive technical overview of how workspaces, execution sandboxes, Git persistence, Gitea backing infrastructure, checkpoint commits, branching, merging, and synchronization operate in **Seamus**. It is prepared as context for designing and discussing **"Mounting Custom User-Provided Git Repositories in Sandbox"**.

---

## 1. System Philosophy & High-Level Architecture

Seamus is a deep agent harness engineered for developer ownership, full transparency, and sandboxed safety. Unlike harnesses that expose arbitrary host directories or maintain unversioned scratchpads, Seamus operates on strict architectural principles:

1. **The Workspace is Not a Loose Directory**: The workspace is a tightly version-controlled, auditable Git repository where every state transition, deliverable modification, and configuration tweak is persisted and delineated.
2. **First-Class Agent Repository**: Every agent owns a dedicated Git repository (`agent-{agent_id}`) hosted in a companion Gitea instance. This repository is the golden source of truth for the agent's configuration, conversational state, checkpoints, and deliverables.
3. **Execution Sandboxing Boundary**: Agents execute shell commands and file tools exclusively inside an isolated container ([`OpenSandbox`](https://github.com/AyushSonuu/langchain-sandbox-opensandbox)). Agents have zero filesystem visibility into internal repository metadata (`.git/`), configuration (`agent/config/`), or state trees (`agent/state/`).
4. **State vs. Deliverables Separation**: Internal runtime artifacts (LangGraph checkpoints, AG-UI event logs, message transcripts) are strictly separated from agent deliverables (`data/`). Base branches (`main`) only record verified deliverables.

```
+--------------------------------------------------------------------------------------------------+
|                                        SEAMUS PLATFORM                                           |
|                                                                                                  |
|   +--------------------+              HTTP / SSE               +-----------------------------+   |
|   |    React Web UI    |  <=================================>  |    FastAPI Backend Server   |   |
|   |  (Diffs, Inspector,|                                       |    (Stores, Run Loop,       |   |
|   |   Chat, Artifacts) |                                       |     Workspace Manager)      |   |
|   +--------------------+                                       +--------------+--------------+   |
|                                                                               |                  |
|                  +------------------------------------------------------------+                  |
|                  |                                                            |                  |
|                  v (Git CLI / REST API)                                       v (Docker Volumes) |
|   +-----------------------------+                            +-------------------------------+   |
|   |    Gitea Service (Forge)    |                            |     OpenSandbox Container     |   |
|   |                             |                            |                               |   |
|   |  * system (global configs)  |                            |  Mounts:                      |   |
|   |  * agent-{id} (dedicated)   |                            |  /workspace <--> data/        |   |
|   |    - main (deliverables)    |                            |  /artifacts <--> artifacts/   |   |
|   |    - session/{id} (branch)  |                            |  /skills/*  <--> skills/      |   |
|   +--------------+--------------+                            +-------------------------------+   |
|                  |                                                                               |
|                  v                                                                               |
|   +-----------------------------+                                                                |
|   |   PostgreSQL 16 Database    |                                                                |
|   +-----------------------------+                                                                |
+--------------------------------------------------------------------------------------------------+
```

---

## 2. Infrastructure & Backing Gitea Architecture

Persistence and forge operations are powered by self-hosted containerized infrastructure defined in `docker-compose.yml`:

- **Gitea Service (`gitea:3000` / host `localhost:3001`)**:
  - Chosen for its permissive MIT license (over copyleft alternatives).
  - Backed by **PostgreSQL 16 Alpine** (`postgres-data` persistent volume).
  - Stores all agent repositories and system configurations.
  - The Seamus backend does not use a relational ORM or database; it uses Gitea’s REST API and Git CLI working trees as its data persistence layer.
  - Initialized with an administrative service user (`seamus`). All automated commits currently use the single commit author identity: `Seamus Agent <agent@seamus.local>`.
- **System Repository (`system`)**:
  - A dedicated repository in Gitea containing:
    - `settings.json`: System-wide settings (e.g., system skill directories `~/.seamus/skills`, `~/.skills`).
    - `config-template.json`: The baseline template for newly created agents.
- **Agent Repositories (`agent-{agent_id}`)**:
  - Each agent maps 1:1 to a public Git repository named `agent-{agent_id}`.
  - Cloned locally on the backend filesystem under `SEAMUS_WORKSPACE_DIR` (default: `/app/workspaces` in Docker Compose via volume `backend-workspaces`, or `.seamus/workspaces` on host).

---

## 3. Repository Directory Layout & Branching Topology

Within each `agent-{agent_id}` repository, Seamus manages two tiers of branches: the long-lived base branch (`main`) and short-lived session branches (`session/{session_id}`).

```
<repo-root> (agent-{agent_id})
├── agent/
│   ├── config/
│   │   └── config.json          # AgentConfig, metadata, entity attributes, thread lists
│   └── state/
│       └── threads/
│           └── {thread_id}/
│               ├── events.json       # Ordered AG-UI event stream (messages, thoughts, tool calls)
│               ├── checkpoints.json  # Serialized LangGraph checkpoints, writes, blobs (HITL state)
│               ├── messages.json     # Human-readable conversation transcripts
│               ├── todos.json        # Active task list snapshots
│               └── pending_wait.json # Transient pause marker for UI artifact interactions
├── artifacts/                   # A2UI JSON schemas & state (questionnaires, forms, plans)
└── data/                        # The agent operational workspace (files created/modified by tools)
    ├── notes/                   # User and agent planning notes/specifications
    ├── skills/                  # Session-explicit custom skills
    └── .skills/                 # Session background/default skills
```

### Branch Responsibilities:

1. **`main` Branch**:
   - Represents the **accepted deliverables** of the project across all completed sessions.
   - Contains:
     - `agent/config/config.json`: The baseline Agent configuration (model parameters, persona, prompt overrides).
     - `data/`: Cumulative deliverables merged from accepted session threads.
     - `agent/state/.gitkeep` and `data/.gitkeep`.
   - **Crucial Rule**: `agent/state/` and session-specific `agent/config/` from active conversations **never** live on `main`.
2. **`session/{session_id}` Branch**:
   - Created whenever a new session begins (branched from `main` or from a historical commit in session branching).
   - Contains the live working copy of `data/`, the session’s specific `agent/config/config.json`, the full `agent/state/` for every thread executed in this session, and any interactive UI `artifacts/`.

---

## 4. Execution Sandboxing & Volume Mount Architecture (`OpenSandbox`)

Agents do not execute code or edit files in the backend host process. All execution is sandboxed using `SeamusOpenSandboxBackend` (wrapping `langchain-sandbox-opensandbox` / `opensandbox-server`):

1. **Zero-Trust Boundary**:
   - The sandbox container is launched as an isolated sibling container on the Docker daemon via `opensandbox-server` listening on `/var/run/docker.sock`.
   - An internal 256-bit cryptographic API key is generated dynamically on startup (`opensandbox-auth` volume) to protect the OpenSandbox REST API.
2. **Directory Mount Mapping**:
   Inside the sandbox container, the filesystem is mapped as follows:

| Host / Volume Path | In-Sandbox Path | Access Mode | Purpose |
| :--- | :--- | :--- | :--- |
| `{session_workspace}/data/` | `/workspace` | Read-Write (configurable) | The agent’s operational directory. All project code lives here. |
| `{session_workspace}/artifacts/` | `/artifacts` | Read-Only | Read access to generated A2UI schemas and manifests. |
| `{session_workspace}/data/notes/` | `/workspace/notes` | Read-Write or Read-Only | Specification and planning scratch space. |
| `bundled_skills/` (shared volume) | `/skills/bundled` | Read-Only | Immutable platform skills (e.g. `artifacts`, `a2ui_components`). |
| System skill directories (host) | `/skills/system/{idx}` | Read-Only | Ambient system-wide skills configured in system settings. |

3. **Storage Backing Modes**:
   - **Docker Compose**: Uses Docker named volume `seamus-workspaces` with subpaths:
     - `PVC(claimName="seamus-workspaces", subPath=f"{agent_id}/{session_id}/data")` mounted at `/workspace`.
   - **Local Host Mode**: Uses direct host bind mounts:
     - `Host(path=str(data_dir.resolve()))` mounted at `/workspace`.
4. **Agent Mental Model**:
   - The agent's dynamic system prompt explicitly informs it:
     *“Your operational directory is `/workspace`. Persistent files must be written here. All paths outside `/workspace` are ephemeral and discarded upon container termination.”*

---

## 5. Operational Modes & Dynamic Mount Policies

Seamus introduces operational modes (`Chat` vs. `Plan`) that dynamically alter the container mount permissions during runtime:

```
[Chat Mode]               --> /workspace is Read-Write
[Plan Mode (Discuss)]     --> /workspace is Read-Write (exploring codebase, taking notes)
[Plan Mode (Make Plan)]   --> /workspace is dynamically REMOUNTED Read-Only (tamper guard)
[Plan Mode (Execute)]     --> /workspace is dynamically REMOUNTED Read-Write (executing plan)
```

- When transitioning from `Discuss` to `Make`, `SeamusOpenSandboxBackend.reconfigure_mounts(workspace_readonly=True)` is called. If the sandbox is active, it is destroyed and reprovisioned with a read-only `/workspace` mount so the LLM cannot mutate project code while drafting a plan.
- Once the user clicks "Proceed" on the plan artifact, the runner switches to `Execute` phase, remounting `/workspace` as read-write.

---

## 6. Commit Lifecycle & Checkpointing Mechanics

Every change in Seamus is committed to Git using standardized commit message prefixes:

| Prefix | Target Branch | Trigger Point | Content Committed |
| :--- | :--- | :--- | :--- |
| `config:` | `main` or `session/{id}` | User updates agent or session settings via UI/API | `agent/config/**` |
| `checkpoint:` | `session/{id}` | LangGraph checkpoint written by `GitCheckpointSaver` | `data/`, `agent/state/`, `artifacts/`, `notes/` |
| `state:` | `session/{id}` | End of agent turn execution loop in runner | `agent/state/threads/{thread_id}/events.json` |
| `artifacts:` | `session/{id}` | Seeding default artifacts on workspace creation | `artifacts/` |
| `sync:` | `main` | Thread accepted by user; merges deliverables to base | `data/` deliverables only (2-parent merge) |

### The Checkpoint Commit Loop (`GitCheckpointSaver`):

1. As the agent reasons and executes tool calls, LangGraph calls `GitCheckpointSaver.put()` / `aput()`.
2. The checkpointer dumps:
   - Serialized state blobs/writes to `agent/state/threads/{thread_id}/checkpoints.json`.
   - Human-readable messages to `messages.json`.
   - Active todo items to `todos.json`.
3. It immediately calls `GitWorkspaceManager.commit_checkpoint_changes()`:
   - Runs `git status --porcelain -- data agent/state artifacts notes`.
   - If changes exist, executes:
     `git add -A -- data agent/state artifacts notes`
     `git commit -m "checkpoint: [session={session_id} thread={thread_id} checkpoint={cp_id}]"`
     `git push origin session/{session_id}`
4. **Auto-Rebase Resilience**: If the push is rejected because the remote was updated externally, it executes:
   `git pull --rebase --autostash origin session/{session_id}`
   and pushes again.

---

## 7. External Workspace Modifications & Auto-Pull Mechanics

Seamus treats external Git operations on session branches as intentional and authoritative (e.g., an administrator inspecting Gitea, fixing a file, or pushing a new skill):

- **Auto-Pull Contract (`sync_session_workspace`)**:
  - Before checking out a session workspace, and **immediately prior to every inference turn loop** in `SessionAgentRunner._run_loop()`, Seamus executes:
    `git pull --rebase --autostash origin session/{session_id}`
- This guarantees that any changes pushed directly to Gitea immediately reflect in the local backend workspace and in the agent's live `/workspace` mount before the next tool runs.

---

## 8. Thread Acceptance & Gitea Sync PR Lifecycle

Work in a session progresses in bounded units called **Threads**. Seamus enforces a strict single-open-thread invariant (`INV-005`): users cannot manually spawn arbitrary threads. Instead, advancement occurs via **Thread Acceptance**.

```
[Session Created]
       |
       v
Opens Gitea "Sync PR" (session/{id} --> main)
       |
       v
[Agent executes turn(s) in Thread 1] (Changes visible in UI "Changes" diff tab)
       |
       v
[User clicks "Accept" (Checkmark icon)]
       |
       +--> 1. Close Thread 1 (is_open = False), commit config
       +--> 2. Approve Sync PR in Gitea
       +--> 3. Perform data-scoped merge into main:
       |        * git checkout main && git pull origin main
       |        * git merge --no-commit --no-ff origin/session/{id}
       |        * git reset/checkout/clean agent/ artifacts/ notes/ back to HEAD
       |        * git add -A data/
       |        * git commit -m "sync: session/{name} (data/ deliverables)"
       |        * git push origin main
       |        * Mark Gitea PR "manually-merged" (merge_commit_id=<sha>)
       +--> 4. Create Thread 2 on session/{id}
       +--> 5. Open new Gitea Sync PR (session/{id} --> main)
```

### Why Data-Scoped Merge Matters:
A naive branch merge would copy `agent/state/` (checkpoints, event logs) and session `agent/config/` into `main`, which would corrupt base agent settings and cause merge conflicts across parallel sessions. The data-scoped merge guarantees that **`main` remains clean, containing strictly project deliverables**.

---

## 9. Session Branching-Out & Lineage Provenance

Users can fork a conversation from any completed assistant turn ($S_1 \to S_2$):

1. **Exact Turn Slicing**:
   - Thread events are sliced up to the selected assistant message turn (`RUN_FINISHED`).
   - S2 initializes cleanly in `AWAITING_USER` state.
2. **Git Commit Discovery (`find_commit_for_event`)**:
   - The workspace manager uses Git's pickaxe search (`git log -S{message_or_event_id} -n 1 --format=%H`) on the parent session's branch to discover the exact commit SHA where that turn landed.
3. **Workspace Fork**:
   - S2 clones or checks out a new branch `session/{new_session_id}` starting from that exact commit SHA:
     `git checkout -b session/{new_session_id} <branch_commit_sha>`
   - This ensures `/workspace` (`data/`) precisely matches the repository state at that historical moment.
4. **State Duplication**:
   - `GitCheckpointSaver.copy_thread()` duplicates checkpoints, writes, and state blobs into the new thread ID up to that turn.
5. **Fresh Sync PR**:
   - Opens a new Sync PR in Gitea from `session/{new_session_id}` targeting `main`.
6. **Provenance Tracking**:
   - $S_2$ records `SessionBranchProvenance` (`parent_session_id`, `parent_message_id`, `branched_at`). The UI displays an inline provenance banner with a one-click link back to $S_1$. $S_1$ is never modified.

---

## 10. Store Hydration & Disaster Recovery Lifecycle

Seamus is completely stateless outside Gitea and local workspace clones. On server restart:

1. `HarnessStore.hydrate_from_gitea()` queries Gitea's REST API for all repositories named `agent-{agent_id}`.
2. Reconstructs `Agent` entities from `main` branch `agent/config/config.json`.
3. Inspects all branches starting with `session/`.
4. Hydrates each `Session` and its `Thread`s from `agent/config/config.json` on that branch.
5. Hydrates the full event trajectory from `agent/state/threads/{thread_id}/events.json`.
6. Checks out working copies under `SEAMUS_WORKSPACE_DIR`.
7. Zero external database dependencies are required to restore full conversational history and code states.

---

## 11. Skill Discovery Hierarchy & In-Sandbox Mounts

Skills extend agent capabilities via Anthropic-compatible tool definitions. Multiple skill layers coexist and are resolved with strict precedence:

```
HIGHEST PRIORITY:
  1. /skills/bundled          (Platform-provided immutable skills, e.g. artifacts, A2UI)
  2. /workspace/skills        (Explicit session workspace overrides)
  3. /workspace/.skills       (Session background/default skills)
  4. (Future) Project mounts  (/projects/<name>/skills and .skills)
  5. system[0]                (Highest priority system directory, /skills/system/0)
  6. system[1] ...            (/skills/system/1)
  7. system[last]             (Lowest priority fallback)
LOWEST PRIORITY
```

To support DeepAgents' "last one wins" collision resolution, `SeamusOpenSandboxBackend.get_skill_sources()` passes these directories to the agent in **reverse priority order** so that `/workspace` and bundled platform skills always override system defaults.

---

## 12. The External Multi-Repo Context & Technical Constraints

The following background details and known technical constraints are essential for understanding how user-provided external repositories intersect with this architecture:

### A. Current Assumptions in the Core Codebase:
1. **Single Git Working Copy per Session**:
   - `GitWorkspaceManager` currently assumes each session corresponds to one Git root directory (`session_dir`), containing `data/`, `agent/config/`, `agent/state/`, and `artifacts/`.
   - `GitCheckpointSaver` invokes `commit_checkpoint_changes()` which executes Git commands (`git status`, `git add`, `git commit`, `git push`) exclusively against that single `session_dir`.
2. **Delivery Scope Boundary**:
   - Currently, all deliverables are assumed to live in `session_dir/data/` (mounted at `/workspace`).
   - The Changes tab diff viewer, the Sync PR, and the thread acceptance merge logic (`merge_sync_pr`) are strictly hardcoded to inspect and stage `data/`.
3. **Session Branching Relies on Commit Pickaxe**:
   - Slicing and forking a session from a past assistant message uses `git log -S{event_id}` against the single agent repository to locate the branch-off commit SHA.
4. **Volume Mount Declarations**:
   - `SeamusOpenSandboxBackend._ensure_sandbox()` builds volume mounts using either Docker named volume subpaths (`pvc=PVC(claimName="seamus-workspaces", subPath=...)`) or host paths (`host=Host(path=...)`).

### B. Pertinent Entries in Project Documentation:
- **`knowledge/backlog.md` Line 61 (`Mounting Custom User-Provided Git Repositories`)**:
  - Documents that external repositories were deliberately postponed while internal layout and verification mechanics matured.
- **`knowledge/backlog.md` Line 99 (`Session Branching Interaction with Session-Local Non-Blocking Artifacts and Multi-Repo Git Mounts`)**:
  - Highlights the known architectural question: when multiple external repositories are mounted into the sandbox, how do session branching, thread checkpoints, and multi-repo commit states remain synchronized across branches and phases without desynchronization or broken history lineage?
- **`INV-017` & `INV-018`**:
  - Strictly mandate that agent state and operational files are versioned atomically and that the sandbox boundary is never violated.

---

### Summary Checklist for External Multi-Repo Discussions

When discussing how to mount custom user-provided repositories into this system, the discussion will typically need to address:
- **Mount Topology**: Where external repositories appear inside the sandbox container (e.g. `/workspace`, `/projects/<name>`, or multiple working directories) and how Docker volume/bind mounts are provisioned.
- **Commit Orchestration Order**: How commits are coordinated between external repositories and the primary agent repository (e.g. committing changes in external working trees first, capturing those commit SHAs, and recording them into `agent/state/` of the first-class agent repository).
- **Branching & Rollback Alignment**: How session branching (`branch_session`) and rollbacks check out corresponding historical commit SHAs across both the agent state repository and the mounted external repositories.
- **Sync PR & Acceptance Semantics**: Whether external repositories use their own remotes/branches/PRs versus the internal Gitea Sync PR mechanism, and what "Accept Thread" means when external codebases are modified.