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

1. **Configurable `skills_implementation` and `deepagents` Defaults**:
   - Introduce `SkillsImplementation(StrEnum)` with values `none` and `deepagents`.
   - Set both `todo_implementation` and `skills_implementation` on `AgentConfig` to default to `DEEPAGENTS` (`"deepagents"`), propagating both fields through `AgentConfig.copy_with_overrides()`.
   - In `SessionAgentRunner._build_deep_agent()`, pass `skills=sandbox_backend.get_skill_sources()` when `skills_implementation == SkillsImplementation.DEEPAGENTS`, and `skills=None` when `skills_implementation == SkillsImplementation.NONE`.
   - Validate `skills_implementation` in both the backend Pydantic models and the frontend `ConfigModal`.

2. **Dynamic Project Rules Discovery (`discover_project_rules`)**:
   - Extend `SystemPromptDocument` with `project_rules: str | None = None`.
   - Implement `discover_project_rules(data_dir: Path | None) -> str | None` in `seamus.harness.prompt`, inspecting `AGENTS.md` and sorted `.md` / `.txt` files under `.seamus/rules/` within the session's `data/` directory.
   - Inject discovered project rules into `<project_rules>` on every inference turn via `SessionAgentRunner.build_effective_system_prompt()` and expose `project_rules` as an inspectable prompt layer in `PromptInspectInfo` and the Inspector UI.

3. **Skills Inspection and State Delineation in Agent Inspector**:
   - Add `SkillInspectInfo` (`name`, `description`, `origin_layer`, `sandbox_path`, `content`, `active`) and `extract_session_skills()` in `seamus.harness.inspector` with resilient frontmatter parsing that tolerates unquoted colons/braces in `SKILL.md` descriptions.
   - Surface `skills` and `skills_implementation` on `AgentInspectReport` and add a dedicated **Skills** tab in `AgentInspector.tsx` displaying active vs. shadowed status, origin layer, sandbox path, description, and expandable Markdown instructions.
   - Distinguish live configuration tabs (`Next Turn Config (Live)`) from checkpoint-backed tabs (`Latest Checkpoint State`) in the Inspector header badge, and preserve multiline formatting on `.tool-description` via `white-space: pre-wrap`.

## Consequences

### Positive
- Operators can toggle both `todo_implementation` and `skills_implementation` between `deepagents` and `none` per template, agent, or session, with `deepagents` enabled by default.
- Agents automatically receive repository-specific rules from `/workspace/AGENTS.md` and `/workspace/.seamus/rules/` in `<project_rules>` without manual prompt copying.
- Full runtime visibility into discovered skills, precedence shadowing, and live vs. checkpoint state in the Agent Inspector.

