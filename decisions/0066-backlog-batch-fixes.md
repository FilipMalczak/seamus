# 0066 — Backlog Batch Fixes

## Context

A batch of nine small-to-medium backlog items across persistence, infrastructure, backend routes, and the React Web UI was selected for implementation together on `0066-backlog-batch-fixes`.

## Decisions

1. **Dedicated PostgreSQL Role & Database for OpenBao**
   - `openbao-db-init` in [docker-compose.yml](../docker-compose.yml) provisions a dedicated `openbao` PostgreSQL role and `openbao` database, and [openbao/config.hcl](../openbao/config.hcl) connects exclusively to that database instead of sharing the `gitea` user and database.

2. **Offloading Synchronous Git Subprocesses in Async Server Flows**
   - `GitWorkspaceManager._run_git` and `ExternalRepoManager._run_git` remain synchronous so existing sync callers, unit tests, and LangGraph's synchronous `BaseCheckpointSaver` methods stay unchanged.
   - `async` FastAPI route handlers in `src/seamus/server/routes/` (`agents.py`, `sessions.py`, `threads.py`, `config.py`, `settings.py`) and `GitCheckpointSaver.aput` offload blocking Git and disk persistence calls via `await asyncio.to_thread(...)`.

3. **Interactive Tool Disabling from Agent Inspector**
   - `AgentConfig.disabled_tools: list[str]` stores disabled tool names on the session configuration.
   - `SessionAgentRunner` filters out `disabled_tools` dynamically per turn when binding tools, so toggling a tool via `PATCH /api/v-alpha/agent/{agent}/session/{session}/inspector/tools` takes effect on the next turn without rebuilding the graph.
   - `ToolInspectInfo.enabled` reflects the toggle state in `AgentInspector.tsx`.

4. **Configurable Terminal Session Timeout & Tab Autocomplete**
   - `SystemSettings.terminal_session_timeout_seconds` (default `300`, `0` = never expire) replaces the hardcoded 5-minute client timeout, exposed via `GET .../terminal/info` and editable in `SettingsModal.tsx`, with an inline UI reset notice in `TerminalView.tsx`.
   - `POST /api/v-alpha/agent/{agent}/session/{session}/terminal/complete` runs a fast `compgen` probe inside the sandbox at the active `cwd` and returns `{ token, common_prefix, candidates }` when `Tab` is pressed in `TerminalView.tsx`.

5. **Artifact Tab Close, Conversational Anchors, Timestamps & Notifications**
   - Non-blocking tabbed artifacts in `App.tsx` support local header close (`X`) without mutating server `is_closed`, and `MessageItem.tsx` renders clickable conversational anchor chips for tabbed artifacts created by tool calls.
   - `useThreadStream.ts` uses `getEventTimestamp(event)` for `threadTransition` messages as well as streamed/replayed parts.
   - `useInteractionNotifications.ts` updates `document.title` and fires Web Notifications when a hidden tab awaits user input or errors.
   - Parallel e2e execution (`pytest-xdist` `-n auto` in `test.sh`) was verified as already active and passing.

