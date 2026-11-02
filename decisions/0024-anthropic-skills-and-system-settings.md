# 0024. Anthropic Skills Support, System Settings, and Gitea-Backed System Persistence

Date: 2026-11-02

## Status

Accepted

## Context

Anthropic agent skills provide modular, progressive-disclosure capabilities (via `SKILL.md` frontmatter and dynamic tool/instruction resolution) supported natively by LangChain and DeepAgents (`SkillsMiddleware`).

In Seamus, two levels of skill search are required:
1. **Agent/session-wide skills**: Situated within the session's Git-tracked operational directory (`<session_workspace>/data/.skills/` on the host, mapping directly to `/workspace/.skills` inside the OpenSandbox container).
2. **System-wide skills**: Configured via a new system settings concept containing a list of system-wide skill directories.

Unlike agent-level skills (which undergo standard Git branch/session commit cycles), system-wide skill directories are intended to be modified live on the host. However, because DeepAgents' `SkillsMiddleware` resolves and reads skills through the agent's storage backend (`SeamusOpenSandboxBackend`), external host directories must be mounted into the OpenSandbox container. Crucially, system-level skills bypass Seamus's core tenets of strict workspace isolation, provenance, and Git version control, so they must be mounted strictly read-only (`readOnly=True`) and documented with a prominent warning against their general use.

Additionally, system settings and the global configuration template (`AgentConfig`) require a persistent lifecycle independent of any specific agent or session, surviving restarts with first-run defaults without introducing new databases or persistent volumes.

## Decision

1. **Dedicated System Git Repository (`system`) in Gitea**:
   - Introduce a dedicated repository named `system` in Gitea under the admin user, managed via `WorkspaceManager`.
   - The repository tracks:
     - `settings.json`: System settings (`SystemSettings`, containing `skill_directories: list[str]`).
     - `config-template.json`: Service-wide agent configuration template (`AgentConfig`).
   - On initial startup, if the `system` repository does not exist, `WorkspaceManager` creates it and seeds first-run defaults (`skill_directories: []`, and default `AgentConfig`).
   - Local clone is maintained under `<workspace_root>/system`.
   - Modifying settings or the config template commits and pushes changes to the `system` repository.
   - When persistence is disabled (`SEAMUS_PERSISTENCE_ENABLED=false`), operations fall back to local disk or memory for fast isolated testing.

2. **System Settings API & Store (`seamus.config.settings`)**:
   - Implement `SystemSettings(BaseModel)` with `skill_directories: list[str] = Field(default_factory=list)`.
   - Implement `SystemSettingsStore` managing cached retrieval and persistence through `WorkspaceManager`.
   - Expose REST API routes `GET /settings` and `POST /settings` to inspect and update system settings.

3. **Read-Only Live Volume Mounts for System Skills in OpenSandbox**:
   - In `SeamusOpenSandboxBackend`, iterate over `SystemSettings.skill_directories`.
   - For each valid host directory, instantiate an OpenSandbox `Volume` mount with `readOnly=True`:
     `Volume(name=f"skill-{idx}", mountPath=str(Path(dir).resolve()), readOnly=True, host=Host(path=str(Path(dir).resolve())))`.
   - Mounting read-only ensures that sandboxed agents cannot mutate external host directories, while host modifications remain live and immediate.

4. **DeepAgents Skills Integration in Runner**:
   - In `SessionAgentRunner._build_deep_agent()`, assemble the skill sources in prioritized order:
     `skills = [*[str(Path(p).resolve()) for p in system_skill_dirs], "/workspace/.skills"]`.
   - Pass `skills=skills` into `create_deep_agent(...)`, which places LangChain's `SkillsMiddleware(backend=sandbox_backend, sources=skills)`.
   - Because agent-level `/workspace/.skills` is ordered last, agent-specific skills override system-level skills with matching names.

5. **Prominent README Warning on System Skills**:
   - Add a prominent warning in `README.md` explicitly stating that system-level skills are **disrecommended** and subject to future removal because they oppose Seamus's core tenets of strict isolation and Git-tracked provenance. Agent-level skills in `<workspace>/data/.skills/` must always be preferred.

6. **Future Multi-Mount and Built-In Skills Tracking**:
   - Record in `knowledge/backlog.md` a Deferred entry for discovering `<mount>/.skills` across multiple mounted repositories once multi-repo workspace mounting is supported.
   - Record in `knowledge/backlog.md` a TODO entry for built-in skills bundled with Seamus.

## Consequences

### Positive
- Full compatibility with Anthropic skills format (`SKILL.md`) and LangChain's progressive disclosure.
- Clean separation between system-wide settings and agent/session configuration.
- Restart-safe persistence for system settings and config template without additional databases or Docker volumes.
- Host-level edits to system skill directories are immediately visible inside sandboxes without container rebuilds.
- Sandboxes are protected from corrupting host skill directories via read-only volume mounts.

### Negative / Trade-offs
- System skills mounted into OpenSandbox containers still require the host paths to fall within `allowed_host_paths` configured in `sandbox.toml`.
- System-level skills operate outside session Git provenance, making runs that rely on them harder to reproduce across environments.

