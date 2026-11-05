# 0032: Operational Mode in AgentConfig and Default Mode & Model Updates

- **Date**: 2026-11-05
- **Status**: Accepted
- **Supersedes**: None

## Context

Following the formalization of operational modes (`chat` and `plan`) in [0030-operational-modes-and-plan-mode.md](./0030-operational-modes-and-plan-mode.md), several testing pain points were identified:
1. The system model default needed to be uniformly updated to `openai/gpt-oss-120b` across all fixtures, presets, and runners (replacing lingering `gpt-oss-20b` references).
2. Sessions previously always started in `chat` mode by default, requiring manual mode switching on newly created agents and sessions. Given that Seamus prioritizes structured plan-first autonomous engineering, `plan` mode (discuss phase) is the intended default operating posture.
3. Operational mode was stored only as a transient or per-thread property rather than a formal, inheritable part of `AgentConfig`. Consequently, agents could not be configured upfront with a default operational mode, and updating the mode in a session was disconnected from the session's persistent configuration snapshot.

## Decisions

### 1. Default Model: `openai/gpt-oss-120b`
- `AgentConfig.model_name` defaults to `openai/gpt-oss-120b`.
- Environment loading in `ConfigTemplateStore._load_from_environment` defaults to `openai/gpt-oss-120b`.
- All lingering test references to `openai/gpt-oss-20b` are standardized to `openai/gpt-oss-120b`.

### 2. Operational Mode as a First-Class Configuration Property (`AgentConfig.mode`)
- `AgentConfig` now includes `mode: str = OperationalMode.PLAN.value`.
- `OperationalMode(StrEnum)` is defined under `seamus.config.models` with values `CHAT = "chat"` and `PLAN = "plan"`.
- `copy_with_overrides` preserves or overrides `mode` when merging configurations.
- The service-wide `ConfigTemplateStore` derives initial agent configurations with `mode: plan` (or overridden via `DEFAULT_MODE`/`SEAMUS_MODE` environment variables).

### 3. Entity Inheritance and Initial Thread Spawning
- **Template to Agent**: When `create_agent` derives an agent configuration from the singleton `ConfigTemplate`, the agent's configuration snapshot inherits `mode`.
- **Agent to Session**: When `Agent.create_session` creates a session, `session.config` is derived from `agent.config` with any session-specific overrides applied.
- **Session Initial Thread**: `Session.create_thread` checks `self.config.mode` when opening its initial thread, ensuring newly spawned sessions immediately begin in `plan` mode (`discuss` phase). Subsequent threads inherit the mode of the preceding thread unless explicitly overridden.
- **Normalization Defaults**: `get_mode_descriptor` and `normalize_mode_and_phase` in `seamus.domain.modes` default unknown or missing modes to `plan` (`discuss` phase).

### 4. Session-Level Mode Switching and Persistence
- `HarnessStore.switch_session_mode` updates `session.config.mode = target_mode` and persists the updated session configuration to Git via `ws_mgr.commit_session_config(session)`.
- If the current open thread is empty, `create_thread` reuses the empty thread in place, updating its mode and phase; if non-empty, it closes the previous thread and opens a new thread.

### 5. Web UI Toggle and Form Updates
- `ChatArea` accepts `sessionMode?: string` (`activeSession?.config?.mode`), allowing the mode toggle buttons in the top action bar to control and highlight the active mode at the session level.
- The thread breadcrumb bar continues to display the specific historical mode badge of the thread currently in view.
- `ConfigModal` includes a "Default Operational Mode" dropdown in the form view (`plan` vs `chat`), enabling direct configuration of mode across templates, agents, and sessions.

