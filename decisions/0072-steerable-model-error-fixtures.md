# 0072. Steerable Model Error Fixtures & Failure Simulation

Date: 2026-11-19

## Status

Accepted

## Context

The steerable model provider introduced in [0056-steerable-model-provider.md](./0056-steerable-model-provider.md) allowed developers and test suites to script assistant responses (text, reasoning, and tool calls) deterministically without calling live LLMs. However, queued responses could only represent successful model outputs. The only way to trigger an execution failure was to leave the queue empty under `SteerableEmptyQueueStrategy.ERROR` or wait for a timeout, which yielded a generic `SteerableQueueEmptyError`.

In production workflows, agents encounter a wide variety of failure modes:
1. **Transient failures** (e.g. API timeouts, temporary network drops, momentary rate limits, service 500s).
2. **Permanent failures** (e.g. running out of cash / quota exhaustion, 401 unauthorized, deprecated model).
3. **Mid-stream failures** where reasoning or partial text was emitted before the connection dropped.

The Autocontinue Daemon introduced in [0070-autocontinue-daemon.md](./0070-autocontinue-daemon.md) supervises execution failures, analyzes lineage and failure details to classify errors as transient (`yes`) or permanent (`no`), and branches from the last successful bubble. To thoroughly test the daemon and give developers a way to simulate real-world failure scenarios on demand, steerable models needed the ability to emit specific, configurable errors.

## Decision

### 1. Error Schema & Response Extension (`src/seamus/harness/steerable.py`)

- Add `SteerableError` model:
  - `error_type: str = "RuntimeError"`
  - `message: str = "Simulated steerable error"`
  - `status_code: int | None = None`
- Extend `SteerableResponse` with optional `error: SteerableError | None = None`.
- Add standard presets dictionary `STEERABLE_ERROR_PRESETS`:
  - `network_timeout` / `timeout`: `APITimeoutError` (status `408`, transient)
  - `out_of_cash` / `insufficient_quota`: `RateLimitError` (status `429`, permanent billing exhaustion)
  - `rate_limit`: `RateLimitError` (status `429`, transient rate limit spike)
  - `auth_failure` / `unauthorized`: `AuthenticationError` (status `401`, permanent)
  - `server_error` / `internal_server_error`: `InternalServerError` (status `500`, transient)
- Provide a convenience constructor `SteerableResponse.for_error(preset_or_error, *, reasoning=None, text=None)`.

### 2. Dynamic Exception Emitting Engine (`src/seamus/harness/steerable.py`)

- Define `SteerableSimulatedError(RuntimeError)` with `.status_code`.
- Implement `create_steerable_exception(error_type, message, status_code)` using dynamic typing `type(error_type, (SteerableSimulatedError,), {})`. This guarantees that `type(exc).__name__` precisely matches `error_type`, allowing `runner.py`, `SeamusLangGraphAgent._last_error`, and `_format_autocontinue_payload` to see the exact class name (`APITimeoutError`, `RateLimitError`, etc.).
- In `_generate` and `_agenerate`: consume the response, record the invocation, and raise the exception if `response.error` is present.
- In `_stream` and `_astream`: if `reasoning` or `text` is specified alongside `error`, emit those chunks first before raising the exception. This simulates mid-stream failures and allows verifying that `find_last_successful_bubble` accurately slices history after the emitted reasoning bubble.

### 3. API & Serialization (`src/seamus/server/schemas.py`, `ui/src/utils/steerable.ts`)

- Expose `SteerableError` in schemas and API types.
- The existing session routes (`POST/PUT .../steerable/{instance_id}/responses`) accept `SteerableResponse` objects and seamlessly support `error`.
- Update `parseResponse()` and `serializeSteerableQueue()` in `ui/src/utils/steerable.ts` to parse, validate, and serialize `error` fields in downloaded and uploaded queue files.

### 4. Agent Inspector UI (`ui/src/components/SteerableInspector.tsx`, `ui/src/App.css`)

- **1-Click Error Fixtures**: Each steerable instance card displays a "Simulate Error Fixtures" row with buttons for Network Timeout, Out of Cash / Quota Exceeded, Rate Limit, Auth Failure, and Server Error. Clicking any button immediately appends that fixture to the queue.
- **Composer Mode Switcher**: The composer offers `Assistant Response` and `Simulated Error` tabs. In error mode, users can specify error type (with datalist suggestions), optional HTTP status code, error message, and optional pre-failure reasoning.
- **Queue Item Visualization**: Queued error items render with distinctive styling (`.is-error` with rose border/background), an `AlertCircle` icon, error type badge, HTTP status code badge, error message, and pre-failure reasoning indicators.

### 5. Automated Autocontinue Daemon Test Matrix (`tests/e2e/test_autocontinue_daemon.py`)

A comprehensive end-to-end test matrix verifies the interaction between steerable error injection and the Autocontinue Daemon:
- **Transient error recovery**: Transient errors (`rate_limit` 429, `server_error` 500) paired with affirmative daemon decisions (`"yes"`, numeric `"1"`) automatically branch a child session and complete the task.
- **Permanent error ignore**: Permanent errors (`auth_failure` 401, custom unhandled `ZeroDivisionError`) paired with negative daemon decisions (`"no"`, `"stop"`) halt execution without branching child sessions.
- **Ambiguous output fallback**: Ambiguous or unparseable daemon text safely defaults to halting (`parse_autocontinue_response` returns `False`).
- **Daemon failure resilience**: If the daemon's own inference model raises a simulated error (e.g. 500 `InternalServerError`) or runs out of queued responses under `ERROR` strategy, the runner logs the failure gracefully, the session remains safely in `SessionStatus.FAILED`, and the harness process does not crash.

## Consequences

- Test suites can deterministically verify autocontinue daemon decisions for both transient and permanent failure modes without live LLM network calls.
- Mid-stream reasoning failures can be simulated to verify last-successful-bubble slicing.
- Operators can inject simulated error fixtures with a single click in the Agent Inspector.
- Queue export and import files preserve scripted error definitions.

