# 0022. Session Branching and Lifecycle Error Handling

Date: 2026-11-01

## Status

Accepted

## Context

Prior to this decision, sessions in Seamus were linear sequences of threads without branching capabilities. If a session failed (e.g. connection timeout, model error, crash), or if a user wanted to explore an alternative line of implementation from an earlier point in the conversation, there was no native mechanism to fork or retry. Retrying required manually creating a new session from scratch and losing context, or attempting to continue on a broken state.

Furthermore, sessions lacked a formal lifecycle state: unhandled errors only set the active thread status to `ERROR` without disabling future turn dispatches or releasing container/PR resources, leaving the session in an ambiguous state.

## Decision

1. **Session Lifecycle States (`ACTIVE`, `KILLED`, `FAILED`)**:
   - Model `SessionStatus` enum on `Session` entities:
     - `ACTIVE`: Normal operational state where turns can be executed.
     - `KILLED`: Explicit manual termination initiated by the user (via "Kill Session" button or `POST .../kill`).
     - `FAILED`: Automatic terminal transition triggered upon unhandled exceptions or execution failures in `SessionAgentRunner`.
   - **Terminal Immutability**: Sessions marked `KILLED` or `FAILED` cannot receive further user messages (`POST .../input` returns 409 Conflict) or spawn new threads.
   - **Resource Teardown**: Transitioning to a terminal state cancels running execution tasks, destroys the associated OpenSandbox container backend (`sandbox_backend.destroy()`), and closes the active Gitea Sync PR.
   - **Retained Readability**: Terminal sessions remain fully inspectable across history, diffs, and inspector tabs.

2. **Session Branching Out (`POST .../branch`)**:
   - Allow branching off any completed assistant message in a session ($S_1$) to spawn a new parallel session ($S_2$) under the same parent agent.
   - **Exact Turn Slicing**: Slices thread events up to the end of the specified assistant message turn (`RUN_FINISHED`), providing a clean conversational baseline starting in `AWAITING_USER`.
   - **Git Branch Forking**: Spawns Git branch `session/{new_session_id}` originating from the specific turn's Git commit SHA (discovered via `git log -S`), guaranteeing `/workspace` (`data/`) precisely matches the codebase state at that turn.
   - **Gitea Sync PR**: Automatically opens a new Sync PR for $S_2$ targeting `main`.
   - **Retry Quirk**: Branching is fully supported from both `ACTIVE` sessions (for experimentation) and `KILLED` or `FAILED` sessions (enabling clean manual retry from the last good agent turn). $S_1$ remains completely untouched when branched.

3. **Lineage Provenance & One-Click Navigation**:
   - Record `SessionBranchProvenance` on $S_2$ (`parent_session_id`, `parent_message_id`, `parent_session_name`, `branched_at`).
   - S2 surfaces a top-of-chat provenance banner with a one-click "Go to original" navigation button back to $S_1$, while $S_1$ remains clean.

4. **UI Usability Integration**:
   - Assistant message headers include a dedicated `<GitFork />` "Branch" action button.
   - Active sessions expose a top-bar "Kill Session" button.
   - Terminal sessions display explanatory status banners and disable composer inputs.
   - Sidebar tree displays distinctive status icons for `KILLED` and `FAILED` sessions.

## Consequences

### Positive
- Clean, native "manual retry" protocol for recovering from runtime or model errors.
- Unconstrained experimentation: users can explore parallel alternatives from any response.
- Guarantees container and Sync PR resource cleanup on failure or manual kill.
- Full provenance traceability preserved across domain entities, Git branches, and UI.

### Negative / Trade-offs
- Creating a branched session allocates a new Git branch and clones local repository state.

