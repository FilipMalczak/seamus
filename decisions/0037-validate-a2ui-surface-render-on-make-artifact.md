# 0037. Validate A2UI Surface Render on `make_artifact`

Date: 2026-11-07

## Status

Accepted

## Context

In [0034-mature-a2ui-artifacts-model.md](./0034-mature-a2ui-artifacts-model.md), Seamus established the opinionated A2UI subset artifact model, where agents create declarative UI artifacts under `/artifacts/<family>/<uuid>/` via atomic builder tools like `make_artifact`.

Previously, `make_artifact` immediately persisted the artifact files (`body.json`, `manifest.json`, `state.json`) and broadcast the `ARTIFACT_CREATED` event without verifying whether the proposed components formed a valid, renderable A2UI surface. If an agent produced an invalid component tree (such as unrecognized component types, dangling child component IDs, cycles, duplicate IDs, missing required properties like `text` on `Text`, buttons in `components` not declared in `manifest.buttons`, or malformed action context pointers), the artifact was persisted to the session workspace and announced to the frontend, resulting in client-side `MessageProcessor` render errors or silent interaction failures.

We need `make_artifact` to proactively attempt rendering and validating the A2UI surface before storing anything. If rendering fails, the artifact must not be persisted, and the tool must report the validation errors and explicitly state that the artifact was not stored so the agent can correct its component tree.

## Decision

1. **Pre-Storage Surface Render Validation**:
   - Introduce `validate_a2ui_surface(components, manifest, initial_data)` in `seamus.harness.artifacts`.
   - Before writing any files to disk or broadcasting events, `SessionAgentRunner.handle_make_artifact` validates the manifest and attempts to render/validate the A2UI surface.

2. **Validation Rules**:
   - **Structure & Uniqueness**: `components` must be a non-empty list of dictionaries. Each component must define a unique, non-empty string `id`.
   - **Supported Catalogs**: Every component type must be a recognized basic catalog component (`Text`, `Image`, `Icon`, `Video`, `AudioPlayer`, `Row`, `Column`, `List`, `Card`, `Tabs`, `Modal`, `Divider`, `Button`, `TextField`, `CheckBox`, `ChoicePicker`, `Slider`, `DateTimeInput`) or an established normalizable alias (`ChoiceSet`, `TextInput`, `Container`).
   - **Child Reference Integrity**: Every referenced child ID in `children`, `child`, `tabs`, or `modal` properties must resolve to an existing component in `components`. Dangling child references are strictly rejected.
   - **Topology & Cycles**: The component hierarchy must be acyclic (no self-references or multi-node cycles), components must have at most one parent, and at least one root component must exist.
   - **Required Component Properties**:
     - `Text`: Requires `text` content; `variant` must be one of `h1`, `h2`, `h3`, `h4`, `h5`, `caption`, `body`, `bold`.
     - `Image`: Requires `url`; `fit` and `variant` must conform to allowed enums.
     - `Icon`: Requires `name`.
     - `ChoicePicker` / `ChoiceSet`: Requires options/choices or a data model binding.
     - `Button`: Every button component in `components` must be declared in `manifest.buttons` so user clicks can be dispatched and processed.
   - **Data Model & Context Pointers**: JSON pointers must conform to RFC 6901 syntax; pointers targeting `/components/<id>/...` must resolve to an existing component ID.
   - **Manifest Validity**: The manifest must be a valid `ArtifactManifest` instance or dictionary.

3. **Rejection Semantics & Tool Response**:
   - If manifest validation or surface rendering fails:
     - No files or directories are created under `/artifacts/<family>/<uuid>/`.
     - No `ARTIFACT_CREATED` event is broadcast or appended to the thread.
     - The tool returns a human-readable error response listing all detected errors and explicitly stating the "did not store" fact:
       ```text
       Failed to render A2UI surface. Artifact was not stored.
       Validation errors:
       - <error 1>
       - <error 2>
       ```
   - If validation succeeds:
     - Files are persisted (`body.json`, `manifest.json`, `state.json`), `ARTIFACT_CREATED` is emitted, and the artifact UUID is returned as normal.

4. **Tool Schema Flexibility**:
   - Relax `MakeArtifactInput` field types to accept dictionaries for `manifest` and arbitrary sequences for `components`, ensuring malformed inputs reach `handle_make_artifact` for unified error reporting rather than triggering premature Pydantic schema validation exceptions in the tool framework.

## Consequences

- Agents receive immediate, actionable diagnostics when authoring custom A2UI artifacts, allowing them to self-correct during the same turn.
- Malformed or broken artifacts are prevented from ever reaching the workspace filesystem, Git history, or client UI.
- Preserves the integrity of the session workspace and ensures `ARTIFACT_CREATED` events only announce renderable artifacts.

