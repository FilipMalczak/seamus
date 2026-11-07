# 0036. Mount Bundled Skills via Shared Workspace Volume in Containerized Sandboxes

Date: 2026-11-07

## Status

Accepted

## Context

Bundled platform skills (`src/seamus/skills/bundled/`, containing `artifacts` and `a2ui_components`) were integrated into the prompt generator and inspector, and mounted into OpenSandbox via `SeamusOpenSandboxBackend.build_bundled_skill_volume()`.

However, `build_bundled_skill_volume()` previously mounted bundled skills solely using a host path:
```python
Volume(
    name="skills-bundled",
    mountPath="/skills/bundled",
    readOnly=True,
    host=Host(path=str(BUNDLED_SKILLS_DIR.resolve())),
)
```

In containerized deployments (such as Docker Compose, where the backend service runs in a container and `OPENSANDBOX_WORKSPACE_VOLUME=seamus-workspaces` is configured):
1. `BUNDLED_SKILLS_DIR.resolve()` resolves to `/app/src/seamus/skills/bundled` inside the backend container.
2. OpenSandbox communicates with the host Docker daemon via `/var/run/docker.sock` to create sibling sandbox containers.
3. The Docker daemon interprets `Host(path="/app/src/seamus/skills/bundled")` from the Docker host's perspective, where `/app/...` does not exist. Docker automatically creates an empty directory on the host and mounts it into the sandbox container.
4. Consequently, while the Inspector (running inside the backend container) discovers the skills and references them in the system prompt (`/skills/bundled/artifacts/SKILL.md`), the agent inside the sandbox finds `/skills/bundled` completely empty, resulting in `file_not_found` and `No files found` errors.

By contrast, session data, artifacts, and notes directories mount correctly in containerized setups because they detect `self.settings.workspace_volume` and mount via `pvc=PVC(claimName=self.settings.workspace_volume, subPath=...)` against the shared `seamus-workspaces` Docker volume mounted at `/app/workspaces`.

## Decision

1. **Synchronize Bundled Skills to Shared Workspace Storage**:
   - Provide a helper function `sync_bundled_skills(target_dir: Path) -> Path` that synchronizes built-in platform skills from `BUNDLED_SKILLS_DIR` into `target_dir` (`workspace_root / "bundled_skills"`).
   - Synchronize on `GitWorkspaceManager` initialization and idempotently in `build_bundled_skill_volume()`. This guarantees that code updates or container recreations immediately reflect updated skills in the shared volume.

2. **PVC-Backed Bundled Skill Volume in Containerized Environments**:
   - In `SeamusOpenSandboxBackend.build_bundled_skill_volume()`:
     - When `self.settings.workspace_volume` is present:
       - Ensure `workspace_root / "bundled_skills"` is synced.
       - Return an OpenSandbox `Volume` mounted at `/skills/bundled` with `readOnly=True`, using `pvc=PVC(claimName=self.settings.workspace_volume, createIfNotExists=True, deleteOnSandboxTermination=False)` and `subPath="bundled_skills"`.
     - When `self.settings.workspace_volume` is unset (host development or lightweight unit testing):
       - Retain the fallback `host=Host(path=str(BUNDLED_SKILLS_DIR.resolve()))`.

3. **Workspace Isolation**:
   - The shared `bundled_skills` directory resides at `workspace_root / "bundled_skills"` (e.g. `/app/workspaces/bundled_skills`).
   - This directory is situated outside individual session repositories (`workspace_root / {agent_id} / {session_id}`) and outside the system repository (`workspace_root / "_system"`), ensuring zero interference with Git tracking, checkpoint commits, or pull/push synchronization.

4. **Preserved Precedence & Mount Paths**:
   - In-sandbox paths (`/skills/bundled`) and precedence rules (top-priority in `get_skill_sources()`, origin layer `Bundled` in Inspector) remain completely unchanged.

## Consequences

### Positive
- Bundled platform skills (`artifacts`, `a2ui_components`) are accessible and readable within the sandbox container under both containerized Docker Compose setups and host development environments.
- Zero host-filesystem leakage or machine-specific dependencies for built-in platform skills.
- Read-only container enforcement ensures sandboxed agents cannot mutate built-in platform skills.

### Negative / Trade-offs
- Requires synchronizing static bundled skill files into the workspace volume storage root upon backend initialization and sandbox provisioning.

