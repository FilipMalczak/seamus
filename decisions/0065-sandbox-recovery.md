# 0065. Transparent OpenSandbox Container Recovery and TTL Renewal

Date: 2026-11-15

## Status

Accepted

## Context

`RunnerRegistry` caches `SessionAgentRunner` instances in memory for the lifetime of the server process, and each runner holds a `SeamusOpenSandboxBackend` whose `_active_sandbox` container is provisioned with a finite TTL (`OPENSANDBOX_SANDBOX_TIMEOUT`, default `3600` seconds) and `[renew_intent] enabled = false` in `opensandbox/sandbox.toml`.

When a sandbox container expires or is removed externally while the runner remains cached, the next tool call (`ls`, `read_file`, `execute`, etc.) or interactive terminal command raises `SandboxApiException` (`DOCKER::SANDBOX_NOT_FOUND`). Because `ToolNode` does not catch `SandboxApiException`, the unhandled exception failed the entire session (`self.session.fail()`), permanently blocking further user input even though all persistent state (`/workspace`, `/artifacts`, `/skills`, external repositories) lives on host-mounted volumes.

## Decision

1. **Single-Retry Container Recovery (`src/seamus/harness/sandbox.py`)**:
   - Add `is_sandbox_not_found(exc)` to detect `SandboxApiException` instances representing missing containers (`status_code == 404` or `SANDBOX_NOT_FOUND` in error code/message).
   - Add `SeamusOpenSandboxBackend.run_with_recovery(fn)` to catch `SANDBOX_NOT_FOUND`, close the stale HTTP transport, clear `_active_sandbox`, and retry `fn()` once so `_ensure_sandbox()` transparently provisions a fresh container with the session's mounted volumes.
   - Wrap `execute()`, `upload_files()`, and `download_files()` on `SeamusOpenSandboxBackend` with this single-retry recovery (also inspecting `upload_files`/`download_files` error strings where the base class catches inner `SandboxApiException`s).
   - Route `SessionAgentRunner.stream_terminal_command()` (`src/seamus/harness/runner.py`) through `backend.run_with_recovery(...)`.
   - Unrelated `SandboxApiException` errors and repeated `SANDBOX_NOT_FOUND` failures after recreation are not swallowed and propagate normally.

2. **Automatic TTL Renewal (`opensandbox/sandbox.toml`)**:
   - Enable `[renew_intent] enabled = true` (with `min_interval_seconds = 60`) so active sessions automatically extend their sandbox TTL on activity.

## Consequences

- Idle or externally-pruned sandbox containers no longer permanently fail active sessions; the next tool or terminal call transparently reprovisions the container with all host-mounted volumes intact.
- Ephemeral state outside mounted volumes (such as background processes or files written outside `/workspace`) is still lost on container recreation, consistent with [0010-opensandbox-filesystem-sandboxing.md](./0010-opensandbox-filesystem-sandboxing.md).

