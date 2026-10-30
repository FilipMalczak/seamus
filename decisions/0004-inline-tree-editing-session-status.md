# 0004. Inline Tree Node Renaming and Session Node Status Indicator

Date: 2026-10-30
Status: Accepted

## Context

Previous iterations used browser modal `window.prompt()` dialogs to collect edited names for Agents, Sessions, and Threads in the navigation tree. In addition, Session nodes in the sidebar tree lacked an immediate visual status indicator showing the operational state of the session's active open thread.

To eliminate modal dialog interruptions and improve real-time situational awareness across the tree hierarchy, we require:
- Complete removal of `window.prompt()`.
- Seamless in-place editing: clicking the edit icon converts the node label into an auto-focused text field, while the edit button transforms into a tick-box accept button (`<Check />` icon).
- Live session status visualization: display a compact status icon on the Session node indicating whether the session is awaiting user input, thinking, executing a tool, or in an error state.

## Decision

1. **Inline Text Editing**:
   - Replace all `window.prompt()` invocations with local editing state (`editingKey`, `editingValue`).
   - When editing a node (Agent, Session, or Thread), the label element is replaced by an `<input className="inline-edit-input">`.
   - The edit action button transforms from a `<Pencil />` icon into a tick-box-only-no-text `<Check />` accept button.
   - Pressing `Enter` or clicking the accept button submits the trimmed name (or `null` if empty, falling back to full UUID per [INV-010](../knowledge/invariants.md#inv-010-entity-display-name-fallback)).
   - Pressing `Escape` cancels editing without saving changes.
   - Click events on the input and accept button stop event propagation, avoiding unintended node collapse or thread selection.

2. **Session Node Status Indicator**:
   - Derive the session's operational status from its active open thread (`session.threads.find(t => t.is_open)?.status || "AWAITING_USER"`).
   - Render a small (`size-3` / 12px) status icon next to the session icon:
     - `AWAITING_USER`: `<CheckCircle2 className="size-3 text-emerald-400" />`
     - `AWAITING_LLM`: `<Loader2 className="size-3 text-sky-400 animate-spin" />`
     - `EXECUTING_TOOL`: `<Wrench className="size-3 text-amber-400 animate-pulse" />`
     - `ERROR`: `<AlertCircle className="size-3 text-rose-400" />`
   - Provide tooltip information summarizing the current session status.

## Consequences

- Zero disruptive browser popups remain in the application.
- Renaming is natural, inline, and keyboard accessible.
- Users can observe background execution status across sessions directly in the navigation sidebar without opening individual threads.

## Cross-References

- [0001-project-initialization.md](./0001-project-initialization.md)
- [0002-harness-server-mvp.md](./0002-harness-server-mvp.md)
- [0003-react-web-ui.md](./0003-react-web-ui.md)
- [../knowledge/requirements.md](../knowledge/requirements.md)
- [../knowledge/invariants.md](../knowledge/invariants.md)
- [../knowledge/conventions.md](../knowledge/conventions.md)
