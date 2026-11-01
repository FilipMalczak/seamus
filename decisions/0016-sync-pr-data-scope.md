# 0016. Restrict Sync PRs and Thread Acceptance Merges to data/ Deliverables

Date: 2026-11-01
Status: Accepted

## Context

In Seamus, agent workspace deliverables, configuration, and internal runtime state are version-controlled in Gitea across dedicated session branches (`session/{session_id}`). In Decisions [0012](./0012-sync-prs-and-thread-accept.md) and [0015](./0015-session-changes-diff-tab.md), Seamus established automated Sync PRs from `session/{session_id}` into `main`, paired with the Changes diff viewer and the thread acceptance lifecycle.

However, merging the Sync PR previously merged the entire session branch tree into `main`. This polluted the base repository branch (`main`) with:
1. `agent/config/config.json`: session-level entity metadata and thread lists overwrote the base agent configuration.
2. `agent/state/threads/{thread_id}/`: internal LangGraph checkpoints, AG-UI event logs, and message traces accumulated on `main`.
3. Multi-session merge conflicts: subsequent sessions attempting thread acceptance encountered merge conflicts on session configuration and internal state files.

The base branch (`main`) is intended to represent clean, merged project deliverables without session-specific runtime checkpoints, event histories, or session configuration blobs.

## Decision

1. **Reviewable Diff Filtering (`filter_sync_pr_diff`)**:
   - Refined `filter_sync_pr_diff` in `src/seamus/persistence/workspace.py` so that unified diff chunks returned to the UI (`GET /api/v-alpha/agent/{agent}/session/{session}/diff`) and the Changes viewer are strictly scoped to files modifying `data/` (`a/data/` or `b/data/`).
   - Diff chunks touching `agent/config/**`, `agent/state/**`, or any other harness-internal directories are discarded from the reviewable payload.

2. **Gitea Repository Merge Policy & Manual Merge API**:
   - Configured `GiteaClient` (`src/seamus/persistence/client.py`) to ensure repositories created or verified in Gitea enable `allow_manual_merge=True` and `autodetect_manual_merge=True`.
   - Extended `GiteaClient.merge_pull_request` to support `do="manually-merged"` and `merge_commit_id=<sha>`.

3. **Data-Scoped Merge Execution (`GitWorkspaceManager.merge_sync_pr`)**:
   - Replaced naive server-side branch merging with an isolated 2-parent merge operation on the agent working copy (`agent_dir` on `main`):
     1. Sync `main` with `origin/main` and fetch `origin/session/{session.id}`.
     2. Execute `git merge --no-commit --no-ff origin/session/{session.id}`.
     3. Restore and isolate harness-internal directories to match `HEAD` on `main`: unstage, checkout, and clean `agent/` (`reset HEAD -- agent`, `checkout HEAD -- agent`, `clean -fd agent`).
     4. Stage strictly `data/` deliverables (`add -A data/`).
     5. Commit the merge commit with standard prefix: `sync: session/{session_identifier} (data/ deliverables)`.
     6. Push the merge commit to `origin main`.
     7. Notify Gitea to record the Sync PR as merged using `do="manually-merged"` with `merge_commit_id=<sha>`.

4. **Multi-Session Independence**:
   - Because `agent/` on `main` is preserved and never modified during thread acceptance merges, multiple sessions for the same agent can merge sequentially or concurrently without experiencing merge conflicts on internal configuration or state files.

## Consequences

- The base branch (`main`) remains clean, recording only accepted agent project deliverables in `data/`.
- `main`'s agent configuration and clean state structure are never overwritten by individual session entities.
- The Changes viewer in the UI accurately mirrors the exact deliverables staged for merge into `main`.
- Multi-session concurrent workflows can be accepted without merge conflicts.

## Cross-References

- [0008-git-persistence.md](./0008-git-persistence.md)
- [0012-sync-prs-and-thread-accept.md](./0012-sync-prs-and-thread-accept.md)
- [0015-session-changes-diff-tab.md](./0015-session-changes-diff-tab.md)
- [../knowledge/requirements.md](../knowledge/requirements.md)
- [../knowledge/invariants.md](../knowledge/invariants.md)
- [../knowledge/architecture.md](../knowledge/architecture.md)
- [../knowledge/abstractions.md](../knowledge/abstractions.md)
- [../knowledge/backlog.md](../knowledge/backlog.md)

