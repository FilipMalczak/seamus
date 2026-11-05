# 0031. Full Migration from A2UI to Microsoft Adaptive Cards

Date: 2026-11-05

## Status

Accepted

## Context

In [0029](./0029-SUPERSEDED-a2ui-questionnaire-artifacts.md), we adopted A2UI v0.9 for interactive agent artifacts (embedded questionnaires, tabbed forms, and tabbed plans). While A2UI provided a baseline for declarative surfaces, operational experience and a successful spike (`spike-adaptive-cards`) revealed significant friction:
1. **Protocol Complexity & Redundant Files**: A2UI modeled surfaces as event streams requiring separate files on disk (`createSurface.json`, `updateComponents.json`, `updateDataModel.json`, `deleteSurface.json`), leading to synthetic `.jsonl` diffs in the Changes viewer, fragmented state resolution, and complex catalog configuration.
2. **Underwhelming Formatting & Ecosystem**: Styling A2UI primitives in a dark-themed coding harness was constrained by catalog limitations, while plans rendered as flat unformatted text blocks without document hierarchy.
3. **Commenting Unreadiness**: Adding interactive features like plan commenting and section feedback was hindered by A2UI's rigid widget catalog and component update models.

Microsoft Adaptive Cards (schema v1.5) provides a battle-tested, standardized JSON card format with rich input primitives (`Input.ChoiceSet`, `Input.Text`), hierarchical containers, declarative action handling (`Action.Submit`), extensible host configuration, and clean markdown processing.

## Decision

1. **Adopt Microsoft Adaptive Cards (v1.5)**:
   - Completely replace A2UI v0.9 across backend domain models, builders, runners, frontend components, and bundled skills with Microsoft Adaptive Cards.
   - Deprecate and remove `@a2ui/react` and `@a2ui/web_core` dependencies from the frontend package.
   - Standardize on schema URI `http://adaptivecards.io/schemas/adaptive-card.json` and version `1.5`.

2. **Clean Artifact Disk Hierarchy & Redundant File Elimination**:
   - Eliminate all A2UI event stream files (`createSurface.json`, `updateComponents.json`, `updateDataModel.json`, `deleteSurface.json`).
   - Standardize artifact persistence under `<session_dir>/artifacts/<kind>/<name>/`:
     - `card.json`: Canonical Adaptive Card definition.
     - `manifest.json`: Presentation and cadence manifest (class-level or instance override).
     - `submission.json`: User response payload written upon form/questionnaire submission.
     - `closed.json`: Closure marker written upon artifact submission, approval, or explicit closing.
   - Keep OpenSandbox mounting `/artifacts` as strictly read-only.
   - An artifact is closed if and only if `closed.json` (or `submission.json`) exists at its instance level.

3. **Domain & API Cleanliness**:
   - Refactor `ArtifactInfo` to expose `card: dict[str, Any]` and optional `data: dict[str, Any] | None`. Remove `surface`, `components`, and `delete_surface`.

4. **Structured Plan Cards & Commenting Readiness**:
   - Author plans as structured Adaptive Card documents with clear container IDs:
     - `plan_header`: Title, badge, and metadata.
     - `plan_content`: Formatted markdown document body.
     - `plan_comments`: Structured container for feedback and comments.
     - `plan_actions`: "Proceed" submission button.
   - Provide distinct `Action.Submit` actions (`submit_questionnaire`, `proceed_plan`, `add_comment`) ensuring immediate extensibility for plan commenting in subsequent iterations.

5. **Frontend Rendering & Typography**:
   - Implement `AdaptiveCardArtifactRenderer` utilizing `adaptivecards` (v3.x) with custom `HostConfig` matching Seamus's dark palette.
   - Integrate `markdown-it` with HTML typography styling matching `.markdown-content` (headings, syntax-highlighted code blocks, tables, blockquotes).
   - In the Changes tab, present real git diffs of `card.json` and `submission.json` with segmented "Diff" / "Rendered" view toggles.

6. **Documentation & Bundled Skills**:
   - Realign `src/seamus/skills/bundled/artifacts/SKILL.md` to instruct agents on Adaptive Cards.
   - Create `knowledge/adaptive_cards.md` as the durable system guide for interactive card lifecycles.
   - Scrub all non-decision references to A2UI across documentation and `knowledge/backlog.md`.

## Consequences

- Streamlined filesystem storage with fewer, self-contained files.
- Greatly improved visual fidelity for plans and questionnaires.
- Elimination of external A2UI catalog network resolution.
- Native extensibility for inline plan commenting.

