# 0055. Artifacts Implementation Toggle and Gating Guard

Date: 2026-11-12

## Status

Accepted

## Context

Seamus features rich interactive artifacts including A2UI renderable surfaces, questionnaires, forms, and plan authoring workflows backed by tools (`make_artifact`, `make_questionnaire`, `make_form`, `make_plan`, `update_plan`, `edit_plan`, and `wait_for_click`) and bundled skills (`artifacts`, `a2ui_components`).

However, some workflows, smaller models, or operational configurations do not require or want interactive artifact capabilities. In these scenarios:
1. Exposing artifact tools consumes model parameter attention and causes unnecessary hallucination of complex UI components.
2. The bundled `artifacts` and `a2ui_components` skills consume context tokens and disclose unused tools.
3. Extensive instructions on interactive questionnaires, forms, button manifests, answers.md, and `/artifacts` mount paths clutter the system prompt.

Following the design pattern established by `todo_implementation` ([0049-native-lmxml-todo-planning.md](./0049-native-lmxml-todo-planning.md)), `skills_implementation` ([0048-native-lmxml-skills-system.md](./0048-native-lmxml-skills-system.md)), and `web_search` ([0050-web-search-tool.md](./0050-web-search-tool.md)), artifact capabilities should be configurable via an extensible enum field rather than an ad-hoc boolean flag.

## Decision

1. **Enum Configuration (`ArtifactsImplementation`)**:
   - Define `ArtifactsImplementation(StrEnum)` with values:
     - `NONE = "none"`: Disables artifact support completely.
     - `SEAMUS = "seamus"`: Default status quo enabling full A2UI and interactive artifact capabilities.
   - Add `artifacts_implementation: ArtifactsImplementation = ArtifactsImplementation.SEAMUS` to `AgentConfig`.
   - Propagate `artifacts_implementation` across the configuration inheritance hierarchy via `AgentConfig.copy_with_overrides()`.

2. **Tool Gating**:
   - In `resolve_available_harness_tools`: accept `artifacts_implementation`. When `artifacts_implementation == ArtifactsImplementation.NONE`, discard `make_artifact`, `make_questionnaire`, `make_form`, `make_plan`, `update_plan`, `edit_plan`, and `wait_for_click`.
   - In `SessionAgentRunner._build_deep_agent`: omit artifact tools from the bound toolset when building the LangGraph execution graph with `artifacts_implementation == ArtifactsImplementation.NONE`.
   - In `SessionAgentRunner.get_active_tools_for_request`: pass `session.config.artifacts_implementation` to dynamically filter out any artifact tools.

3. **Skills Discovery Gating**:
   - In `discover_session_skills` and `extract_session_skills`: accept `artifacts_implementation`. When `NONE`, filter out the `artifacts` and `a2ui_components` skills from discovered session skills.
   - In `OpenSandboxBackend.get_skill_sources`: when `artifacts_implementation == ArtifactsImplementation.NONE`, omit `/skills/bundled` from DeepAgents skill sources.
   - In `build_middleware_prompt_sections`: omit `/skills/bundled` when `artifacts_implementation == ArtifactsImplementation.NONE`.

4. **Prompt Sanitization**:
   - In `build_user_inquiry`: return `None` when `artifacts_implementation == ArtifactsImplementation.NONE`, omitting the `<user_inquiry>` block and all rules regarding questionnaires, forms, and button manifests.
   - In `build_operating_environment`: when `artifacts_implementation == ArtifactsImplementation.NONE`, set `artifacts_directory=None` and `artifacts_access=None`, and omit all descriptions of `/artifacts` mounts and approved plan artifacts from persistence instructions.
   - In `build_operational_mode_section`: when `artifacts_implementation == ArtifactsImplementation.NONE`, remove references to inquiry tools, `make_plan`, `update_plan`, `edit_plan`, and the dedicated Plan artifact tab across Discuss, Make, and Execute phases.

5. **User Interface and Inspector Integration**:
   - In `ui/src/api/types.ts`: add `ArtifactsImplementation = "none" | "seamus"` and declare `artifacts_implementation` in `AgentConfig` and `AgentInspectReport`.
   - In `ui/src/components/ConfigModal.tsx`: add validation and a dropdown select for Artifacts Support (`seamus` vs `none`).
   - In `AgentInspectReport`: include `artifacts_implementation` and filter reported tools accordingly.

## Consequences

### Positive
- Users can disable artifacts globally in template configuration or per session.
- When disabled, prompts and tool manifests are significantly smaller, cleaner, and free of artifact baggage.
- Consistent with existing Seamus configuration enums (`todo_implementation`, `skills_implementation`, `web_search`).

### Negative / Trade-offs
- In Plan mode with `artifacts_implementation: none`, plan authoring does not produce an interactive Plan tab or Proceed button; the agent formulates plans via standard files in the workspace and chat.

