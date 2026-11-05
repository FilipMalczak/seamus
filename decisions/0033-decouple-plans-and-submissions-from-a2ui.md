# 0033: Decouple Plans and Submissions from A2UI

- **Status**: Decided
- **Date**: 2026-11-05
- **Deciders**: Seamus Engineering
- **Consulted**: Seamus Architecture Team

## Context

In [0031-migrate-a2ui-to-adaptive-cards.md](./0031-migrate-a2ui-to-adaptive-cards.md), Seamus migrated its renderable artifact system from A2UI v0.9 to Microsoft Adaptive Cards v1.5. Interactive artifacts (questionnaires and forms) were transitioned to store user responses in `submission.json` upon submission, while cards are defined in `card.json`.

However, an audit of artifact persistence and prompt generation revealed remnants of A2UI terminology and assumptions:
1. **Plan Ingestion in Prompt Composer**: In `src/seamus/harness/prompt.py`, the system prompt generator for `plan/execute` phase pointed the agent to read `/artifacts/plans/<plan_id>/updateDataModel.json` under `/plan/content`. Under Adaptive Cards, this file was no longer produced, causing executing agents to look for a non-existent file.
2. **Legacy Fallback Readers**: Both `ArtifactResolver` and `handle_read_artifact_submission` retained fallback branches attempting to read `updateDataModel.json` and unpack `{updateDataModel: {value: ...}}`.
3. **Frontend Value Binding**: The UI renderer retained a fallback check for `artifact.data?.updateDataModel?.value`.

## Decision

1. **Persist Canonical Plan Markdown (`plan.md`) Alongside `card.json`**:
   - `PlanBuilder.create_plan` and `PlanBuilder.update_plan` write `/artifacts/plans/<plan_id>/plan.md` containing raw, unescaped GitHub-Flavored Markdown alongside `card.json` (Adaptive Card representation) and `manifest.json`.
   - `PlanBuilder.read_plan` prioritizes reading directly from `plan.md` when present, falling back to inspecting `card.json` for backward compatibility.
   - Exposing `plan.md` gives the agent in the OpenSandbox container a clean, format-agnostic Markdown document to read without having to parse Adaptive Card JSON schema structures or synthetic data models.

2. **Decouple Prompt Composition from Data Models**:
   - Update `ActivePlanPromptContext` in `src/seamus/harness/prompt.py`: replace `plan_data_model_path: str` with `plan_path: str` pointing directly to `/artifacts/plans/<plan_id>/plan.md`.
   - Update execute phase system prompt instructions to direct the agent to read `/artifacts/plans/<plan_id>/plan.md`.

3. **Format-Agnostic Submissions (`submission.json`)**:
   - Affirm that user submissions for interactive artifacts remain pure, unadorned JSON dictionaries in `submission.json` (e.g. `{"database": "sqlite", "auth": true}`).
   - Submissions are not wrapped in external protocol envelopes.

4. **Eradicate Obsolete `updateDataModel` Fallbacks**:
   - Remove fallback lookups for `updateDataModel.json` from `ArtifactResolver.load_artifact` and `SessionAgentRunner.handle_read_artifact_submission`.
   - Remove `updateDataModel` checks from `AdaptiveCardArtifactRenderer.tsx`.

## Consequences

- Agents executing plans in OpenSandbox have direct access to `/artifacts/plans/<plan_id>/plan.md`.
- No lingering references to A2UI or `updateDataModel` remain in active code or prompts.
- Submissions and plans are decoupled from any specific UI protocol and easily consumed by LLM tooling.

