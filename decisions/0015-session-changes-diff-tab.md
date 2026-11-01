# 0015. Session Changes Tab, Diff Viewer, and Thread Acceptance Relocation

Date: 2026-11-01
Status: Accepted

## Context

In Decision [0012](./0012-sync-prs-and-thread-accept.md), Seamus introduced the thread acceptance lifecycle and automated Gitea Sync PRs:
- Every active session workspace maintains an open Sync PR from `session/{session_id}` into `main`.
- An "Accept" action button was placed in the Chat Area top header to close the active thread, merge the Sync PR into `main`, and spawn a fresh thread with a renewed Sync PR.

While functional, having the "Accept" action in the conversation header lacked transparency: users could not review the cumulative codebase and state modifications contained in the Sync PR before deciding whether to accept and merge.

## Decision

1. **Relocation of Thread Acceptance Action**:
   - Removed the "Accept" tick button from the top right of the Chat Area header (`ChatArea.tsx`).
   - Placed the "Accept" button prominently within the header of a dedicated **Changes** view.
   - Kept the acceptance prerequisites: active only when the current thread is open and the agent is idle (`AWAITING_USER`).

2. **Dedicated "Changes" Tab in Right Main Panel**:
   - Added a "Changes" tab to the main panel tab navigation bar, placed immediately after the "Inspector" tab (`Chat` | `Inspector` | `Changes`).
   - Accessible whenever an agent and session are selected.

3. **Sync PR Diff Retrieval API**:
   - Added `get_pull_request_diff` to `GiteaClient` (`src/seamus/persistence/client.py`) to fetch raw unified diffs from Gitea (`GET /api/v1/repos/{owner}/{repo}/pulls/{index}.diff`).
   - Added `get_sync_pr_diff` to `WorkspaceManager` (`src/seamus/persistence/workspace.py`) to query the active Sync PR and retrieve its diff.
   - Exposed endpoint `GET /api/v-alpha/agent/{agent_id}/session/{session_id}/diff` (`src/seamus/server/routes/sessions.py`) returning `SessionDiffResponse` with `pr_number`, `pr_url`, and the unified `diff`.

4. **Diff Rendering via `@pierre/diffs`, File Tree Navigation, and Collapsible Cards**:
   - Integrated `@pierre/diffs` into the frontend to render the unified patch with full syntax highlighting.
   - Filtered out internal runtime persistence blobs (`agent/state/**`) from the API diff payload to ensure responsive rendering.
   - Added a collapsible file navigation sidebar supporting both hierarchical directory Tree view and flat List view, with status badges (`[A]`, `[M]`, `[D]`, `[R]`), diff stats, and click-to-scroll navigation.
   - Implemented per-file collapsible diff cards with header status badges, path copying, line change counts, and global Expand/Collapse All controls.
   - Provided unified/split layout toggle and external link to the active Gitea PR when available.
   - Provided a manual refresh control to reload changes on demand.

## Consequences

- Users have complete visibility into code and state modifications staged in the Sync PR before committing to merge into `main`.
- The Chat header is decluttered, focusing solely on conversation and execution status.
- The thread acceptance lifecycle remains atomic and safe, now paired directly with visual diff verification.

## Cross-References

- [0012-sync-prs-and-thread-accept.md](./0012-sync-prs-and-thread-accept.md)
- [0011-agent-inspector.md](./0011-agent-inspector.md)
- [../knowledge/requirements.md](../knowledge/requirements.md)
- [../knowledge/invariants.md](../knowledge/invariants.md)
- [../knowledge/architecture.md](../knowledge/architecture.md)

