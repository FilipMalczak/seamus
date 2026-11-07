# 0040 Session-Level UI View and Unified Thread Feed

- **Status**: Accepted
- **Date**: 2026-11-07
- **Authors**: Filip, DeepMind Pair Assistant
- **Deciders**: Filip, Seamus Harness Core Team
- **Consulted**: Seamus Harness Core Team
- **Informed**: Seamus Developer Community

## Context and Problem Statement

In Seamus, the execution architecture established in [0019-threads-modes-personas-architecture.md](./0019-threads-modes-personas-architecture.md) structures agent workflows into three levels:
1. **Agent (Persona)**: Enduring identity and capabilities.
2. **Session (Workspace & Git Branch)**: Dedicated container sandbox and `session/{id}` Git branch.
3. **Thread (Mode & Phase)**: Deterministic execution and mode-switch boundary (e.g. `plan/discuss` $\to$ `plan/make` $\to$ `plan/execute`, or mode switches between `chat` and `plan`).

Previously, the Single-Page Application (SPA) UI required users to navigate into individual threads. This model created significant conversational friction during multi-phase workflows:
- When a session advanced from discussion to plan synthesis or execution, a new thread was opened, leaving the previous conversation behind and requiring the user to switch between separate thread nodes in the sidebar.
- Selecting an agent or session did not present a holistic view of the ongoing task; it forced the user to guess which thread held the active context.
- While threads serve as isolated checkpoints and mode boundaries internally, from the user's perspective a session is a unified, progressive conversation across sequential phases.

As recorded in `knowledge/backlog.md` under *"Session-Level UI View and Unified Thread Feed [HIGH PRIO]"*, the harness required a session-level view that presents an aggregated, continuous chronological feed of all past threads in the session, with the message composer serving as a direct alias to the active open thread.

## Decision Drivers

- **Conversational Continuity**: Treat the session as the primary unit of user interaction, presenting all turns and artifacts in an unbroken chronological feed.
- **Underlying Execution Isolation**: Maintain threads as strict execution, mode, and checkpoint boundaries without leaking prompt histories or compromising Git branch safety.
- **Ergonomic Tree Navigation**:
  - Clicking an Agent opens its last active session in Session View.
  - Clicking a Session opens that session in Session View.
  - Clicking a Thread isolates that specific thread in Thread View.
- **Session View Stickiness**: Ensure that thread transitions (e.g., mode switches, plan phase transitions, or Sync PR thread acceptance) keep the user in Session View rather than forcibly redirecting to an isolated thread view.
- **Clear Visual Demarcation**: Provide clean, identifiable indicators in the bubble stream marking when a thread transition occurs, displaying the new thread's name, mode, and phase.
- **Context Scoping**: In Session View, auxiliary panels (Inspector, Changes / Sync PR diffs) inspect the session's active open thread.

## Decision

1. **Backend Session SSE Stream (`GET .../session/{session_id}/stream`)**:
   - Added `stream_session_events(session, accept_header, follow)` on `SessionAgentRunner`.
   - Replays historical events across all session threads sorted by `created_at`.
   - Emits a `THREAD_TRANSITION` event before each thread's events with `is_first: bool`, `thread_id`, `thread_name`, `mode`, `phase`, and `mode_label`.
   - While `session.status == SessionStatus.ACTIVE` and `follow=True`, subscribes to `runner.broadcaster` and streams live events across thread transitions without closing the SSE stream.

2. **Frontend Entity Selection & URL Synchronization**:
   - Represented Session View in `useAgentsTree` with `selectedThreadId: string | null` where `null` denotes Session View.
   - Added `selectSession(agentId, sessionId)` and `selectAgent(agentId)` (which resolves to the agent's last active session sorted by `last_touched_at` or `created_at` descending).
   - In `resolveSelectionFromUrl`, omitting the `thread` parameter resolves to Session View (`threadId: null`).
   - URL synchronization omits `&thread=...` when in Session View (`?agent=...&session=...&tab=chat`).

3. **Navigation Tree Interactions (`Sidebar.tsx`)**:
   - Clicking an Agent node row opens its last active session in Session View.
   - Clicking a Session node row opens that session in Session View (`selected-session` highlight).
   - Clicking a Thread node row opens that specific thread in Thread View (`selected-thread` highlight).
   - Chevron expansion toggles, inline name editing, and settings action buttons retain `e.stopPropagation()`.

4. **Thread Transition Delimiters in Bubble Feed (`ChatArea.tsx` & `App.css`)**:
   - Added `ThreadTransitionInfo` to `ChatMessage` in `ui/src/api/types.ts`.
   - When non-initial `THREAD_TRANSITION` events arrive, `useThreadStream` appends a delimiter record.
   - `ChatArea.tsx` renders `.thread-transition-separator` matching `.branch-provenance-separator`, with a `Sparkles` icon, `"Thread switched to"`, thread name/slug (clickable to isolate that thread), and a mode badge (`plan/discuss`, `plan/make`, `plan/execute`, `chat`).

5. **Inspector, Changes, and Transition Stickiness (`App.tsx`)**:
   - In Session View, `displayedThread` resolves to the session's current open thread (`activeSession.threads.find(t => t.is_open)`).
   - `AgentInspector` and `ChangesViewer` operate on the session's open thread.
   - `onThreadTransition` and `onSwitchMode` preserve `selectedThreadId === null` when in Session View, seamlessly appending new thread events to the feed without mode/thread desynchronization.

## Consequences

### Positive
- Users immediately land on a continuous, unified conversation feed when selecting agents or sessions.
- Multi-phase tasks (`plan/discuss` $\to$ `plan/make` $\to$ `plan/execute`) flow naturally in a single chat history without manual thread switching.
- Thread isolation remains available on demand by clicking individual thread nodes in the sidebar or clicking thread links within the stream dividers.
- Deep links and browser Back/Forward navigation distinguish between Session View (`?agent=...&session=...`) and Thread View (`?agent=...&session=...&thread=...`).

### Negative / Trade-offs
- Very long sessions spanning dozens of threads will stream more events on initial load. This can be addressed in future work by introducing pagination or token budgeting for initial event replay.

