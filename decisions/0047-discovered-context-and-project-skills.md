# 0047. Dynamic Context Discovery (rules_patterns) and Mounted Projects Skill Discovery

Date: 2026-11-09

## Status

Accepted

## Context

Following the evaluation in [0027-skills-config-project-rules-and-inspector.md](./0027-skills-config-project-rules-and-inspector.md) which rejected DeepAgents' mutable `<agent_memory>` `MemoryMiddleware` for static repository instructions, project and repository rules support remained outstanding on the backlog. Agents had no automated mechanism to read repository guidance (such as `AGENTS.md` or `.seamus/rules/**/*.md`) unless manually pasted into user custom instructions.

Additionally:
1. **Configuration Shape Symmetry**: While `AgentConfig` represents templates, agents, and sessions, UI and configuration capabilities across these three scopes must strictly mirror one another (ensuring templates, agents, and sessions expose identical fields, with templates permitted to be partially complete).
2. **Mounted Project Skill Discovery**: Although [0042-mount-external-git-repositories.md](./0042-mount-external-git-repositories.md) mapped external repositories into `/projects/{mount_name}` and registered project skill sources in `SeamusOpenSandboxBackend.get_skill_sources()`, project skills were missing from the Agent Inspector's extraction logic (`extract_session_skills`), and the precedence order among multiple mounted projects (`projects[0]` overriding `projects[1]`) was not explicitly inverted to match DeepAgents' "last-one-wins" resolution semantics.

## Decision

1. **Configurable `rules_patterns` Across Templates, Agents, and Sessions (INV-051, REQ-041)**:
   - Add `rules_patterns: list[str] = Field(default_factory=lambda: ["AGENTS.md", ".seamus/rules/**"])` to `AgentConfig`.
   - Propagate `rules_patterns` through `AgentConfig.copy_with_overrides()`.
   - Update `ui/src/api/types.ts` and `ConfigModal.tsx` to expose an editable list of rules pattern rows (matching the mounted repositories UX) across ConfigTemplate, Agent, and Session configuration modals.
   - Enforce the **Configuration Model Symmetry Invariant (INV-051)**: `AgentConfig` schemas and UI editing interfaces must share identical shapes across all three scopes (`ConfigTemplate`, `AgentConfig`, `SessionConfig`), with templates permitted to be partially complete (e.g. omitting API keys or base URLs).

2. **Dynamic Context Discovery and LM-XML Injection (INV-052, REQ-042)**:
   - Define `DiscoveredContextItem(BaseModel)` with `path: str` and `content: str`.
   - Add `discovered_context: list[DiscoveredContextItem] | None = None` to `SystemPromptDocument`.
   - Implement `discover_context_files(workspace_data_dir, repositories, projects_dir, rules_patterns, max_file_size_bytes=1_000_000)`:
     - Search roots: `/workspace` first, then `/projects/{mount_name}` for each external repository in `repositories` in configured order.
     - Within each root, iterate through `rules_patterns` in order:
       - Match regular files recursively (`**`), skipping directories and ignoring `.git/`.
       - Sort matched files alphabetically by relative path.
       - Deduplicate across patterns and roots preserving the earliest match.
       - Skip binary/unreadable files and files exceeding 1 MB.
       - Strip leading and trailing whitespace/newlines from content to prevent prompt pollution.
       - Construct in-sandbox paths (`/workspace/...`, `/projects/{mount_name}/...`).
   - In `SystemPromptDocument`, when `discovered_context` is empty or `None`, it is excluded via `model_dump(exclude_none=True)` and omitted from serialized LM-XML. When populated, it serializes cleanly under `<discovered_context>` as a list of item objects.
   - Inject discovered context dynamically per model turn in `SessionAgentRunner._provide_prompt_for_request()` and `build_effective_system_prompt()`, and render it in the Agent Inspector's System Prompt tab.

3. **Mounted Project Skill Discovery and Precedence Alignment (INV-035)**:
   - Align DeepAgents source registration order in `SeamusOpenSandboxBackend.get_skill_sources()` to enforce confirmed precedence:
     `bundled` > `workspace/skills` > `workspace/.skills` > `projects[0]/skills` > `projects[0]/.skills` > `projects[1]/skills` > `projects[1]/.skills` > ... > `system[0]` > `system[1]` ...
     Because DeepAgents applies "last-one-wins", sources are appended in reverse priority order (`system` reversed, then `repositories` reversed, then `workspace`, then `bundled`).
   - Update `extract_session_skills` in `src/seamus/harness/inspector.py` to scan `projects_dir / mount_name / "skills"` and `... / ".skills"` for all session repositories in configured order, marking origin layers as `Project {mount_name}` and reflecting active vs. shadowed status.

## Consequences

### Positive
- Agents automatically and dynamically discover repository conventions and rule files without mutating prompt configuration or using DeepAgents' mutable memory middleware.
- Configuration models and UI modal shapes are symmetric and unified across Template, Agent, and Session levels.
- Skills residing in mounted external Git repositories are discovered, mounted, exposed to DeepAgents with strict precedence, and visible in the Agent Inspector UI.

### Neutral / Technical Debt
- Non-fatal discovery events (e.g. context files skipped due to size limits or binary encoding) are logged; surfaced as a backlog item for an Agent Runtime Warnings panel in the UI.

