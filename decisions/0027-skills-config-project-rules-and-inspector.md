# 0027. Skills Implementation Configuration, Dynamic Project Rules, and Inspector Enhancements

Date: 2026-11-03

## Status

Accepted

## Context

Following the introduction of Anthropic skills support ([0024-anthropic-skills-and-system-settings.md](./0024-anthropic-skills-and-system-settings.md), [0026-in-sandbox-skill-mount-paths.md](./0026-in-sandbox-skill-mount-paths.md)) and configurable task planning ([0025-todo-list-middleware.md](./0025-todo-list-middleware.md)), several closely related harness configuration and inspection gaps remained:

1. **Skills Implementation Toggle and Default Alignment**: While `todo_implementation` allowed selectively enabling or disabling `TodoListMiddleware`, skills were unconditionally wired into `create_deep_agent`. Furthermore, both `todo_implementation` and `skills_implementation` should default to `deepagents` out of the box until native Seamus implementations replace them.
2. **Dynamic Workspace Project Rules (`<project_rules>`)**: `DynamicSystemPromptMiddleware` assembled `<identity>`, `<operating_environment>`, `<engineering_discipline>`, `<tool_usage>`, `<communication_style>`, `<dynamic_context>`, and `<custom_instructions>`, but did not inspect the session's operational workspace (`/workspace/AGENTS.md` or `/workspace/.seamus/rules/*.md`) for repository-specific guidelines.
3. **Inspector Skills Visibility & State Delineation**: Operators had no way in the Agent Inspector UI to see which skills were discovered across workspace (`skills`, `.skills`) and system skill directories, which skills were active vs. shadowed by higher-precedence layers, or what instructions they contained. Additionally, the Inspector header labeled the entire view "Latest Inference State" even though configuration tabs (System Prompt, Tools, Skills, Inference) reflect live "Next Turn Config" while Trajectory and Todos reflect persisted checkpoint state, and multiline tool descriptions collapsed whitespace.

## Decision

1. **Configurable `skills_implementation`, `rules_implementation`, and `deepagents` Defaults**:
   - Introduce `SkillsImplementation(StrEnum)` and `RulesImplementation(StrEnum)` with values `none` and `deepagents`.
   - Set `todo_implementation`, `skills_implementation`, and `rules_implementation` on `AgentConfig` to default to `DEEPAGENTS` (`"deepagents"`), and add `rules_globs: list[str]` defaulting to `["AGENTS.md", ".seamus/rules/**/*.md"]`, propagating all fields through `AgentConfig.copy_with_overrides()`.
   - In `SessionAgentRunner._build_deep_agent()`, pass `skills=sandbox_backend.get_skill_sources()` when `skills_implementation == SkillsImplementation.DEEPAGENTS` (`None` when `NONE`), and wire `SeamusMemoryMiddleware` (subclassing DeepAgents' `MemoryMiddleware`) when `rules_implementation == RulesImplementation.DEEPAGENTS`.
   - Validate `skills_implementation`, `rules_implementation`, and `rules_globs` in both backend Pydantic models and the frontend `ConfigModal`.

2. **Configurable Project Rules over DeepAgents `MemoryMiddleware` (`SeamusMemoryMiddleware`)**:
   - Implement `resolve_session_rules(data_dir, rules_globs, workdir)` and `SeamusMemoryMiddleware(MemoryMiddleware)` in `seamus.harness.runner`, dynamically expanding `rules_globs` against the session's `data/` directory into `<agent_memory>` and `<memory_guidelines>` prompt sections managed by `MemoryMiddleware`.

3. **Skills Inspection, Middleware Prompt Visibility, and State Delineation in Agent Inspector**:
   - Add `SkillInspectInfo` (`name`, `description`, `origin_layer`, `sandbox_path`, `host_path`, `content`, `active`) and `extract_session_skills()` in `seamus.harness.inspector` with resilient frontmatter parsing. Populate `host_path` for system-wide host skills and omit it (`None`) for session workspace skills.
   - Include active middleware system prompt sections (`SeamusTodoListMiddleware`, `SkillsMiddleware`, and `MemoryMiddleware`) in both `PromptInspectInfo.scaffold` and `PromptInspectInfo.composite` so the Inspector's System Prompt tab accurately displays the full harness scaffold and effective composite prompt.
   - Surface `skills`, `skills_implementation`, `rules_implementation`, and `rules_globs` on `AgentInspectReport` and add a dedicated **Skills** tab in `AgentInspector.tsx` displaying active vs. shadowed status, origin layer, sandbox path, optional host path, description, and expandable Markdown instructions.
   - Distinguish live configuration tabs (`Next Turn Config (Live)`) from checkpoint-backed tabs (`Latest Checkpoint State`) in the Inspector header badge, and preserve multiline formatting on `.tool-description` via `white-space: pre-wrap`.

## Consequences

### Positive
- Operators can toggle `todo_implementation`, `skills_implementation`, and `rules_implementation` between `deepagents` and `none` and customize `rules_globs` per template, agent, or session, with `deepagents` enabled by default.
- Agents automatically receive repository-specific rules matching configured `rules_globs` via `SeamusMemoryMiddleware` (`MemoryMiddleware`).
- Full runtime visibility into discovered skills (with host paths for system skills), active middleware prompt sections (`todo`, `skills`, `rules`), precedence shadowing, and live vs. checkpoint state in the Agent Inspector.

