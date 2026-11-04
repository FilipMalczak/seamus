# 0029. A2UI Questionnaire Artifacts, Read-Only Sandboxing, and Bundled Platform Skills

Date: 2026-11-04

## Status

Accepted

## Context

Seamus agents require a mechanism to present structured, interactive interfaces to users—starting with questionnaires (sets of closed questions with optional write-in fields) to gather human preferences, design decisions, or clarifying answers before proceeding with tasks.

We selected **A2UI v0.9** as our representation format. A2UI structures UI state as an event sequence:
1. `createSurface`: declares the surface ID, basic catalog URL, and data model dispatch configuration.
2. `updateComponents`: composes the UI component tree (additive across updates).
3. `updateDataModel`: sets values bound to component paths (additive and overwriting by JSON path).
4. `deleteSurface`: declares that a surface is deleted/closed.

To integrate this cleanly with Seamus's core tenets of strict workspace isolation, Git provenance, and sandbox safety, we require:
- Storing artifacts on disk within the session workspace (`<session_workspace>/artifacts/`), mounted into the OpenSandbox container as `/artifacts/` strictly read-only (`readOnly=True`).
- A 3-tier hierarchical file lookup (`/artifacts/<class>/<instance>/<file>` -> `/artifacts/<class>/<file>` -> `/artifacts/<file>`) to allow shared defaults at higher levels while permitting instance-specific overrides.
- Special handling for surface closure: an artifact is closed if and only if `deleteSurface.json` is present directly at its instance level (`/artifacts/<class>/<instance>/deleteSurface.json`); no upward traversal occurs for deletion.
- A specialized agent tool `ask` that batches questions during an inference turn into a single questionnaire artifact under `/artifacts/questionnaires/<uuid>/updateComponents.json`.
- A blocking conversation cadence (`cadence=blocking`) that disables user text input and rejects chat messages with HTTP 409 while open questionnaires exist.
- Form submission that writes canonical `updateDataModel.json` and `deleteSurface.json`, synthesizes a tool call `read_artifact_submission(<uuid>)` with `{data: ...}`, and resumes agent execution.
- Bundled platform skills mounted at `/skills/bundled` with highest precedence in the DeepAgents skill hierarchy.

## Decision

1. **Standardized Surface ID (`surface`)**:
   - `surfaceId` is standardized to `"surface"` across all A2UI files (`createSurface.json`, `updateComponents.json`, `updateDataModel.json`, `deleteSurface.json`).
   - Artifact identity is tracked via filesystem coordinates (`/artifacts/<class>/<instance>`), not by varying surface IDs.

2. **Hierarchical Artifact Storage & Resolution**:
   - Within each session workspace (`<session_workspace>/artifacts/`), files are resolved by checking:
     1. `/artifacts/<class>/<name>/<file>`
     2. `/artifacts/<class>/<file>`
     3. `/artifacts/<file>`
   - `createSurface.json` defaults at `/artifacts/createSurface.json`:
     ```json
     {
       "version": "v0.9",
       "createSurface": {
         "surfaceId": "surface",
         "catalogId": "https://a2ui.org/specification/v0_9/basic_catalog.json",
         "sendDataModel": true
       }
     }
     ```
   - Class-level manifest defaults at `/artifacts/questionnaires/manifest.json`:
     ```json
     {
       "exposition": "embedded",
       "cadence": "blocking"
     }
     ```
   - For questionnaires, instance-level manifests must match the class-level manifest; discrepancies are treated as errors.
   - Closure check: an artifact is closed if and only if `deleteSurface.json` exists in its instance directory (`/artifacts/<class>/<name>/deleteSurface.json`).

3. **OpenSandbox Read-Only Mount & Git Tracking**:
   - In `SeamusOpenSandboxBackend`, `<session_workspace>/artifacts` is mounted to `/artifacts` with `readOnly=True`. Sandboxed agents cannot modify artifacts via shell or raw filesystem tools, only via authorized agent tools.
   - In `GitWorkspaceManager`, `artifacts` is included alongside `data` and `agent/state` in `commit_checkpoint_changes()`, preserving complete version history on the session's Git branch.

4. **`ask` Tool & Questionnaire Layout**:
   - Agent tool `ask(question: str, answers: list[str], multiple: bool = False, writein: bool = False, id: str | None = None) -> str`.
   - `answers` is required with cardinality constraints: must contain at least 2 choices when `writein=False` and `multiple=False`, or at least 1 choice when `writein=True` or `multiple=True`.
   - Normalizes question identifiers to camelCase slugs (e.g. `"What color is the background?"` -> `backgroundColor`) and strips whitespace.
   - Rejects duplicate question IDs within the current questionnaire immediately at `ask` invocation time with a `ValueError`.
   - Gathers all questions called within a single inference turn into a single questionnaire.
   - On turn completion, generates `/artifacts/questionnaires/<uuid>/updateComponents.json` containing an A2UI v0.9 `Card` and `Column` layout. Layout is clean and streamlined: a direct sequence of question cards followed by a primary `Button` (`"submit_button"`), omitting redundant headers, subtitles, and intermediate dividers.
   - Inside each question card, `ChoicePicker` uses `variant="multipleSelection"` when `multiple=True` and `variant="mutuallyExclusive"` when `multiple=False`, without duplicating the question header in `label`.

5. **Blocking Cadence & Submission Flow**:
   - `cadence=blocking`: while an open blocking artifact exists, `POST /session/.../input` returns HTTP 409 Conflict, and the UI disables the composer textarea and send button.
   - When the user submits the form, the frontend dispatches `POST /agent/.../session/.../artifact/{kind}/{name}/submit` with the form's data model context.
   - The backend:
     1. Writes `/artifacts/questionnaires/<name>/updateDataModel.json` with the submitted data model.
     2. Writes `/artifacts/questionnaires/<name>/deleteSurface.json` with `{"version": "v0.9", "deleteSurface": {"surfaceId": "surface"}}` (closing it).
     3. Synthesizes a tool call `read_artifact_submission(artifact_id=name)` with result `{"data": data}`.
     4. Broadcasts AG-UI tool events (`TOOL_CALL_START`, `TOOL_CALL_ARGS`, `TOOL_CALL_END`, `TOOL_CALL_RESULT`), updates the thread checkpointer, and resumes agent inference.
   - `read_artifact_submission` is also registered as an agent tool to enable re-reading canonical data from disk, but fails with `ValueError` if invoked in the same turn that created the questionnaire.

6. **Bundled Platform Skills (`/skills/bundled`)**:
   - Bundled skills are maintained in repository source under `src/seamus/skills/bundled/`.
   - Mounted read-only into OpenSandbox at `/skills/bundled`.
   - In `SeamusOpenSandboxBackend.get_skill_sources()` and `inspector.extract_session_skills()`, `/skills/bundled` is placed at the highest precedence (loaded last in DeepAgents "last one wins" list, surfaced as `Bundled` in Inspector and system prompt).
   - Bundled skill `artifacts` provides comprehensive operational instructions on A2UI v0.9 and the artifact lifecycle.

7. **React A2UI Renderer & Changes Tab Integration**:
   - Front-end integrates `@a2ui/react` and `@a2ui/web_core` (v0.15.0) targeting A2UI v0.9 and the basic catalog. Supports both the official A2UI catalog URI (`https://a2ui.org/specification/v0_9/catalogs/basic/catalog.json`) and the short alias (`https://a2ui.org/specification/v0_9/basic_catalog.json`).
   - Embedded surfaces render inline within assistant messages; closed questionnaires show submitted answers in a read-only state.
   - In the **Changes tab**, artifacts are not shown as raw filesystem files. Instead, the full A2UI stream per artifact (`createSurface`, `updateComponents`, `updateDataModel`, `deleteSurface`) is synthesized as `artifacts/<kind>/<uuid>.jsonl`, pretty-printed with 2-space indentation, separated visually from `data/` deliverables, and equipped with a per-artifact segmented toggle between "Diff" view and read-only "Rendered" view.

## Consequences

### Positive
- Type-safe, declarative A2UI v0.9 rendering embedded in the chat interface.
- Complete auditability and Git persistence for UI surfaces and user submissions.
- Strict sandbox safety preventing sandboxed agents from modifying artifact definitions directly.
- First-class bundled platform skills model with clean precedence and container isolation.

### Negative / Trade-offs
- Adding `@a2ui/react` and `@a2ui/web_core` introduces new npm dependencies in the frontend bundle.
- Currently, only the `questionnaires` family is supported; custom artifact creation remains deferred.

