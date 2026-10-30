# 0006. External System Links and Telemetry Endpoint Exclusions

Date: 2026-10-30
Status: Accepted

## Context

Users inspecting and interacting with Seamus agents need direct, seamless access to external companion systems from the Web UI—starting with the Pydantic Logfire observability dashboard. Rather than requiring users to manually construct dashboard URLs or leave the application context, the navigation panel should provide quick-launch external links.

Furthermore:
- If telemetry export to Logfire is disabled (e.g. via `LOGFIRE_SEND_TO_LOGFIRE=false` or absent tokens in `if-token-present` mode), the Logfire shortcut icon must not be displayed in the UI.
- Frequent system health probes to `/health` pollute telemetry spans and metrics, so request tracing on `/health` should be suppressed.

## Decision

1. **System Info REST API (`GET /api/v-alpha/system/info`)**:
   - Expose system integration metadata via a dedicated FastAPI endpoint under `/api/v-alpha/system/info`.
   - Provide `SystemInfoResponse` returning `logfire: SystemLogfireInfo(enabled: bool, service_name: str, url: str | None)`.
   - Hardcode the Logfire dashboard target URL pattern: `https://logfire-eu.pydantic.dev/filip-malczak/{service_name}`, defaulting `service_name` to `seamus` if unspecified.

2. **Telemetry Configuration & Active Status Guard**:
   - Update `seamus.telemetry.setup_telemetry` to explicitly evaluate `LOGFIRE_SEND_TO_LOGFIRE` environment variable values (`false`, `0`, `off`, `no`, `never` resolving to `False`; `true`, `1`, `on`, `yes`, `always` resolving to `True`; `if-token-present` resolving to token presence check).
   - Provide `is_logfire_enabled() -> bool` and `get_logfire_service_name() -> str` helper functions in `seamus.telemetry`.

3. **FastAPI Request Tracing Exclusion**:
   - Update `seamus.telemetry.instrument_fastapi` to support URL regex exclusions via `excluded_urls`, defaulting to `r".*/health.*"` to prevent `/health` heartbeat checks from emitting traces.

4. **Navigation Tree Left Panel Footer**:
   - In `Sidebar.tsx`, add a footer section below `.sidebar-tree` pinned to the bottom of the navigation left panel.
   - When Logfire is enabled (`systemInfo.logfire.enabled === true`), render a styled flame icon button linking to `https://logfire-eu.pydantic.dev/filip-malczak/${LOGFIRE_SERVICE_NAME=seamus}` with `target="_blank"` and `rel="noopener noreferrer"`.
   - Provide an accessible tooltip indicating the target Logfire service name.
   - When Logfire is disabled, the icon is omitted from the UI.

## Consequences

- Direct one-click access to the Logfire observability project from the web interface.
- Automatic respect for telemetry configuration toggles (`LOGFIRE_SEND_TO_LOGFIRE` and token presence).
- Clean telemetry traces without noisy `/health` probe spans.
- Foundation established for future external system shortcuts in the sidebar footer.

## Cross-References

- [0001-project-initialization.md](./0001-project-initialization.md)
- [0002-harness-server-mvp.md](./0002-harness-server-mvp.md)
- [0003-react-web-ui.md](./0003-react-web-ui.md)
- [0004-inline-tree-editing-session-status.md](./0004-inline-tree-editing-session-status.md)
- [0005-logfire-integration.md](./0005-logfire-integration.md)
- [../knowledge/requirements.md](../knowledge/requirements.md)
- [../knowledge/invariants.md](../knowledge/invariants.md)
- [../knowledge/architecture.md](../knowledge/architecture.md)
- [../knowledge/abstractions.md](../knowledge/abstractions.md)
- [../knowledge/vocabulary.md](../knowledge/vocabulary.md)

