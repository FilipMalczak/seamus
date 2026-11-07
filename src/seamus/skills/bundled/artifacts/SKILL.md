---
name: artifacts
description: Comprehensive operational guide for A2UI renderable artifacts, questionnaires, forms, plans, button whitelist manifests, wait_for_click, and synthetic interaction notifications in Seamus.
---

# Seamus Renderable Artifacts Guide

Seamus provides renderable artifacts allowing agents to present rich, interactive user interfaces directly in the chat or in dedicated workspace tabs. Artifacts are authored using an **A2UI basic catalog subset** representation and persisted on disk under `/artifacts/<family>/<uuid>/`.

## Filesystem Structure & Direct Resolution

Artifact instances live in isolated directories with no hierarchical search:

```
/artifacts/
├── questionnaires/
│   └── <uuid>/
│       ├── manifest.json              # Behavioral manifest & button whitelist
│       ├── body.json                  # Sequence of A2UI basic catalog components
│       ├── state.json                 # Accumulated dataModel and clicksLeft counters
│       ├── closed.marker              # Present if and only if artifact is closed
│       └── interactions/
│           └── <button_id>.json       # Payloads written upon button clicks
├── forms/
│   └── <uuid>/
│       ├── manifest.json
│       ├── body.json
│       ├── state.json
│       ├── closed.marker
│       └── interactions/
│           └── <button_id>.json
└── plans/
    └── <uuid>/
        ├── manifest.json
        ├── body.json
        ├── state.json
        ├── plan.md                    # Canonical Markdown plan body
        ├── closed.marker
        └── interactions/
            └── <button_id>.json
```

- **`manifest.json` & `body.json`**: Written atomically upon creation. If `manifest.json` exists without `body.json`, the artifact is corrupted (INV-ART-003).
- **`state.json`**: Initialized with `{ "dataModel": {}, "clicksLeft": { ... } }`.
- **`closed.marker`**: Empty file touched when an artifact closes. When closed, tabbed artifacts unmount and embedded artifacts auto-collapse into read-only mode.
- **`/interactions/<button_id>.json`**: Created when the user clicks an active button.

## Manifest Schema & Button Whitelist

The manifest controls exposure, blocking behavior, inline commenting, and whitelisted buttons:

```json
{
  "name": "Database Configuration",
  "exposition": "embedded",
  "blocking": true,
  "commentable": false,
  "buttons": [
    {
      "id": "submit-btn",
      "mode": "set",
      "clicks": 1,
      "unblocking": true,
      "closing": true
    }
  ]
}
```

- **`exposition`**: `"embedded"` (rendered directly inline in chat) or `"tabbed"` (opened in a dedicated tab).
- **`blocking`**: If `true`, the user cannot send chat messages until an unblocking button is clicked.
- **`commentable`**: If `true`, enables inline text selection and review comments.
- **`buttons`**: List of whitelisted buttons:
  - `id`: Button component ID in `body.json`. Any button clicked in UI that is not listed in `buttons` will log a warning and be ignored.
  - `mode`: `"set"` (overwrites `/interactions/<id>.json` with pretty JSON) or `"append"` (appends JSON lines).
  - `clicks`: Positive integer (e.g. `1` or `3`) or `"*"` (unlimited). When clicks reaches `0`, the button is rendered visibly disabled in the UI.
  - `unblocking`: Whether clicking this button unblocks the session.
  - `closing`: Whether clicking this button writes `closed.marker` to close the artifact. Closing implies unblocking.

## Atomic Artifact Tools

### 1. `make_questionnaire` (Embedded + Blocking)
Creates a closed-choice questionnaire:
```python
make_questionnaire(
    title="Deployment Target",
    questions=[
        Question(
            body="Which environment should we target?",
            answers=["staging", "production"],
            multiple_choice=False,
        )
    ],
    blocking=True,
    exposition="embedded",
)
```

### 2. `make_form` (Tabbed + Non-Blocking)
Creates a structured form in a dedicated tab to the right of Changes:
```python
make_form(
    title="Feature Flags Form",
    fields=[...],
    blocking=False,
    exposition="tabbed",
)
```

### 3. `make_artifact` (Core Atomic Builder)
Creates custom artifacts with custom manifests and arbitrary A2UI basic catalog components:
```python
make_artifact(
    family="custom",
    manifest=ArtifactManifest(...),
    components=[...],
)
```
> [!IMPORTANT]
> `make_artifact` validates the component tree and manifest to ensure the A2UI surface can be rendered without errors:
> 1. **Mandatory Root**: Exactly one component in `components` should have `"id": "root"` (e.g. a `Column` or `Row`) containing all other widgets as descendants. If `"id": "root"` is omitted or multiple disconnected roots are found, Seamus auto-synthesizes a root `Column` and returns a warning so you can refine the layout.
> 2. **Render Validation**: If validation fails (e.g. unknown component types, dangling child IDs, cycles, missing required properties, or buttons in `components` not declared in `manifest.buttons`), **the artifact is not stored** and the tool returns the list of errors with a notification stating that the artifact was not stored. When this occurs, inspect the errors, fix the component tree, and call `make_artifact` again.

### 4. `make_plan`, `update_plan`, `edit_plan` (Plan Mode)
- `make_plan(title="Plan", content="# Implementation Plan...")`: Creates the session plan tab with a whitelisted **Proceed** button (`id="proceed-btn"`, `clicks="*"`, `unblocking=true`, `closing=true`) and inline review commenting enabled.
- Once created, `update_plan(content)` and `edit_plan(old_string, new_string)` are used for refinements.

## Resumption & Human-In-The-Loop Execution

### In-Turn Suspension: `wait_for_click`
To suspend execution within the current turn until the user interacts with the artifact:
```python
result_json = wait_for_click(artifact_id=uuid, button_id="submit-btn", fresh=True)
```
- Suspends execution and writes `pending_wait.json` to `<session_dir>/agent/state/threads/{thread_id}/pending_wait.json`.
- When the user clicks the button, execution resumes seamlessly within the same turn (even across server restarts!).
- Returns a JSON string of `ClickResult`: `{ "artifact_id": str, "button_id": str, "context": dict, "timestamp": float }`.

### Synthetic Unblocking Notification
If the agent concludes its turn with an assistant message (e.g. without calling `wait_for_click`), when the user subsequently clicks an unblocking or closing button, Seamus injects a synthetic user turn beginning with:
`<SYNTHETIC MESSAGE INDICATOR>`
Treat this notification as direct user event data. The user chat input prevents users from typing this prefix directly.
