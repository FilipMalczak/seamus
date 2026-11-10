# 0052: Backlog Low-Hanging Fruits and A2UI 1.0 Upgrade

- **Date**: 2026-11-10
- **Status**: Accepted
- **Supersedes**: None

## Context

A thorough evaluation of [knowledge/backlog.md](../knowledge/backlog.md) identified multiple high-value, low/mid-effort backlog items across runtime cleanliness, UI ergonomics, prompt precision, and secret management. In addition, the A2UI client implementation in Seamus was migrated from v0.9 to the official v1.0 specification.

The addressed friction points include:

1. **A2UI Migration to v1.0 and Catalog Documentation**: Seamus previously relied on A2UI v0.9 pre-release structures. Migrating to v1.0 aligns with the official specification and `@a2ui` package releases, while documenting missing basic widgets (`Tabs`, `Modal`, `List`, `Image`, `Icon`, `AudioPlayer`, `Video`, `CheckBox`, `Slider`, `DateTimeInput`) against the canonical v1.0 schema.
2. **Legacy `ask` and `form` Tooling**: The resilient `ask` and `form` tools predated the artifact architecture and duplicated functionality now handled cleanly by `make_questionnaire` and `make_form`, leaving dead code and test inconsistencies.
3. **Prompt Ambiguity Between Scratchpad and Mounted Projects**: System prompts did not explicitly distinguish between `/workspace` (agent scratchpad for notes and plans) and `/projects/<name>/` (canonical codebase for development), occasionally leading agents to create code directly in `/workspace`.
4. **Questionnaire "Other/Custom" Redundancy**: When questionnaires enable freeform text input via `write_in=True`, models often redundantly included an explicit "Other" or "Custom" choice, confusing users.
5. **Tool Inspector Clutter**: The Agent Inspector displayed an unorganized flat list of tools without functional categories or domain indicators.
6. **Model Reasoning Effort Configuration**: Frontier reasoning models (such as `o1`, `o3-mini`, `gpt-5`) support reasoning effort tiers (`low`, `medium`, `high`, `none`), but Seamus provided no mechanism to configure this or defer to provider defaults.
7. **Obscured Symbolic Secret Expressions in UI Inputs**: Masking inputs (`type="password"`) for fields containing symbolic secret references (e.g. `${secret('/api-key')}`) made it impossible for operators to verify which secret path was referenced without re-entering the expression.
8. **System Events Misalignment in Chat Feed**: Synthetic and system events were styled similarly to user or agent messages, making it harder to visually distinguish harness operational logs.
9. **Skill Stashing Across Thread Transitions**: Thread rollover cleanly reset active skills to avoid token bloat, but lacked a mechanism for operators or tools (like `plan`) to selectively retain essential cross-phase skills (such as `artifacts`).
10. **Compound Symbolic Secret Reference Verification**: The parser supported compound string references (e.g. `postgres://${secret('/user')}:${secret('/pass')}@host:5432/${secret('/db')}`), but test coverage for composite URL interpolation and error handling was missing.

## Decisions

### 1. A2UI v1.0 Upgrade and Basic Catalog Widget Documentation
- Updated `ui/src/components/A2UIArtifactRenderer.tsx` to import from `@a2ui/react` and `@a2ui/web_core/v1_0`.
- Initialized `MessageProcessor` with `[basicCatalog]` to enable proper default catalog resolution in `createSurface`.
- Updated outbound A2UI event envelopes to `version: "1.0"`.
- Synchronized `src/seamus/skills/bundled/a2ui_components/resources/catalog.json` with the canonical A2UI v1.0 catalog definition.
- Documented all basic catalog widgets in `src/seamus/skills/bundled/a2ui_components/SKILL.md` strictly matching the v1.0 specification (including omitting unsupported properties like `step` on `Slider`).

### 2. Deletion of Legacy `ask` and `form` Tools
- Removed `ask_tool`, `form_tool`, `ResilientAskInput`, and `ResilientFormInput` from `src/seamus/harness/runner.py`.
- Purged legacy question and form event broadcasting logic and state fields.
- Cleaned up obsolete `ask` tool handling in `ui/src/hooks/useThreadStream.ts`.
- Updated existing tests in `tests/test_bundled_skills.py` and `tests/test_skills.py` to assert the presence of `make_questionnaire` and the absence of `ask`.

### 3. Prompt Differentiation: Workspace Scratchpad vs. Project Codebase
- Enhanced `src/seamus/harness/prompt.py` (`build_operating_environment`) with explicit guidelines:
  - `/workspace` is an ephemeral scratchpad dedicated to notes (`/workspace/notes`), plans, and temporary files.
  - `/projects/<name>/` is the canonical working directory for project repositories where all codebase modifications must be made.

### 4. Negative Constraint on Redundant "Other/Custom" Questionnaire Options
- Added instructions in `src/seamus/harness/prompt.py` and `src/seamus/skills/bundled/artifacts/SKILL.md` directing models never to inject explicit "Other" or "Custom" choice options when `write_in=True`, as the UI renderer automatically supplies the necessary freeform entry field.

### 5. Tool Categorization and Badging in Agent Inspector
- Introduced `categorize_tool` in `src/seamus/harness/inspector.py` assigning tools to semantic categories: `Sandbox`, `Artifacts`, `Planning`, `Skills`, `Todos`, `Web Search`, `Vault`, and `Other`.
- Added `category` field to `ToolInspectInfo`.
- Added category filter pills and color-coded badges to `AgentInspector.tsx` and `App.css`.

### 6. Model Reasoning Effort Configuration
- Defined `ReasoningEffort(StrEnum)` in `src/seamus/config/models.py` with values `DEFAULT="default"`, `NONE="none"`, `LOW="low"`, `MEDIUM="medium"`, and `HIGH="high"`.
- Added `reasoning_effort: ReasoningEffort = ReasoningEffort.DEFAULT` to `InferenceConfig`.
- In `src/seamus/harness/runner.py`, configured `ReasoningChatOpenAI` to pass `reasoning_effort` only when explicitly set to a non-default tier, allowing providers to apply their defaults when `"default"` is selected.
- Added a Reasoning Effort dropdown selector in `ConfigModal.tsx`.

### 7. Unmasking Symbolic Secret Expressions in UI Inputs
- Modified `ConfigModal.tsx` and `SettingsModal.tsx` to detect values starting with `${secret(`.
- Dynamically toggle the input field from `type="password"` to `type="text"` when a symbolic expression is present, ensuring secret paths remain readable while keeping actual literal passwords masked.

### 8. System Events Chat Alignment
- Updated `.synthetic-row` in `ui/src/App.css` to `align-self: flex-end` with `flex-direction: row-reverse`.
- System and daemon notifications are clearly distinguished on the right side of the chat feed while maintaining visual separation from standard user inputs.

### 9. Skill Stashing Across Thread Transitions
- Updated `Session.create_thread`, `store.create_thread`, and `ThreadCreateRequest` to accept `retained_skills: list[str] | None = None`.
- Updated `plan_tool` schema (`PlanTransitionInput`) and `runner.handle_plan` to accept `retained_skills: list[str]`, passing them into `runner.transition_to_phase`.
- When `retained_skills` is omitted, new threads start with clean active skills (`[]`) to avoid token bloat; when specified, the designated skills are retained across the transition.

### 10. Compound Symbolic Secret Reference Test Coverage
- Added unit tests in `tests/vault/test_parser.py` verifying non-greedy regex matching and extraction across multi-secret compound connection strings, as well as syntax error handling on malformed embedded expressions.
- Added asynchronous integration tests in `tests/vault/test_client_and_interpolator.py` verifying multi-secret template interpolation and version tracking against mock OpenBao endpoints.

## Consequences

- The codebase is free of legacy question-asking tools and dead state variables.
- A2UI artifacts conform to the official v1.0 specification and documentation.
- The web UI provides improved inspectability for tools, unmasked secret expression editing, and cleaner event feed layout.
- Agents receive clearer instructions distinguishing project roots from scratchpads and creating cleaner questionnaires.
- Reasoning effort can be tuned per agent or left to provider defaults.
- Cross-phase skill continuity is now supported without unbounded token leakage.

