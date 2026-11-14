# 0063: Remove Inspector Trajectory Tab and Include Mounted Repository Changes in Changes Tab

Date: 2026-11-14
Status: Accepted

## Context

1. The Agent Inspector (`ui/src/components/AgentInspector.tsx`) previously included a **Trajectory** tab (`subTab === "messages"`) duplicating conversation history already shown in the main Chat view.
2. The Changes tab (`ui/src/components/ChangesViewer.tsx` backed by `GET /api/v-alpha/agent/{agent_id}/session/{session_id}/diff`) only displayed the agent repository's Sync PR diff (`data/` and `artifacts/`). Changes made by the agent inside mounted external Git repositories under `/projects/{mount_name}` — including uncommitted/untracked edits, new commits, and branch switches relative to the configured branch — were not visible in the Changes tab.

## Decision

1. **Remove Inspector Trajectory Tab (UI)**:
   - Removed `"messages"` from `SubTab`, the `Trajectory` tab button, and the message-trajectory panel in `ui/src/components/AgentInspector.tsx`, along with its unused CSS rules in `ui/src/App.css`.
   - Kept `history` on `AgentInspectReport` in `src/seamus/harness/inspector.py` so backend inspection consumers and E2E tests remain unaffected.

2. **Mounted Repository Diffs, Commits, and Branch Changes in `/diff` and `ChangesViewer`**:
   - **Initial Base Commit Recording**: `ExternalRepositoryManager.provision_session_working_copy` (`src/seamus/persistence/external_repo.py`) records the initial `HEAD` SHA at mount time to `.seamus_indexes/{attachment_id}.base_commit` (outside `/projects/{mount_name}`). When unavailable, `ExternalRepositoryManager._resolve_base_commit` falls back to `origin/{repo_config.branch}` or `repo_config.branch`.
   - **Non-Mutating Diff & Metadata Collection**: Added `ExternalRepositoryManager.get_working_copy_changes` to compute:
     - Current branch vs. configured `repo_config.branch` (`branch_changed`).
     - Commits reachable from `HEAD` since `base_commit` (`git log base_commit..HEAD`).
     - Full unified diff from `base_commit` to the current working tree (covering commits, staged changes, unstaged changes, and non-ignored untracked files) using an alternate `GIT_INDEX_FILE` (`git read-tree HEAD` + `git add -A -- .` + `git diff --cached --no-color <base_commit>`), leaving `.git/index` and `HEAD` untouched.
   - **API & UI**: Extended `SessionDiffResponse` (`src/seamus/server/schemas.py`, `src/seamus/server/routes/sessions.py`, `ui/src/api/types.ts`) with `mounted_repos: list[MountedRepoDiffInfo]`. Updated `ChangesViewer.tsx` to render mounted repository sections in both the file sidebar and diff viewport, displaying branch transitions (`configured_branch → current_branch`), commit lists, and syntax-highlighted file diffs.

## Cross-References

- [0011-agent-inspector.md](./0011-agent-inspector.md)
- [0015-session-changes-diff-tab.md](./0015-session-changes-diff-tab.md)
- [0042-mount-external-git-repositories.md](./0042-mount-external-git-repositories.md)

