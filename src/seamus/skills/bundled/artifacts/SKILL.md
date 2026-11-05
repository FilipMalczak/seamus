---
name: artifacts
description: Comprehensive operational guide for Microsoft Adaptive Cards renderable artifacts, questionnaires, forms, plans, and synthetic submission tool calls in Seamus.
---

# Seamus Renderable Artifacts & Adaptive Cards Guide

Seamus provides renderable artifacts allowing agents to present rich, interactive user interfaces directly in the chat or in dedicated workspace tabs. All artifacts are formatted using the **Microsoft Adaptive Cards (v1.5)** specification and persisted on disk under `/artifacts/`.

## Adaptive Cards Protocol Foundations

Adaptive Cards represent user interfaces declaratively as structured JSON cards:
- **Card Root**: Includes `$schema: "http://adaptivecards.io/schemas/adaptive-card.json"`, `type: "AdaptiveCard"`, and `version: "1.5"`.
- **Containers**: Structural elements (`Container`, `ColumnSet`, `Column`) that group and lay out content.
- **Visual Elements**: Rich text blocks (`TextBlock`) supporting Markdown formatting, lists, code spans, headings, and tables.
- **Input Elements**: Interactive fields such as `Input.ChoiceSet` (for single-choice radio buttons or multi-choice checkboxes) and `Input.Text` (for single-line or multi-line text input).
- **Actions**: Interactive actions such as `Action.Submit` configured with descriptive action payloads (`submit_questionnaire`, `proceed_plan`).

## Filesystem Structure & Hierarchical Resolution

Inside your sandbox, `/artifacts/` is mounted **read-only**. You can read existing artifacts to inspect prior structures, plans, or user responses, while creating and modifying artifacts through dedicated harness tools (`ask`, `form`, `make_plan`, `update_plan`, `edit_plan`, `discard`).

Artifact files are organized by family and instance:
```
/artifacts/
├── questionnaires/
│   ├── manifest.json              # Family manifest (exposition=embedded, cadence=blocking)
│   └── <artifact_uuid>/
│       ├── card.json              # Canonical Adaptive Card schema
│       ├── submission.json        # User-submitted response values
│       └── closed.json            # Present if and only if artifact is closed
├── forms/
│   ├── manifest.json              # Family manifest (exposition=tabbed, cadence=nonblocking)
│   └── <artifact_uuid>/
│       ├── manifest.json          # Instance manifest (custom tab title)
│       ├── card.json              # Canonical Adaptive Card schema
│       ├── submission.json        # User-submitted response values
│       └── closed.json            # Present if and only if artifact is closed
└── plans/
    ├── manifest.json              # Family manifest (exposition=tabbed, cadence=nonblocking)
    └── <plan_uuid>/
        ├── manifest.json          # Instance manifest (plan tab title)
        ├── card.json              # Structured document card with Proceed action
        ├── plan.md                # Canonical Markdown plan content
        └── closed.json            # Present when plan is closed, approved, or discarded
```

### Hierarchical Resolution
When loading artifact files, the system checks:
1. `/artifacts/<family>/<name>/<file>`
2. `/artifacts/<family>/<file>`
3. `/artifacts/<file>`

*Exception*: `closed.json` (and `submission.json`) is checked strictly at the instance level (`/artifacts/<family>/<name>/closed.json`). An artifact is open until this file exists, and closed once it is created.

## Specialized Questionnaire & Form Artifacts

### The `ask` Tool (Embedded + Blocking)
Available in `Chat` mode and `Plan/Discuss` phase:
```python
ask(
    question: str,
    answers: list[str],
    multiple: bool = False,
    writein: bool = False,
    id: str | None = None,
) -> str
```
- Creates an inline `questionnaires` artifact (`exposition=embedded`, `cadence=blocking`).
- Multiple calls in the same turn are batched into a single questionnaire card.
- While open, the chat composer is disabled until the user submits the questionnaire.

### The `form` Tool (Tabbed + Non-Blocking)
Available in `Plan/Discuss` phase:
```python
form(
    question: str,
    answers: list[str],
    multiple: bool = False,
    writein: bool = False,
    id: str | None = None,
    title: str = "Form",
) -> str
```
- Creates a `forms` artifact (`exposition=tabbed`, `cadence=nonblocking`) rendered in its own tab to the right of `Changes`.
- Multiple calls in the same turn are batched into a single form tab.
- Because `cadence=nonblocking`, the user can continue freestyle conversation in the chat before or instead of submitting the form.

### Communication Rule: Do NOT Duplicate Questions in Text
When invoking `ask` or `form`, the interactive UI presents all questions, options, and write-in inputs directly to the user.
- **NEVER** re-state, list, or duplicate the questions or choices in your assistant message text.
- Emit at most a single brief introductory sentence or emit no text at all.

## Plan Artifacts (`plans`)

In `Plan` mode (`Make` phase):
- `make_plan(content: str, name: str = "Plan") -> str`: Creates the session-local plan artifact under `/artifacts/plans/<plan_id>/` (`exposition=tabbed`, `cadence=nonblocking`), opening a tab named `name` to the right of `Changes` with rendered Markdown and a **Proceed** button.
- Once `make_plan` has been called, `make_plan` disappears and is replaced by:
  - `update_plan(content: str) -> str`: Overwrites the full Markdown content of the active session plan.
  - `edit_plan(old_string: str, new_string: str) -> str`: Performs an exact substring replacement on the active session plan.
- Clicking **Proceed** on the Plan tab approves the plan and transitions the session into a new `Plan/Execute` thread.
- Accepting the Sync PR in `Plan/Execute` (or calling `discard()` on explicit user command) writes `closed.json` to close the plan artifact and removes its tab.

## Receiving User Submissions & `read_artifact_submission`

When the user submits a `questionnaires` or `forms` artifact, the system saves `submission.json`, writes `closed.json`, and synthesizes `read_artifact_submission(artifact_id="<UUID>")` to resume inference.

### Calling Constraints for `read_artifact_submission`
- **Same-turn prohibition**: You MUST NOT call `read_artifact_submission` in the same turn that you invoke `ask`, `form`, or `make_plan`.
- **Non-blocking to blocking promotion**: When `read_artifact_submission` is explicitly called on an open non-blocking artifact (`cadence=nonblocking`), that artifact instance's manifest is promoted to `cadence=blocking` until the user submits it.
