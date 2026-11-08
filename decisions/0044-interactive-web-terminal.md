# 0044. Interactive Web Terminal & Real-Time Shell Emulator for Agent Sandbox

Date: 2026-11-08

## Status

Accepted

## Context

Developers and operators inspecting active agent sessions previously had to locate container IDs on the Docker host (`docker exec -it sandbox-... bash`) to inspect running processes, check installed tools, examine mounted volumes, test commands, or diagnose Git state.

To provide immediate, non-intrusive visibility into the agent's execution environment directly inside the Seamus Web UI, an interactive web terminal was needed. Furthermore, output must appear on screen ASAP in real-time as commands run (e.g. during long builds, tests, or package installations), making buffered command responses unacceptable.

## Decision

1. **Real-Time Streaming Backend (`src/seamus/harness/runner.py`, `src/seamus/server/routes/sessions.py`)**:
   - Exposed `POST /agent/{agent_identifier}/session/{session_identifier}/terminal/stream` returning a `StreamingResponse(media_type="text/event-stream")`.
   - In `SessionAgentRunner.stream_terminal_command`, commands execute inside the session's active OpenSandbox container using `ExecutionHandlersSync` (`on_stdout`, `on_stderr`).
   - Output lines stream immediately via an asynchronous queue and threadsafe event dispatch (`loop.call_soon_threadsafe`), ensuring zero buffering delay.
   - Command execution is wrapped to track working directory changes across `cd` invocations (`__SEAMUS_CWD__=$(pwd)` sentinel) while preserving the command's exact exit code.
   - Dispatches SSE event objects:
     - `stdout`: chunked standard output lines.
     - `stderr`: chunked standard error lines.
     - `exit`: exit code and updated working directory.
     - `error`: execution error messages.
   - Exposed `GET /agent/{agent_identifier}/session/{session_identifier}/terminal/info` returning the active working directory and container status.

2. **Interactive Terminal View & Web UI Integration (`ui/src/components/TerminalView.tsx`, `ui/src/App.tsx`)**:
   - Added a first-class `Terminal` tab to `main-panel-tabs` alongside `Chat`, `Inspector`, and `Changes`, with URL query parameter deep-linking (`?tab=terminal`).
   - Implemented `TerminalView` featuring:
     - Monospaced, dark-themed scrollable terminal output buffer.
     - Real-time SSE stream consumption via `ReadableStream` (`res.body.getReader()`).
     - Command prompt displaying active working directory: `sandbox:${cwd}$ `.
     - Command input with history navigation (`↑`/`↓` keys) and Enter to run.
     - Client-side command interruption (`AbortController` / Cancel button) triggering SIGINT.
     - Quick action buttons for common developer tasks (`ls -la`, `git status`, `pwd`, `which tools`, `ps aux`, `inspect sandbox`).
     - Exit status indicators (green check on 0, red status on non-zero).
     - Buffer clearing via `Ctrl+L` or Clear button.

## Consequences

- Developers can immediately inspect running processes, test commands, and verify container tools without leaving the Seamus Web UI or accessing the Docker host.
- Real-time streaming provides instantaneous feedback for long-running scripts and builds.
- Directory state is preserved across commands, enabling natural shell navigation (`cd`, `git`, etc.).
