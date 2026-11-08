# 0042: Mount External Git Repositories into Agent Sandboxes

## Status

Accepted

## Context

Previously, Seamus agents could only operate inside their dedicated agent repository (`agent-{agent_id}`), mounted into the OpenSandbox container at `/workspace`. To have agents work on existing software repositories or multi-repo projects, users had to copy files manually into `/workspace` or treat external projects as part of the agent's internal operational state.

To support real-world development workflows, Seamus needs to mount an arbitrary number of external Git repositories into an agent's sandbox environment under `/projects/` while preserving the following architectural requirements:
- The agent repository (`agent-{agent_id}`) remains the authoritative persistence layer for session state, checkpoints, config, and conversation turns.
- External repositories must retain fully functional Git capabilities (`git status`, `git diff`, `git add`, `git commit`, `git branch`, etc.) inside the sandbox.
- Seamus automated filesystem checkpointing must snapshot mounted repositories into durable Gitea storage without polluting or advancing the semantic Git history of the project, and without modifying the agent's staged index (`.git/index`) or working tree.
- Git credentials must use OpenBao symbolic secret references (`${secret(...)}`) and never be exposed inside the sandbox or persisted in `.git/config`.
- Historical state reconstruction across session branching and crash recovery must restore exact semantic `HEAD`, ordinary staged index, and working-tree contents.

## Decision

We implement external Git repository mounting and persistence across the configuration model, OpenBao vault integration, persistence layer, OpenSandbox backend, session runner, and Web UI:

1. **Configuration & Inheritance (`ExternalRepositoryConfig`)**:
   - `AgentConfig`, `SessionConfig`, and `ConfigTemplate` accept a `repositories: list[ExternalRepositoryConfig]` field.
   - Each entry defines:
     - `id: str`: Unique session attachment identifier (`uuid4().hex`).
     - `url: str`: Remote Git repository URL (HTTPS or SSH format).
     - `branch: str`: Configured upstream branch to check out (defaults to `main`).
     - `credentials_ref: str | None`: Optional OpenBao symbolic secret reference (`${secret(path=...)}`).
   - Secret references are validated against user-configuration constraints (`allow_version=False`) and resolved strictly in-memory on the host by `ExternalRepositoryManager`. Cleartext credentials are never written to disk, committed to Git, or exposed inside container environment variables.

2. **Deterministic Mount Path Resolution (`/projects/{mount_name}`)**:
   - Repositories are mounted into OpenSandbox at `/projects/{mount_name}`. The existing `/workspace` mapping remains unchanged.
   - Mount names are derived deterministically from the final path component of the repository URL (stripping `.git` and trailing slashes, converted to alphanumeric + hyphens/underscores).
   - If multiple repositories produce the same base name, numeric suffixes (`_0`, `_1`, `_2`, ...) are appended to **all** colliding entries. Unique names receive no suffix.
   - Host storage path: `<workspace_root>/{agent_id}/{session_id}/projects/{mount_name}`.

3. **Gitea Internal Repository Topology (`project-{project_id}`)**:
   - Each unique upstream repository has a deterministic internal identity:
     `project_id = sha256(canonical_url)[:12]`.
   - On the self-hosted Gitea instance, an internal mirror repository `project-{project_id}` is provisioned and mirrored from the upstream remote using resolved credentials.
   - Each session clones from `project-{project_id}` and checks out the configured branch (`repo_config.branch`, e.g. `master` or `main`), tracking `origin/{repo_config.branch}` so the agent observes the true upstream branch name inside the sandbox.

4. **Dual-Index Snapshot Architecture**:
   - Inside `/projects/{mount_name}`, the agent interacts directly with `.git/index` and the working tree.
   - During Seamus checkpointing (`GitCheckpointSaver._checkpoint_external_repositories`), Seamus persists intermediate filesystem state without touching the agent's index or `HEAD`:
     1. Captures the agent's staged index as an immutable tree: `git write-tree` against `.git/index` $\to$ `staged_tree`.
     2. Uses an external alternate Git index file located outside the sandbox mount (`.seamus_indexes/{attachment_id}.idx`) via `GIT_INDEX_FILE`.
     3. Initializes the alternate index from current `HEAD`: `git read-tree HEAD`.
     4. Stages working-tree modifications into the alternate index: `git add -A -- .` (respecting `.gitignore`).
     5. Writes the working-tree snapshot tree: `git write-tree` $\to$ `snapshot_tree`.
     6. Creates an independent checkpoint commit: `git commit-tree snapshot_tree -p prev_cp_sha` $\to$ `checkpoint_sha`.
     7. Pushes the checkpoint commit and tree to Gitea under dedicated refs:
        `refs/seamus/sessions/{session_id}/attachments/{attachment_id}/checkpoints/{checkpoint_id}`,
        `refs/seamus/snapshots/{session_id}/{attachment_id}`, and visible branch
        `refs/heads/seamus/checkpoints/{session_id}/{mount_name}` (so checkpoints are directly browseable and inspectable in the Gitea UI).
     8. Pushes semantic commits created by the agent to `refs/heads/seamus/semantic/{session_id}/{mount_name}` in Gitea so semantic work is never lost.
   - Project checkpoint commits have independent ancestry and never fast-forward or modify the agent's semantic Git branch.

5. **Multi-Repository Checkpoint Ordering & Agent Manifest**:
   - Invariant: All external project snapshots must be committed and pushed to Gitea **before** the agent repository checkpoint is committed.
   - `MountedRepositoryCheckpointRecord` records for each mounted repo:
     - `attachment_id`, `project_id`, `mount_name`, `url`, `branch`
     - `semantic_head` and `semantic_branch`
     - `staged_tree` (agent's staged state)
     - `snapshot_tree` (agent's uncommitted working tree)
     - `checkpoint_sha` (durable checkpoint commit in Gitea)
     - `gitea_repo_name` and `gitea_repo_url` (explicitly mapping internal Gitea repositories to external projects)
   - These records are written to `agent/state/external_checkpoints.json` and committed directly to the agent repository's session branch, guaranteeing atomic provenance.

6. **Historical State Reconstruction & Session Branching**:
   - When branching a session (`branch_session`) or recovering from a crash, the target agent commit contains `external_checkpoints.json`.
   - `ExternalRepositoryManager.restore_working_copy_checkpoint` reconstructs the exact historical working copy:
     1. Checks out `record.semantic_head` on `record.semantic_branch`.
     2. Extracts `record.snapshot_tree` files onto the working tree via `git archive | tar -x` without modifying the Git index.
     3. Restores the agent-facing staged index via `git read-tree {record.staged_tree}` against `.git/index`.
   - The reconstructed working copy has the exact same `git status`, staged changes, unstaged changes, and untracked files as when the checkpoint was created.

7. **Ephemeral Working-Tree Semantics Across Unmount/Remount**:
   - If a repository is unmounted from a session (removed from configuration) and later remounted, uncommitted working-tree modifications are discarded.
   - The remounted working copy starts clean from the project's configured branch (`repo_config.branch`, e.g. `master` or `main`).

8. **Skill Discovery Integration (INV-035)**:
   - Skills located inside mounted projects (`/projects/{name}/skills` and `/projects/{name}/.skills`) are automatically discovered and loaded into the agent's operating environment.
   - Precedence order:
     `bundled` (`/skills/bundled`) > `session workspace` (`/workspace/skills`) > `session workspace background` (`/workspace/.skills`) > `project` (`/projects/{name}/skills`) > `project background` (`/projects/{name}/.skills`) > `system` (`/skills/system/{idx}`).

9. **Web UI Support**:
   - The Agent Configuration Modal (`ConfigModal.tsx`) includes a "Mounted Git Repositories (/projects/)" section with dynamic add/remove, URL, branch, and OpenBao credentials secret reference inputs.
   - The Session Inspector (`InspectorModal.tsx`) displays mounted repository status, canonical project IDs, active semantic commits, and checkpoint snapshot references.

10. **Developer Sandbox Environment (`seamus-sandbox:latest`)**:
    - OpenSandbox containers execute using a first-party Ubuntu 24.04 image (`opensandbox/Dockerfile.sandbox`) with pre-installed `python3`, `git`, `ca-certificates`, `curl`, `less`, and `procps`.
    - `python3` ensures DeepAgents filesystem tools (`ls`, `read_file`, `write_file`, `edit_file`) function without silent failures, while `git` enables standard Git operations within `/projects/{mount_name}`.
    - An automated build via the `sandbox-image` service in `docker-compose.yml` ensures the image is tagged on the host Docker daemon prior to backend initialization.

## Consequences

- Agents can now develop, test, and commit code directly on external Git repositories while running inside isolated OpenSandbox containers.
- Agent Git operations inside `/projects/` remain completely standard (`git status` and `git diff` accurately reflect the agent's work).
- Checkpoint persistence is non-intrusive, crash-resilient, and fully auditable in Gitea.
- Credentials remain secure in OpenBao with zero container exposure.

