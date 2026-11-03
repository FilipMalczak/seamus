# 0027. Skills Implementation Configuration and Inspector Enhancements

Date: 2026-11-03

## Status

Accepted

## Context

Following the introduction of Anthropic skills support ([0024-anthropic-skills-and-system-settings.md](./0024-anthropic-skills-and-system-settings.md), [0026-in-sandbox-skill-mount-paths.md](./0026-in-sandbox-skill-mount-paths.md)) and configurable task planning ([0025-todo-list-middleware.md](./0025-todo-list-middleware.md)), several closely related harness configuration and inspection gaps remained:

1. **Skills Implementation Toggle and Default Alignment**: While `todo_implementation` allowed selectively enabling or disabling `TodoListMiddleware`, skills were unconditionally wired into `create_deep_agent`. Furthermore, both `todo_implementation` and `skills_implementation` should default to `deepagents` out of the box until native Seamus implementations replace them.
2. **Inspector Skills Visibility, Middleware Prompt Sections, & State Delineation**: Operators had no way in the Agent Inspector UI to see which skills were discovered across workspace (`skills`, `.skills`) and system skill directories, which skills were active vs. shadowed by higher-precedence layers, what host paths backed system skills, or what instructions they contained. In addition, the `TodoListMiddleware` and `SkillsMiddleware` system prompt sections were missing from the Inspector's System Prompt views (`Scaffold` and `Composite`), the Inspector header labeled the entire view "Latest Inference State" even though configuration tabs (System Prompt, Tools, Skills, Inference) reflect live "Next Turn Config" while Trajectory and Todos reflect persisted checkpoint state, and multiline tool descriptions collapsed whitespace.
3. **Evaluation of DeepAgents `MemoryMiddleware` for Project Rules**: We evaluated wiring project rules (`AGENTS.md`, `.seamus/rules/**/*.md`) over DeepAgents' built-in `MemoryMiddleware`, but found that `MemoryMiddleware` frames loaded files as `<agent_memory>` and appends `<memory_guidelines>` instructing the LLM to self-modify those files as mutable memory. Project rules support is therefore kept on the backlog for a native Seamus implementation that injects loaded rule files cleanly into LM-XML.

## Decision

1. **Configurable `skills_implementation` and `deepagents` Defaults**:
   - Introduce `SkillsImplementation(StrEnum)` with values `none` and `deepagents`.
   - Set both `todo_implementation` and `skills_implementation` on `AgentConfig` to default to `DEEPAGENTS` (`"deepagents"`), propagating both fields through `AgentConfig.copy_with_overrides()`.
   - In `SessionAgentRunner._build_deep_agent()`, pass `skills=sandbox_backend.get_skill_sources()` when `skills_implementation == SkillsImplementation.DEEPAGENTS`, and `skills=None` when `skills_implementation == SkillsImplementation.NONE`.
   - Validate `skills_implementation` in both the backend Pydantic models and the frontend `ConfigModal`.

2. **Skills Inspection, Middleware Prompt Visibility, and State Delineation in Agent Inspector**:
   - Add `SkillInspectInfo` (`name`, `description`, `origin_layer`, `sandbox_path`, `host_path`, `content`, `active`) and `extract_session_skills()` in `seamus.harness.inspector` with resilient frontmatter parsing that tolerates unquoted colons/braces in `SKILL.md` descriptions. Populate `host_path` for system-wide host skills and omit it (`None`) for session workspace skills.
   - Include active middleware system prompt sections (`SeamusTodoListMiddleware` and `SkillsMiddleware`) in both `PromptInspectInfo.scaffold` and `PromptInspectInfo.composite` so the Inspector's System Prompt tab accurately displays the full harness scaffold and effective composite prompt.
   - Surface `skills` and `skills_implementation` on `AgentInspectReport` and add a dedicated **Skills** tab in `AgentInspector.tsx` displaying active vs. shadowed status, origin layer, sandbox path, optional host path, description, and expandable Markdown instructions.
   - Distinguish live configuration tabs (`Next Turn Config (Live)`) from checkpoint-backed tabs (`Latest Checkpoint State`) in the Inspector header badge, and preserve multiline formatting on `.tool-description` via `white-space: pre-wrap`.

## Consequences

### Positive
- Operators can toggle both `todo_implementation` and `skills_implementation` between `deepagents` and `none` per template, agent, or session, with `deepagents` enabled by default.
- Full runtime visibility into discovered skills (with host paths for system skills), active middleware prompt sections (`todo`, `skills`), precedence shadowing, and live vs. checkpoint state in the Agent Inspector.
- Avoids conflating repository project rules with DeepAgents' mutable `<agent_memory>` middleware, preserving a clean path for native LM-XML project rules.

