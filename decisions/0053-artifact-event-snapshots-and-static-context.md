# 0053 Artifact Event Snapshots and Static Context

- **Status**: Accepted
- **Date**: 2026-11-11
- **Authors**: Filip, DeepMind Pair Assistant
- **Deciders**: Filip, Seamus Harness Core Team
- **Consulted**: Seamus Harness Core Team
- **Informed**: Seamus Developer Community

## Context and Problem Statement

Seamus interactive artifacts previously relied on a dynamic context pointer pattern (`{"path": "/components/<id>/value"}`) declared on button actions in `body.json`. In this model:
1. When an agent authored an artifact, it had to manually declare JSON pointers for each input widget whose value it wanted returned on button click.
2. The web frontend evaluated these path pointers at click time against the local component tree.
3. The harness accumulated the evaluated context into `state.json.dataModel` across turns and wrote interactions using a button-configured `mode` (`set` overwriting the interaction file, or `append` appending to it).
4. For questionnaires and forms, agents were given a transitional `read_artifact_submission` tool to re-read submitted answers from disk.

In practice, this architecture introduced unnecessary complexity and failure modes:
- Agents frequently misconfigured path expressions in button actions or omitted required field pointers.
- Accumulating fields turn-by-turn into `dataModel` obscured the exact temporal event that occurred and made it difficult to inspect raw submission snapshots.
- Per-button `mode` (`set` vs `append`) was an unnecessary abstraction, as interaction history is inherently an append-only timeline.
- The `read_artifact_submission` tool was an outdated leftover that cluttered the agent's tool surface and conflicted with the standard `wait_for_click` and synthetic message lifecycle.

## Decision Drivers

- **Simplicity for Agents & Builders**: Agents should not need to write dynamic path pointers or configure persistence modes when defining buttons.
- **Complete Input Snapshots**: Every button click should capture the full state of all input widgets on the surface, ensuring no user input is lost.
- **Append-Only History**: All interaction events must be preserved in chronological order without truncation or overwrites.
- **Human-Readable Answers**: Questionnaires and forms should produce a clean, human-readable Markdown summary (`answers.md`) alongside raw JSON/JSONL artifacts.
- **Tool Surface Hygiene**: Deprecate and remove redundant legacy tools (`read_artifact_submission`).

## Decision Outcome

We adopt an event-driven snapshot model for all artifacts:

1. **Disallow Dynamic Context & Allow Static Context**:
   - Buttons are not required to define `context`.
   - Dynamic context pointers (`{"path": ...}`) are disallowed in button actions. During artifact creation and component normalization, any `{path: ...}` entries in button context are automatically dropped, and an explanatory mutation log notice is emitted to the agent.
   - Non-dynamic static context (e.g. `{"approved": true}`, `{"action": "confirm"}`) is supported and preserved.

2. **Remove Button Persistence Modes**:
   - Remove `mode` (`"set"` / `"append"`) from `ManifestButton`. All button interactions are recorded into append-only JSONL files.

3. **Event Payload Specification**:
   - When any button is clicked, the frontend dispatches a structured event payload:
     - `event`: Name from `button.action.event.name`, falling back to `button.id` if omitted.
     - `timestamp`: Current time in ISO 8601 with timezone (e.g. `2026-11-11T10:44:09+01:00`).
     - `context`: Static context defined on the button (optional).
     - `data`: Snapshot of all interactive inputs on the surface (`TextField`, `CheckBox`, `ChoicePicker`, `Slider`, `DateTimeInput`) mapped by component ID to current value (unchecked checkboxes explicitly `false`, multi-select choice pickers as arrays of choice keys).
     - `comments`: Accumulated review comments if the button defines `action: { comments: "push" }` (optional).

4. **Persistence Structure**:
   - `<artifact_dir>/interactions/<button_id>.jsonl`: Append-only JSONL file recording each event in exact order.
   - `<artifact_dir>/state.json`: Replaces `dataModel` with `last_event` storing the latest event snapshot, pretty-printed (`indent=2`).

5. **`answers.md` for Questionnaires and Forms**:
   - For question-centric artifacts (`family` in `{"questionnaires", "forms"}`), the harness automatically generates/updates `<artifact_dir>/answers.md` upon button click, translating widget IDs and option values into human-readable question prompts and answers using `schema.json`.

6. **Deprecate `read_artifact_submission`**:
   - Remove the `read_artifact_submission` tool from the runner, tool registries, dynamic mode tool sets, and bundled skills.

## Consequences

### Positive
- Artifact creation by agents is significantly simplified: buttons need only declare their label, variant, and optional static flags.
- Complete, non-destructive audit trail of all button clicks in `.jsonl` files.
- `answers.md` provides an immediate, readable Markdown document that agents or users can inspect without parsing raw A2UI component IDs.
- Cleaner agent tool surface without confusing legacy submission readers.

### Negative / Neutral
- Existing test cases and fixtures asserting `dataModel` or `mode: "set"` must be updated to the new event and JSONL schema.

