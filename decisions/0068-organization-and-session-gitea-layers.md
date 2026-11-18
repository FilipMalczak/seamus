# 0068. Gitea Organization Hierarchy, Dedicated Session Repositories, and Multi-Tier External Repositories

Date: 2026-11-18

## Status

Accepted

## Context

Prior to this decision, Seamus stored all Git persistence under the flat namespace of the single service user (`seamus`):
- Each agent was mapped to a single repository `agent-{agent_id}` owned by the service user ([0008-git-persistence.md](./0008-git-persistence.md)).
- Sessions within an agent shared this repository, existing only as Git branches (`session/{session_id}`).
- External repositories were mirrored directly into a single internal repository `project-{project_id}` under the service user ([0042-mount-external-git-repositories.md](./0042-mount-external-git-repositories.md)), and sessions cloned directly from that single mirror into their local `/projects/{mount_name}` workspaces.

This design had several limitations:
1. All sessions of an agent operated against branches of a single shared repository, entangling session state, branch protection, and lifecycle governance.
2. External repository mirrors mixed read-only downstream upstream tracking with agent checkpoint branches and semantic working commits, rather than separating read-only upstream tracking from writable agent workspaces.
3. Multiple sessions concurrently working on the same external repository pushed checkpoints and semantic commits to the same backing repository.

## Decision

We establish an organization-based, multi-tiered hierarchy in Gitea across agent lifecycle and external repository mounting:

1. **Agent Organizations (`agent-<agent_uuid>`)**:
   - Every agent is provisioned with a dedicated Gitea organization named `agent-<agent_uuid>`.
   - Baseline agent configuration and templates live in a dedicated repository named `agent` inside the organization on branch `main`.

2. **Dedicated Session Repositories (`session-<session_uuid>`)**:
   - Each session operates in its own dedicated repository `session-<session_uuid>` inside `agent-<agent_uuid>`.
   - Root sessions are created by forking `agent-<agent_uuid>/agent` to `agent-<agent_uuid>/session-<session_uuid>`.
   - Branched sessions are created by forking the parent `session-<parent_uuid>` repository to `session-<new_session_uuid>` in `agent-<agent_uuid>`, preserving lineage and fork provenance in Gitea.
   - Sync PRs are opened across forks from `session-<session_uuid>` to base `agent`.

3. **Read-Only Upstream Mirrors (`mirrors` Organization)**:
   - Upstream repositories are mirrored into a central, system-wide Gitea organization named `mirrors`.
   - Mirror repositories are named `project-<project_name>-<url_hash>`, where `<project_name>` is the sanitized last path segment of the upstream URL and `<url_hash>` is the first 8 characters of `sha256(canonical_url)`.
   - Mirrors are configured as read-only downstream pull mirrors with automated synchronization (`mirror_interval: "10m"`).

4. **Session-Specific Writable External Mount Forks**:
   - For each mounted repository in a session, a writable fork is created in the agent's organization:
     `project-<project_name>-<url_hash>-<session_hash>`, where `<session_hash>` is `session_id.hex[:8]`.
   - Root sessions fork from `mirrors/project-<project_name>-<url_hash>`.
   - Branched sessions fork from the parent session's mount fork `agent-<agent_uuid>/project-<project_name>-<url_hash>-<parent_session_hash>`.
   - The sandbox working copy at `/projects/{mount_name}` clones directly from this session-specific fork.
   - Dual-index checkpointing pushes snapshot and semantic refs (`refs/seamus/...`, checkpoint branches, semantic branches) to this writable session fork.

5. **Eight-Character Hash Rule**:
   - All newly generated derived identifiers and path segments adhere to an 8-character convention (`sha256(canonical_url)[:8]`, `session_id.hex[:8]`).

6. **State Hydration and Soft-Delete Filtering**:
   - `HarnessStore.hydrate_from_gitea()` discovers agent organizations (`agent-<uuid>`) and session repositories (`session-<uuid>`).
   - Prefixed organizations (e.g. `archived-agent-...`) are ignored during hydration, establishing the foundation for non-destructive soft-delete / archiving.

## Consequences

- Sessions are completely isolated at the Git repository boundary, eliminating branch namespace collisions and enabling clean per-session access control.
- External upstream mirrors remain strictly read-only downstream mirrors; agent changes and checkpoints are isolated to writable per-session forks.
- Session branching preserves Git fork provenance in Gitea across both session workspaces and mounted external projects.

