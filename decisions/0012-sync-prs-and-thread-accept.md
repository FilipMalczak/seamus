# 0012. Gitea Sync PRs and Thread Acceptance Lifecycle

Date: 2026-10-31
Status: Accepted

## Context

In Seamus, an agent's persistent workspace and state are tracked in Gitea on dedicated session branches (`session/{session_id}`). Prior to this decision:
- Users could explicitly and manually create new threads at any time via a "+" button next to the session in the sidebar or via the "New Thread" button in the chat area top bar.
- Changes committed on session branches (agent outputs in `data/`, state events, and checkpoints) were not automatically propagated or merged into the default branch (`main`).
- There was no structured gate or lifecycle mechanism for accepting an agent's work in a thread before advancing to the next thread.

## Decision

1. **Removal of Explicit Manual Thread Creation**:
   - Removed manual thread creation controls from the UI sidebar session node.
   - Sessions are created with an initial open thread automatically.
   - Subsequent threads in a session are created exclusively through the thread acceptance lifecycle.

2. **Top Bar "Accept" Action**:
   - Replaced the "New Thread" button at the top bar with an "Accept" action button displaying only a tick icon (`Check`), styled in an inviting emerald/green visual treatment without a text label.
   - The button is active only when the current thread is open and the agent is idle (`AWAITING_USER`).
   - When clicked, it initiates atomic acceptance of the thread's work and transitions the session to a fresh open thread.

3. **Gitea Sync PR Lifecycle**:
   - **Session Initialization**: When a session workspace is created, a "Sync PR" is automatically opened in Gitea from `session/{session_id}` targeting `main`.
   - **Thread Acceptance**: When the user accepts:
     1. The current thread is closed (`is_open = False`), and session config is committed to the session branch.
     2. The active Sync PR for the session is approved (if permissions allow) and merged into `main` using standard merge commit (`Do: "merge"`, retaining the branch).
     3. A new thread is created on the session (`session.create_thread()`).
     4. Session config is committed, and a new Sync PR from `session/{session_id}` to `main` is opened.
     5. The new thread is returned and auto-selected in the UI.

4. **Deferred Action**:
   - Merge rules on Sync PRs (branch protection rules, required review policies, and CI status checks) are deferred and tracked in `knowledge/backlog.md`.

## Consequences

- Direct manual thread spawning is replaced with an intentional acceptance lifecycle that syncs verified agent output back into the repository's base branch.
- Base branch `main` reflects accepted increments from completed threads across sessions.
- In-flight work remains isolated on `session/{session_id}` until explicitly accepted by the user.

## Cross-References

- [0008-git-persistence.md](./0008-git-persistence.md)
- [../knowledge/requirements.md](../knowledge/requirements.md)
- [../knowledge/invariants.md](../knowledge/invariants.md)
- [../knowledge/backlog.md](../knowledge/backlog.md)

