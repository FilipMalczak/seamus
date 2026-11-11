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
│       ├── schema.json                # Schema mapping questions/choice IDs to text/labels
│       ├── state.json                 # latest last_event snapshot and clicksLeft counters
│       ├── answers.md                 # Human-readable summary of user answers & selections
│       ├── closed.marker              # Present if and only if artifact is closed
│       └── interactions/
│           └── <button_id>.jsonl      # Append-only chronological stream of click events
├── forms/
│   └── <uuid>/
│       ├── manifest.json
│       ├── body.json
│       ├── schema.json
│       ├── state.json
│       ├── answers.md
│       ├── closed.marker
│       └── interactions/
│           └── <button_id>.jsonl
└── plans/
    └── <uuid>/
        ├── manifest.json
        ├── body.json
        ├── state.json
        ├── plan.md                    # Canonical Markdown plan body
        ├── closed.marker
        └── interactions/
            └── <button_id>.jsonl
```

- **`manifest.json` & `body.json`**: Written atomically upon creation. If `manifest.json` exists without `body.json`, the artifact is corrupted (INV-ART-003).
- **`state.json`**: Contains `{ "last_event": { ... }, "clicksLeft": { ... } }`.
- **`answers.md`**: Automatically generated and kept updated for questionnaires and forms upon submission. Provides a clean, human-readable Markdown summary of user responses.
- **`closed.marker`**: Empty file touched when an artifact closes. When closed, tabbed artifacts unmount and embedded artifacts auto-collapse into read-only mode.
- **`/interactions/<button_id>.jsonl`**: Append-only log recording every click event in order.

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
      "id": "submit_btn",
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
  - `id`: Button component ID in `body.json`. MUST be a valid UAX #31 identifier (letters, digits, underscores; no hyphens!). Any button clicked in UI that is not listed in `buttons` will log a warning and be ignored.
  - `clicks`: Positive integer (e.g. `1` or `3`) or `"*"` (unlimited). When clicks reaches `0`, the button is rendered visibly disabled in the UI.
  - `unblocking`: Whether clicking this button unblocks the session.
  - `closing`: Whether clicking this button writes `closed.marker` to close the artifact. Closing implies unblocking.

## Button Events, Snapshots, and Context

Whenever a user clicks a button:
1. **Input Data Snapshot**: The client automatically gathers a complete snapshot of all input widgets across the surface (`TextField`, `CheckBox`, `ChoicePicker`/`ChoiceSet`, `Slider`, `DateTimeInput`) and sends them as key-value pairs in `event.data`.
2. **No Dynamic Path Pointers Needed**: Buttons do **NOT** need dynamic context pointers (e.g. `{ "path": "/components/..." }` is disallowed and dropped). All widgets are automatically captured by their component IDs.
3. **Static Context**: Buttons may define static flags or values (e.g. `{"approved": true}`, `{"action": "deploy"}`) in `button.action.event.context`.
4. **Append-Only History**: The event `{ "event": "<name>", "timestamp": "<ISO-8601>", "context": { ... }, "data": { ... }, "comments": [ ... ] }` is appended to `/interactions/<button_id>.jsonl` and persisted in `state.json` (`last_event`).
5. **Answers Summary (`answers.md`)**: For questionnaires and forms, responses are translated using `schema.json` into `/artifacts/<family>/<uuid>/answers.md`. Inspect `answers.md` directly to review user responses.

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
            write_in=True,
        )
    ],
    blocking=True,
    exposition="embedded",
)
```
> [!NOTE]
> When `write_in=True` is enabled, the UI automatically provides an unselected freeform write-in text field. Do **NOT** provide explicit `"Other"` or `"Custom"` choice items in `answers`.

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
> 1. **Mandatory Root**: Exactly one component in `components` should have `"id": "root"` (e.g. a `Column` or `Row`) containing all other widgets as descendants. If `"id": "root"` is omitted or multiple disconnected roots are found, Seamus auto-synthesizes a root `Column` and returns a notice so you can refine the layout.
> 2. **Loose Normalization & Mutation Log**: To eliminate unnecessary conversational roundtrips, Seamus automatically normalizes common minor syntax variations:
>    - Missing component `id` values are automatically assigned deterministic unique IDs (e.g. `text_0`, `button_1`).
>    - Common type aliases (`"type"`, `"component_type"`, `"componentType"`, `"widget"`) and lowercase names (`"text"`, `"button"`, `"heading"`) are automatically converted to standard `"component"` types.
>    - `Button` elements with inline `label` or `text` automatically receive synthesized child `Text` components.
>    - `Card` elements with inline `title`, `body`, or `children` are automatically adapted into standard child container subtrees.
>    - Buttons omitted from `manifest.buttons` are automatically declared.
>    When any automatic normalization occurs, `make_artifact` returns a `Notice: Automatically normalized component tree:` log alongside the created artifact UUID so you can see exactly how the request was adapted.
> 3. **Render Validation**: If fatal validation fails (e.g. unknown component types, dangling child IDs, or cycles), **the artifact is not stored** and the tool returns the list of errors with a notification stating that the artifact was not stored. When this occurs, inspect the errors, fix the component tree, and call `make_artifact` again.

### 4. `make_plan`, `update_plan`, `edit_plan` (Plan Mode)
- `make_plan(title="Plan", content="# Implementation Plan...")`: Creates the session plan tab with a whitelisted **Proceed** button (`id="proceed_btn"`, `clicks="*"`, `unblocking=true`, `closing=true`) and inline review commenting enabled.
- Once created, `update_plan(content)` and `edit_plan(old_string, new_string)` are used for refinements.

## Resumption & Human-In-The-Loop Execution

### In-Turn Suspension: `wait_for_click`
To suspend execution within the current turn until the user interacts with the artifact:
```python
result_json = wait_for_click(artifact_id=uuid, button_id="submit_btn", fresh=True)
```
- Suspends execution and writes `pending_wait.json` to `<session_dir>/agent/state/threads/{thread_id}/pending_wait.json`.
- When the user clicks the button, execution resumes seamlessly within the same turn (even across server restarts!).
- Returns a JSON string of `ClickResult`: `{ "artifact_id": str, "button_id": str, "event": str, "data": dict, "context": dict, "timestamp": str }`.

### Synthetic Unblocking Notification
If the agent concludes its turn with an assistant message (e.g. without calling `wait_for_click`), when the user subsequently clicks an unblocking or closing button, Seamus injects a synthetic user turn beginning with:
`<SYNTHETIC MESSAGE INDICATOR>`
Treat this notification as direct user event data. The user chat input prevents users from typing this prefix directly.
