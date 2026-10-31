# 0008. Gitea-Backed Git Persistence, Isolated Workspace Filesystem, and Session Config Editing

Date: 2026-10-31
Status: Accepted

## Context

Seamus agents require durable, version-controlled persistence. Unlike harnesses that mount host directories directly into agent-accessible space, Seamus enforces that agent data must be Git-tracked and isolated. Prior to this decision, agent sessions operated with ephemeral in-memory state (`MemorySaver`), without Git tracking of agent files or restart persistence, and without in-browser UI support for per-session configuration editing.

## Decision

1. **Gitea Service with PostgreSQL Backing (`docker-compose.yml`)**:
   - Spin up companion **Gitea** service (`gitea/gitea:latest`) on port `3001` (internal `3000`), selected for its permissive MIT license over Forgejo's copyleft GPLv3 license.
   - Back Gitea with a dedicated **PostgreSQL** service (`postgres:16-alpine`) and persistent volume `postgres-data`.
   - The Seamus backend itself does not require direct SQL or ORM dependencies; Gitea uses PostgreSQL as its backing layer, while Seamus treats Gitea's Git repositories and REST API as the golden source of truth for agents, sessions, and workspaces.
   - Maintain the Gitea Web UI accessible on `http://localhost:3001` with automated user initialization (`seamus`) and auto-install configuration.

2. **Repository & Branch Layout**:
   - Each Agent is mapped to a dedicated public Git repository (`private=False`) named `agent-{agent_id}` owned by the `seamus` service user, browsable without authentication.
   - **Repository Structure**:
     ```text
     <repo> (agent-{agent_id})
     ├── agent/
     │   ├── config/
     │   │   └── config.json          # Agent metadata, entity attributes, and AgentConfig
     │   └── state/
     │       └── threads/
     │           └── {thread_id}/
     │               ├── events.json       # Ordered AG-UI event stream (messages, thoughts, tool calls)
     │               ├── checkpoints.json  # Serialized LangGraph checkpoints, writes, and blobs (HITL state)
     │               └── messages.json     # Human-readable conversation messages
     └── data/                        # Isolated working directory for agent tool file operations
     ```
   - **`main` branch**:
     - `agent/config/config.json`: JSON dump of the Agent entity, metadata, and base `AgentConfig`.
     - `agent/state/.gitkeep`: Base state directory placeholder.
     - `data/.gitkeep`: Base workspace placeholder.
   - **`session/{session_id}` branch**:
     - Branched from `main`.
     - `agent/config/config.json`: JSON dump of the Session entity, session-level `AgentConfig`, and thread metadata.
     - `agent/state/`: State directory holding events, checkpoints, and messages per thread.
     - `data/`: Working directory containing all agent-generated files.

3. **DeepAgent Filesystem Isolation Boundary (`seamus.harness.runner`)**:
   - Local clones/working trees are managed under `SEAMUS_WORKSPACE_DIR` (`.seamus/workspaces/{agent_id}/{session_id}`).
   - DeepAgent's `FilesystemBackend` is instantiated with `root_dir = <session_dir>/data` and `virtual_mode = True`.
   - The agent has zero visibility or access to `agent/` or `.git/`, completely separating agent files from configuration and repository internals.
   - *Deferred Action*: This filesystem scoping is an intermediate mechanism to control agent exposure. Future iterations will cover exact filesystem exposure mechanisms and sandboxed shell execution boundaries.

4. **Automated Commit Delineation (`seamus.persistence`)**:
   - `GitCheckpointSaver` wraps LangGraph checkpointing (`put`, `aput`, `put_writes`, `aput_writes`). When a checkpoint is written, it serializes checkpoint state to `agent/state/threads/{thread_id}/checkpoints.json`, writes human-readable messages to `messages.json`, and commits modifications in `data/` and `agent/state/`:
     `checkpoint: [session=<session_id> thread=<thread_id> checkpoint=<checkpoint_id>]`
     and pushes immediately to the session branch.
   - Turn completion commits remaining AG-UI streaming events in `agent/state/`:
     `state: update thread events [session=<session_id> thread=<thread_id>]`
   - Config updates commit the entire `agent/config/**` directory (`git add -A agent/config/`) to Git:
     - `config: update agent config [agent=<agent_id>]` on `main`
     - `config: update session config [session=<session_id>]` on `session/{session_id}`
   - Default commit author: `Seamus Agent <agent@seamus.local>`.

5. **Store Hydration from Gitea (`seamus.harness.store`)**:
   - On server startup, `HarnessStore.hydrate_from_gitea()` discovers existing repositories owned by `seamus`.
   - Reconstructs `Agent` entities from `main` branch `agent/config/config.json` (with fallback to `config/config.json`).
   - Reconstructs `Session` entities and their `Thread`s from each `session/{session_id}` branch `agent/config/config.json`.
   - Reconstructs `thread.events` from `agent/state/threads/{thread_id}/events.json`.
   - Restores the entire hierarchy without external database dependencies.

6. **Web UI Session Configuration Editing & External Gitea Links (`ui`)**:
   - Add a `Settings` icon button to Session nodes in `Sidebar.tsx` opening `ConfigModal` to inspect and modify session-specific `AgentConfig`.
   - Wire up `updateSession` and `updateAgent` API persistence handlers on modal save.
   - Add an external system navigation link in the bottom-left sidebar linking to Gitea home (`http://localhost:3001`), exposed dynamically via `GET /api/v-alpha/system/info`.
   - Add two contextual branch navigation buttons to the bottom-left sidebar footer:
     1. **Agent Git Branch**: Direct link to `{gitea_url}/{owner}/agent-{agent_id}/src/branch/main` using a composite icon (base `Bot` icon in sky-400 badged with a mini `GitBranch` at bottom-right).
     2. **Session Git Branch**: Direct link to `{gitea_url}/{owner}/agent-{agent_id}/src/branch/session/{session_id}` using a composite icon (base `MessageSquare` icon in indigo-400 badged with a mini `GitBranch` at bottom-right).
     - Both buttons display in an inactive/disabled state with descriptive tooltips when no agent or session is selected, activating upon selection.
     - *Note*: Option B (Git base with entity badge) was evaluated and may be reconsidered in the future.

7. **Container Launch Script Refinement (`run.sh`)**:
   - Refined `--restart` (`-r`) to rebuild only the application containers we own (`backend`, `frontend`) and recreate them to apply code updates while preserving infrastructure containers (`postgres`, `gitea`) and all persistent volumes.
   - Added `--clean` (`-c`) to stop all containers, tear down persistent volumes (`postgres-data`, `gitea-data`, `backend-workspaces`), purge local `.seamus/workspaces`, and restart all services cleanly.

8. **Deferred Tasks**:
   - Sandboxed shell access and exact filesystem exposure mechanism.
   - Per-agent, per-session, and per-thread Gitea commit authors, organizations, and teams.
   - Mounting custom user-provided Git repositories.

## Consequences

- All agent operations and state are strictly versioned in Git with clear delineation between `config:`, `state:`, and `checkpoint:` commits.
- Agents are restricted to their `data/` workspace, unable to access or corrupt repository configuration, state, or Git metadata.
- Sessions and agents persist across container rebuilds, hydratable directly from Gitea repositories.
- Users can view and edit both agent and session configurations in the web interface and navigate to Gitea from the sidebar.

## Cross-References

- [0002-harness-server-mvp.md](./0002-harness-server-mvp.md)
- [0003-react-web-ui.md](./0003-react-web-ui.md)
- [0004-inline-tree-editing-session-status.md](./0004-inline-tree-editing-session-status.md)
- [0006-external-system-links.md](./0006-external-system-links.md)
- [../knowledge/requirements.md](../knowledge/requirements.md)
- [../knowledge/invariants.md](../knowledge/invariants.md)
- [../knowledge/architecture.md](../knowledge/architecture.md)
- [../knowledge/abstractions.md](../knowledge/abstractions.md)
- [../knowledge/conventions.md](../knowledge/conventions.md)
- [../knowledge/vocabulary.md](../knowledge/vocabulary.md)
