# 0005. Pydantic Logfire Observability and Hierarchical Spans

Date: 2026-10-30
Status: Accepted

## Context

As Seamus manages deep multi-turn agent conversations with tool calls, sub-agent delegations, and SSE event streaming, deep observability is critical for inspection, latency profiling, and debugging agent reasoning loops.

We require a first-class observability integration where:
- Every agent, session, and thread has its own dedicated spans.
- Execution traces reflect the domain hierarchy: an agent span wraps session spans, which wrap thread spans, which wrap DeepAgent/LangGraph model invocations and tool executions.
- Store lifecycle operations (creation and renaming of agents, sessions, and threads) emit structured spans.
- FastAPI REST API endpoints are automatically instrumented with request tracing.
- Telemetry behaves safely and non-invasively in local development and automated CI test suites without requiring cloud keys.

## Decision

1. **Pydantic Logfire Dependency & OTel Integration**:
   - Add `logfire[fastapi]` to project dependencies via `uv`.
   - Enable LangChain and LangGraph native OpenTelemetry export via environment variables (`LANGSMITH_OTEL_ENABLED=true`, `LANGSMITH_OTEL_ONLY=true`, `LANGSMITH_TRACING=true`), routing all underlying graph transitions, ChatOpenAI calls, and tool calls into the active Logfire span context without LangSmith keys.
   - Configure Logfire with `send_to_logfire="if-token-present"` so telemetry pushes to Logfire when `LOGFIRE_TOKEN` is present and runs safely offline during local development and testing.
   - Provide a custom scrubber callback in `seamus.telemetry` preserving domain `session` attributes and session identifiers while maintaining strict redaction of sensitive credentials, passwords, and tokens.

2. **Hierarchical Execution Spans**:
   - In `SessionAgentRunner._run_loop`, wrap the execution loop in three nested spans:
     - **Agent Span**: `agent {agent_identifier}` with attributes `agent_id`, `agent_name`, `agent_identifier`, and `model`.
     - **Session Span**: `session {session_identifier}` with attributes `session_id`, `session_name`, `session_identifier`, and `agent_id`.
     - **Thread Span**: `thread {thread_identifier}` with attributes `thread_id`, `thread_name`, `thread_identifier`, `session_id`, `agent_id`, and `run_id`.
   - All sub-operations, model invocations, and tool executions automatically nest as child spans within the thread span.
   - User message dispatch in `SessionAgentRunner.dispatch_user_input` records structured informational events.
   - Execution failures log structured error events on the span and mark status as `ERROR`.

3. **Store Lifecycle Spans**:
   - In `HarnessStore`, wrap entity creation and updates (`create_agent`, `update_agent`, `create_session`, `update_session`, `create_thread`, `update_thread`) in structured spans (`agent {agent_identifier}`, `session {session_identifier}`, `thread {thread_identifier}`) with entity metadata and `operation` tags.

4. **FastAPI Application Instrumentation & Environment Configuration**:
   - In `create_app()`, call `setup_telemetry()` and instrument the FastAPI app using `logfire.instrument_fastapi(app)` to capture route methods, status codes, latency, and parameters.
   - `setup_telemetry()` automatically discovers and loads `.env` using `python-dotenv` before initializing telemetry, honoring `LOGFIRE_TOKEN`, `LOGFIRE_SERVICE_NAME`, `LOGFIRE_SEND_TO_LOGFIRE`, and related variables.
   - Provide `.env.template` in the project root documenting all telemetry and inference configuration variables.

## Consequences

- Full-fidelity OpenTelemetry-compatible tracing across all harness executions and REST APIs.
- Clean 3-level hierarchical trace tree in the Logfire dashboard: `agent` → `session` → `thread` → [graph / tool steps].
- Offline development and test suites remain zero-dependency and fast.
- Domain "session" terminology is preserved in telemetry dashboards without being redacted as sensitive cookies.

## Cross-References

- [0001-project-initialization.md](./0001-project-initialization.md)
- [0002-harness-server-mvp.md](./0002-harness-server-mvp.md)
- [0003-react-web-ui.md](./0003-react-web-ui.md)
- [0004-inline-tree-editing-session-status.md](./0004-inline-tree-editing-session-status.md)
- [../knowledge/requirements.md](../knowledge/requirements.md)
- [../knowledge/invariants.md](../knowledge/invariants.md)
- [../knowledge/architecture.md](../knowledge/architecture.md)
- [../knowledge/abstractions.md](../knowledge/abstractions.md)
- [../knowledge/vocabulary.md](../knowledge/vocabulary.md)

