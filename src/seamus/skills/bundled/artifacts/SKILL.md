---
name: artifacts
description: Comprehensive operational guide for A2UI v0.9 renderable artifacts, questionnaires, and synthetic submission tool calls in Seamus.
---

# Seamus Renderable Artifacts & A2UI v0.9 Guide

Seamus provides renderable artifacts allowing agents to present rich, interactive user interfaces directly in the chat or in specialized panels. All artifacts are formatted using the **A2UI v0.9** protocol and persisted on disk under `/artifacts/`.

## A2UI v0.9 Protocol Foundations

A2UI represents user interfaces as an event stream:
- `createSurface`: Declares a surface with `surfaceId: "surface"`, basic catalog URL, and data model dispatch configuration.
- `updateComponents`: Composes the UI hierarchy from widgets (additive across events).
- `updateDataModel`: Fills or updates data values bound to component paths (additive and overwriting by path).
- `deleteSurface`: Declares that a surface is deleted/closed.

## Filesystem Structure & Hierarchical Resolution

Inside your sandbox, `/artifacts/` is mounted **read-only**. You can read existing artifacts to inspect prior structures or user responses, but you create and modify artifacts exclusively through specialized tools (e.g. `ask`).

Artifact files are organized by family and instance:
```
/artifacts/
├── createSurface.json              # Shared root default surface configuration
└── questionnaires/
    ├── manifest.json               # Family manifest (exposition=embedded, cadence=blocking)
    └── <artifact_uuid>/
        ├── updateComponents.json   # Generated A2UI component tree
        ├── updateDataModel.json    # Canonical user-submitted data model
        └── deleteSurface.json      # Present if and only if artifact is closed
```

### Hierarchical Resolution
When loading artifact files, the system checks:
1. `/artifacts/<family>/<name>/<file>`
2. `/artifacts/<family>/<file>`
3. `/artifacts/<file>`

*Exception*: `deleteSurface.json` is checked strictly at the instance level (`/artifacts/<family>/<name>/deleteSurface.json`). An artifact is open until this file exists, and closed once it is created.

## Specialized Questionnaire Artifacts

To ask clarifying questions, collect user preferences, or resolve design choices, use the `ask` tool.

### The `ask` Tool
Signature:
```python
ask(question: str, answers: list[str], writein: bool = False, id: str | None = None) -> str
```
- `question`: The closed question prompt (e.g., `"What color is the background?"`).
- `answers`: The available choices (e.g., `["white", "blue"]`).
- `writein`: Set to `True` to provide an "Other" option with an accompanying text field for user-specified input.
- `id`: Optional identifier slug (e.g., `"backgroundColor"`). If omitted, an identifier is automatically derived from the question.

### Batching Behavior
When you call `ask` one or more times in a single turn, Seamus batches all calls from that inference into a single questionnaire artifact under `/artifacts/questionnaires/<UUID>/`.

The tool returns `"OK"` in your tool history so you can proceed.

### Conversation Cadence (`blocking`)
Questionnaires default to `cadence=blocking`. While an open questionnaire exists:
- The user cannot send normal chat messages.
- The UI send button is disabled.
- The user is prompted to complete and submit the questionnaire.

## Receiving User Submissions

When the user fills out and submits the questionnaire:
1. The system canonically saves the filled values to `/artifacts/questionnaires/<UUID>/updateDataModel.json`.
2. The system writes `/artifacts/questionnaires/<UUID>/deleteSurface.json`, marking the questionnaire closed.
3. The system generates a **synthetic tool call**:
   ```json
   read_artifact_submission(artifact_id="<UUID>")
   ```
   returning:
   ```json
   {
     "data": {
       "backgroundColor": "other",
       "backgroundOther": "fuchsia",
       "headerStyle": "bold"
     }
   }
   ```
4. Your inference resumes immediately with the submitted answers so you can continue executing the task.

You can also invoke `read_artifact_submission(artifact_id="<UUID>")` directly at any time if you need to re-read canonical submission data from disk.

