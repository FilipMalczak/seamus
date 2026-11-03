# 0028. UI/UX Ergonomics, URL State Synchronization, Live Refresh, and Verbose Error Diagnostics

Date: 2026-11-03
Status: Accepted

> Supersedes in part [0014-SUPERSEDED-ui-layout-proportions-breadcrumbs](./0014-SUPERSEDED-ui-layout-proportions-breadcrumbs.md) (changing the default sidebar-to-main split ratio and double-click reset from 50/50 to 1:2).

## Context

Several Web UI and runner diagnostic improvements were identified in the project backlog:

1. **Default Layout Proportions**: While Decision [0014](./0014-SUPERSEDED-ui-layout-proportions-breadcrumbs.md) introduced a draggable split divider with a 50/50 (`0.50`) default, in practice a 50% sidebar width leaves too much empty horizontal whitespace in the navigation tree while constricting the primary chat, inspector, and diff panels. A 1:2 tree-to-chat ratio (`33.33%` sidebar / `66.67%` main content) better matches real usage.
2. **Configuration Modal Ergonomics**: `ConfigModal` required editing raw JSON for all global, agent, and session configurations, increasing the risk of syntax or enum typos when selecting models, providers, or middleware toggles.
3. **URL State Synchronization**: The Single-Page Application (SPA) did not reflect the active agent, session, thread, or main panel tab in `window.location.search`, preventing deep-linking, bookmarking, browser Back/Forward navigation, and state preservation across page reloads.
4. **Live UI State Refresh**: Both the **Changes** tab (`ChangesViewer`) and the sidebar entity tree required manual refreshes or page reloads to reflect newly written files or session/thread status transitions during and after active runs.
5. **Unhandled Error Diagnostics**: When an unhandled exception occurred in `SessionAgentRunner._run_loop()`, the `RUN_ERROR` event only broadcast `{"type": "RUN_ERROR", "message": str(exc)}` without appending it to `thread.events` for replay or including the exception class name (`error_type`) and stack trace (`traceback`).

## Decision

1. **1:2 Default Sidebar-to-Chat Split Ratio**:
   - Change the default `sidebarRatio` fallback and double-click resizer reset in `App.tsx` from `0.5` to `1 / 3` (`0.3333`).
   - Preserve user customizations in `localStorage` (`seamus_sidebar_ratio`) and existing minimum width clamps (`280px` sidebar, `300px` main panel).

2. **Structured Form & Raw JSON Modes in `ConfigModal`**:
   - Provide a bidirectional mode toggle (`Form` | `Raw JSON`) in `ConfigModal.tsx`, defaulting to `Form`.
   - In `Form` mode, render structured controls for model preset selection + custom model identifier input, inference format, base URL (with OpenRouter and OpenAI quick presets), API key (with visibility toggle and explicit `null` clear action), `todo_implementation` (`deepagents` | `none`), `skills_implementation` (when present in config), and custom `system_prompt`.
   - Retain `Raw JSON` mode with formatting and validation for power users.

3. **URL Query Parameter Synchronization**:
   - Synchronize the active agent, session, thread, and main panel tab (`chat` | `inspector` | `changes`) with URL query parameters (`?agent=...&session=...&thread=...&tab=...`).
   - Prefer human-readable entity slug names when serializing to the URL (falling back to UUIDs when unnamed), and accept either UUIDs or slug names when hydrating selection on initial load or handling browser `popstate` events.

4. **Automatic UI Polling and Turn-Transition Refresh**:
   - In `ChangesViewer.tsx`, automatically re-fetch the Sync PR diff (silently when data is already displayed) on `thread.id` change, on `agentStatus` transitions, and every `3000ms` while a turn is actively running (`AWAITING_LLM` or `EXECUTING_TOOL`).
   - In `App.tsx`, automatically trigger `refreshTree()` when `activeStatus` transitions to `AWAITING_USER` or `ERROR` and poll every `4000ms` while a turn is actively running.

5. **Verbose `RUN_ERROR` Diagnostics & Expandable Error Panel**:
   - In `SessionAgentRunner._run_loop()`, enrich the `RUN_ERROR` event payload with `error_type: type(exc).__name__` and `traceback: traceback.format_exc()`, and append it to `thread.events` before broadcasting so replayed streams preserve full failure diagnostics.
   - In `useThreadStream.ts` and `ChatArea.tsx`, capture `StreamErrorDetails` (`message`, `errorType`, `traceback`) and render an expandable diagnostic panel with an error type badge, one-click clipboard copy, and collapsible stack trace viewer.

## Consequences

- New users and double-click resets immediately get a balanced 1:2 sidebar-to-main layout.
- Common configuration adjustments can be performed via dropdowns and inputs without touching raw JSON.
- Deep links, page refreshes, and browser Back/Forward navigation preserve the exact selected agent, session, thread, and tab.
- Diff views and sidebar status indicators stay synchronized with background execution automatically.
- Unhandled provider, sandbox, or harness errors are immediately diagnosable in the Web UI without grepping server logs.

