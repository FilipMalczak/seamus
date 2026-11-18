# 0069. Agent and Session Archival, Hard Deletion, and Soft-Delete Governance

Date: 2026-11-18

## Status

Accepted

## Context

Prior to this decision, Seamus supported creating, updating, and executing agents, sessions, and threads, but provided no mechanism to remove or archive them. As a consequence:
1. Inactive or test agents and sessions cluttered the UI navigation tree indefinitely.
2. Under [0002-harness-server-mvp.md](./0002-harness-server-mvp.md) and [INV-007](../knowledge/invariants.md#inv-007-no-resource-deletion-invariant), the API surface prohibited HTTP `DELETE` operations across all endpoints to enforce non-destructive persistence safety.
3. The organizational hierarchy introduced in [0068-organization-and-session-gitea-layers.md](./0068-organization-and-session-gitea-layers.md) paved the way for soft deletion (ignoring prefixed organizations such as `archived-agent-...`), but lacked formal archiving and deletion workflows.

## Decision

We establish first-class **Archive** and **Hard Delete** lifecycles for agents and sessions, backed by native Gitea operations:

1. **Session Archival**:
   - Marking a session as archived invokes Gitea's repository settings API (`PATCH /api/v1/repos/{agent_org}/{repo}` with `{"archived": true}`) on the session state repository (`session-{session_id}`) and on each external mount fork in the agent organization (`project-{project_name}-{url_hash}-{session_hash}`).
   - Archiving is potentially reversible: before archiving, Seamus guarantees that any dirty workspace state is checkpointed and committed to Git (`commit_checkpoint_changes`, `snapshot_session_repositories`).
   - Once persisted, the local workspace clone (`<workspace_root>/<agent_id>/<session_id>`) is safely removed from disk.
   - The session is evicted from active in-memory store state.

2. **Session Hard Deletion**:
   - Permanently deletes all external mount forks (`project-*-{session_hash}`) and the session state repository (`session-{session_id}`) via `DELETE /api/v1/repos/{agent_org}/{repo}` in Gitea.
   - Purges the local workspace clone from disk.
   - Evicts the session from active in-memory store state.

3. **Agent Archival**:
   - Renames the agent's dedicated Gitea organization from `agent-{agent_id.hex}` to `archived-agent-{agent_id.hex}` via `POST /api/v1/orgs/{org}/rename`. All repositories within the organization remain intact.
   - Purges local agent workspace directories from disk.
   - Evicts the agent from active in-memory store state.

4. **Agent Hard Deletion**:
   - Gitea strictly forbids deleting an organization while repositories still exist within it. Therefore, agent hard deletion first enumerates and permanently deletes every repository in `agent-{agent_id.hex}` (`agent`, all `session-*`, and all `project-*` forks), followed by deleting the organization itself via `DELETE /api/v1/orgs/{org}`.
   - Purges local agent directories from disk.
   - Evicts the agent from active in-memory store state.

5. **Gitea State Hydration & Filtering**:
   - `HarnessStore.hydrate_from_gitea()` enforces strict pattern validation on organization names (`agent-<uuid>`), ignoring all prefixed organizations (`archived-agent-...`) and administrative orgs (`mirrors`).
   - During session discovery within an agent organization, repositories with `archived: true` are ignored.

6. **System Settings Toggle (`enable_delete`)**:
   - A boolean setting `enable_delete` is added to `SystemSettings` (persisted in `seamus/system/settings.json`, default `false`).
   - When `false`, hard delete icons are hidden in the navigation tree, permitting only archiving.
   - When `true`, both archive and hard delete icons are visible.

7. **Confirmation and Running Execution Guard**:
   - In the UI navigation tree, archive and delete actions require user confirmation.
   - If a target session is actively executing (not awaiting user), confirmation explicitly warns that the active execution will be terminated before proceeding.

8. **Revision of Invariant INV-007**:
   - Invariant [INV-007](../knowledge/invariants.md#inv-007-no-resource-deletion-invariant) is scoped: HTTP `DELETE` operations are restricted strictly to Agent (`/api/v-alpha/agent/{agent_identifier}`) and Session (`/api/v-alpha/agent/{agent_identifier}/session/{session_identifier}`) lifecycle management. All other resources (threads, messages, checkpoints, artifacts, steerable queues) continue to prohibit `DELETE`.

## Consequences

- Inactive, completed, or failed sessions and agents can be cleanly hidden from active UI views without destroying underlying Git history (via Archive) or permanently removed (via Delete).
- Gitea remains the golden source of truth for both active and archived entities.
- Accidental permanent data loss is mitigated by the default `enable_delete: false` setting and required confirmation dialogues.

