# 0067. Resilient Stale Git Lock Recovery and Workspace Concurrency Serialization

Date: 2026-11-18

## Status

Accepted

## Context

When the host machine, container, or harness backend process abruptly terminates (kill, power loss, OOM, SIGKILL), any in-flight Git command operating in an agent, session, system, or external repository working tree leaves behind advisory lock files (such as `.git/index.lock`, `.git/HEAD.lock`, `.git/refs/**/*.lock`, or `.git/shallow.lock`).

Git creates lock files using `open(path, O_CREAT | O_EXCL)` to enforce mutual exclusion during index and ref mutations. By design, Git never automatically deletes existing lock files after an abnormal process death (`fatal: Unable to create '.../.git/index.lock': File exists. Another git process seems to be running...`).

Upon harness restart, opening an affected session triggers `SessionAgentRunner` initialization, which calls `create_session_workspace()` -> `commit_session_config()`. Running `git add -A agent/config/` fails with exit code 128, raising `GitWorkspaceError`. Because `GitWorkspaceError` is a `RuntimeError`, the SSE stream endpoint (`GET /api/v-alpha/agent/{agent}/session/{session}/stream`) caught it and converted it into an HTTP `400 Bad Request`, permanently bricking the session until manual filesystem deletion. Furthermore, concurrent backend threads executing Git commands in the same repository lacked thread serialization.

## Decision

1. **Stale Lock Recovery & Management (`src/seamus/persistence/git_lock.py`)**:
   - Introduce `clean_stale_locks(repo_dir: Path, force: bool = False, max_age_seconds: float = 0.0) -> list[Path]` to recursively scan `.git/` (and `.seamus_indexes/`) for all `*.lock` files.
   - Introduce `is_git_process_running_in_repo(repo_dir: Path) -> bool` which inspects Linux `/proc` to verify whether an active `git` process is executing with its working directory inside `repo_dir`.
   - If no active `git` process is detected (or `force=True`), unlink all matching `.lock` files and log warnings.
   - Introduce `sweep_workspace_stale_locks(root_dir: Path) -> int` to sweep all `.git` directories across the workspace tree on startup.
   - Introduce `get_repo_lock(repo_dir: Path) -> threading.RLock` to serialize concurrent Git operations on the same repository within the backend process.

2. **Self-Healing `_run_git` with Retries**:
   - In both `GitWorkspaceManager._run_git` (`src/seamus/persistence/workspace.py`) and `ExternalRepositoryManager._run_git` (`src/seamus/persistence/external_repo.py`), wrap execution in `get_repo_lock(cwd)`.
   - On `CalledProcessError` (or `returncode == 128` when `check=False`) matching lock collisions (`Unable to create '...lock': File exists` or `Another git process seems to be running`), extract referenced lock paths, purge stale locks, log a recovery warning, and retry the command up to 2 times.

3. **Startup & Lifecycle Proactive Cleaning**:
   - In `create_app()` (`src/seamus/server/app.py`), `GitWorkspaceManager.__init__`, and `ExternalRepositoryManager.__init__`, execute `sweep_workspace_stale_locks()` to purge crash debris across all existing workspaces at backend startup before requests or runners begin.
   - In `create_session_workspace()`, `sync_session_workspace()`, `commit_session_config()`, `commit_checkpoint_changes()`, `provision_session_working_copy()`, and `checkpoint_working_copy()`, proactively clean stale locks before performing workspace mutations.

## Consequences

- Abrupt host or container terminations no longer brick existing sessions. On restart, stale locks are automatically swept at startup and self-healed on demand during Git operations.
- Concurrent requests touching the same repository serialize safely across Python threads via re-entrant repository mutexes.
- No manual intervention is needed to revive sessions affected by previous host crashes.

