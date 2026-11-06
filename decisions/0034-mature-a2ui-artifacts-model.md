# 0034. Mature A2UI Subset Artifact Model, Opinionated Persistence, and Atomic Generation

Date: 2026-11-06

## Status

Accepted

## Context

In [0029-SUPERSEDED-a2ui-questionnaire-artifacts.md](./0029-SUPERSEDED-a2ui-questionnaire-artifacts.md), Seamus initially adopted A2UI v0.9 for interactive agent artifacts, utilizing full event streaming. Operational friction with complex event logs and catalog bindings led to [0031-SUPERSEDED-migrate-a2ui-to-adaptive-cards.md](./0031-SUPERSEDED-migrate-a2ui-to-adaptive-cards.md), which evaluated Microsoft Adaptive Cards.

However, subsequent experimentation revealed that while Adaptive Cards offered a monolithic card format, it was ill-suited for our desired Human-In-The-Loop (HITL) execution mechanics, dynamic multi-button interactions, atomic generation templates, and fine-grained state synchronization. Furthermore, the previous pattern of accumulating questions turn-by-turn via `ask` hindered prompt clarity, tool determinism, and clean artifact lifecycles.

We require a mature, robust, and opinionated model:
1. **A2UI Subset for UI Representation**: Use A2UI JSON purely as a declarative UI component representation (`components` sequence from A2UI `updateComponents`), completely rejecting A2UI's event-stream and data-model filesystem models.
2. **Custom, Opinionated State & Interaction Filesystem**: Direct filesystem persistence under `/artifacts/<family>/<uuid>/` capturing manifest, body, state (`dataModel` and `clicksLeft`), closure markers, and per-button evaluated interaction files.
3. **Atomic Generation Tools**: Replace accumulating inquiry tools with atomic builders (`make_artifact`, `make_questionnaire`, `make_form`).
4. **Explicit Agent Waiting and Unblocking Semantics**: Introduce `wait_for_click` for direct agent suspension, coupled with synthetic user unblocking messages if an agent responds during a blocking turn without calling `wait_for_click`.
5. **Inline Commenting Support**: First-class support for `commentable` artifacts where frontend text selections and user review notes are buffered client-side and dispatched via rewritten `Review` push actions.

## Decision

1. **Adopt A2UI Subset for Declarative UI Representation**:
   - Standardize on the declarative component hierarchy of A2UI v0.9 (`body.json` mirrors the `components` list of `updateComponents`).
   - Eliminate all filesystem-based A2UI event streams. The harness synthesizes an in-memory A2UI event stream dynamically and feeds it directly to the frontend renderer.
   - Reject multi-level component search in favor of a flat, predictable component sequence with explicit identifier bindings.

2. **Standardize Artifact Filesystem Layout**:
   - Mount `/artifacts` inside OpenSandbox containers as strictly read-only (`readOnly=True`).
   - Store all artifacts at `/artifacts/<family>/<uuid>/`:
     - `manifest.json`: Configuration defining exposition (`"tabbed"` | `"embedded"`), blocking cadence (`blocking: bool`), commentability (`commentable: bool`), and button interaction rules (`buttons: list[Button]`).
     - `body.json`: Canonical declarative UI component hierarchy. Must exist prior to or simultaneously with `manifest.json`.
     - `state.json`: Managed state tracking `dataModel` (accumulated context from button clicks) and `clicksLeft` (remaining click quotas per button).
     - `closed.marker`: Marker file indicating artifact closure. The presence of this file (empty or non-empty) signifies that the artifact is closed, auto-collapsing embedded artifacts and closing tabbed panels.
     - `interactions/<button_id>.json`: Evaluated event contexts written on button clicks according to the button's configured mode (`"set"` for formatted JSON overwrite, `"append"` for JSONL append).
   - Invariant: Artifact files are never deleted by the harness; updates replace file content (or append for JSONL interactions).

3. **Atomic Artifact Generation Tools**:
   - Replace accumulating inquiry tools (`ask`) with atomic generators.
   - Core tool: `make_artifact(family: str, components: list[dict], manifest: dict) -> str` (returning artifact UUID).
   - Specialized templated tools:
     - `make_questionnaire(questions: list[Question]) -> str` with `Question(body: str, answers: list[str], multiple_choice: bool = False)`.
     - `make_form(...)`.

4. **Agent Waiting and Blocking Interaction Lifecycle**:
   - Provide the agent tool `wait_for_click(artifact_id: str, button_id: str | "*", fresh: bool = True)`.
     - `fresh=True`: Waits until a click occurs strictly after the tool invocation.
     - `fresh=False`: Immediately returns existing click context if already clicked; otherwise awaits a click.
     - Returns evaluated click context, button ID, and modification timestamp.
   - For `blocking: true` artifacts:
     - The chat input area is disabled in the Web UI until an unblocking button is clicked.
     - If the agent calls `wait_for_click`, execution halts until the user clicks an active button.
     - If the agent terminates its turn with a message without invoking `wait_for_click`, the harness remains blocking until the user clicks an unblocking button, at which point the harness injects a synthetic message (`<SYNTHETIC MESSAGE INDICATOR>`) notifying the agent of the unblocking event.

5. **Commentability & Review Action Rewriting**:
   - When `commentable: true` in `manifest.json`, the Web UI enables text-span selection and inline review commenting.
   - Inline comments accumulate client-side until a `Review` component with `action: {"comments": "push"}` is clicked.
   - The harness rewrites `{"comments": "push"}` into a standard A2UI `push_comments` event containing structured comment spans (start/end line and character offsets before and after Markdown rendering, markdown text, and comment text), and clears the frontend buffer upon dispatch.

6. **Agent Skills & Documentation**:
   - Maintain the `artifacts` bundled skill instructing agents on atomic artifact construction, read-only filesystem semantics, and favoring specialized templates over raw custom artifacts.
   - Introduce the `a2ui-components` skill with the basic catalog specification (`catalog.json`) to guide custom component authoring.

## Consequences

- Completely decouples declarative UI representation (A2UI JSON subset) from state persistence and interaction mechanics.
- Eliminates fragile accumulating survey state; questionnaires and forms are created deterministically and atomically.
- Provides explicit, robust Human-In-The-Loop semantics via `wait_for_click` and synthetic unblocking turn injection.
- Unlocks rich text commenting and review workflows for plans and documents without polluting the underlying document source.
- Establishes a durable, easily inspectable filesystem structure for artifacts under `/artifacts/<family>/<uuid>/`.

## Cross-References

- [artifacts.md](../knowledge/artifacts.md)
- [0029-SUPERSEDED-a2ui-questionnaire-artifacts.md](./0029-SUPERSEDED-a2ui-questionnaire-artifacts.md)
- [0031-SUPERSEDED-migrate-a2ui-to-adaptive-cards.md](./0031-SUPERSEDED-migrate-a2ui-to-adaptive-cards.md)
- [backlog.md](../knowledge/backlog.md)

