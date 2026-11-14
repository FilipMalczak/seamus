# 0064. `start_executing` Tool for `plan/make` When Artifacts Are Disabled

Date: 2026-11-15

## Status

Accepted

## Context

In [0055-artifacts-implementation-toggle.md](./0055-artifacts-implementation-toggle.md), setting `artifacts_implementation = "none"` disables all artifact tools (including `make_plan`, `update_plan`, `edit_plan`) and omits the interactive Plan tab and **Proceed** button.

However, in Plan mode's Make phase (`plan/make`), the **Proceed** button on the Plan artifact tab is the mechanism that transitions the session from `plan/make` to `plan/execute`. Without an alternative transition mechanism when `artifacts_implementation == "none"`, the agent had no tool to transition from `plan/make` to `plan/execute`, and the Make-phase system prompt explicitly stated that no transition tool existed.

## Decision

1. **Domain & Tool Resolution (`src/seamus/domain/modes.py`)**:
   - Add `"start_executing"` to `ALL_HARNESS_TOOLS` and `PLAN_MAKE_PHASE.tools`.
   - In `resolve_available_harness_tools`, keep `"start_executing"` when `artifacts_implementation == ArtifactsImplementation.NONE` (only in `plan/make`), and discard `"start_executing"` when artifacts are enabled (`ArtifactsImplementation.SEAMUS`), preserving the **Proceed** button workflow.

2. **Runner & Inspector (`src/seamus/harness/runner.py`, `src/seamus/harness/inspector.py`, `src/seamus/harness/resources/tool_labeling.json`)**:
   - Define `StartExecutingInput` (mirroring `PlanTransitionInput` with optional `retained_skills`) and `SessionAgentRunner.handle_start_executing`.
   - `handle_start_executing` validates that the open thread is in `plan/make` and `session.config.artifacts_implementation == ArtifactsImplementation.NONE`, then schedules `_pending_phase_transition = ("plan", "execute", True)` so the harness closes the Make thread, opens a fresh Execute thread, and auto-wakes the agent.
   - Bind `start_executing` in `_build_deep_agent` when `artifacts_implementation == NONE`, register it in Inspector `dummy_tools`, and label it in `tool_labeling.json`.

3. **Make-Phase System Prompt (`src/seamus/harness/prompt.py`)**:
   - When `artifacts_implementation == NONE`, instruct the agent in `plan/make` to author and present the full Markdown implementation plan in chat (noting `/workspace` is read-only), await user approval in chat, and call `start_executing()` to transition to Execute.
   - When `artifacts_implementation == SEAMUS`, keep the existing `make_plan` + **Proceed** button instructions unchanged.

## Consequences

### Positive
- Plan mode (`discuss -> make -> execute`) is fully functional end-to-end when `artifacts_implementation == "none"`.
- Behavior when `artifacts_implementation == "seamus"` remains unchanged and continues to rely on the Plan tab's **Proceed** button.

### Negative / Trade-offs
- In `plan/make` with `artifacts_implementation == "none"`, `/workspace` remains read-only, so the plan is presented in chat rather than persisted as a Plan artifact.

