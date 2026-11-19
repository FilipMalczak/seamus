# 0070. Autocontinue Daemon & Branching Recovery

Date: 2026-11-19

## Status

Accepted

## Context

When an agent execution encounters an unhandled exception or fatal provider failure during `SessionAgentRunner._run_loop()`, the session transitions to `SessionStatus.FAILED`, destroys its sandbox container, and stops accepting user inputs. Previously, recovering from a failure required manual inspection by the user and manual branching to attempt recovery.

However, many failures in agent workflows are transient (e.g., temporary timeouts, momentary network glitches, recoverable tool execution hiccups). In contrast, others are permanent (running out of credits, quota exhaustion, offline network, 401 unauthorized). Furthermore, without supervision, automated retries risk spinning in infinite failure loops when a recurring error persists across retry attempts.

To solve this, Seamus introduces the **Autocontinue Daemon**: a lightweight, non-agentic supervisor daemon that evaluates session execution failures and takes appropriate automated recovery or termination actions.

## Decision

1. **Configuration Schema (`src/seamus/config/models.py`)**:
   - Add `DaemonAutocontinueConfig` with fields:
     - `enabled: bool = True`
     - `provider: InferenceConfig | None = None`
     - `model: str | None = "openai/gpt-oss-120b"`
   - Validate that `model` is provided when `enabled: True`, and validate symbolic secret references.
   - Add `autocontinue: DaemonAutocontinueConfig = Field(default_factory=DaemonAutocontinueConfig)` to `DaemonsConfig`.
   - Update `AgentConfig` daemons container and copy overrides.

2. **Session Disabling & Terminal State (`src/seamus/domain/entities.py`, `src/seamus/server/schemas.py`)**:
   - Add `disabled: bool = False` to `Session`.
   - Add `disable()` method to `Session` which sets `disabled = True`, sets `config.daemons.autocontinue.enabled = False`, calls `fail()`, and updates timestamps.
   - Update `is_active` to return `self.status == SessionStatus.ACTIVE and not self.disabled`.
   - Expose `disabled: bool = False` on `SessionSummaryResponse` and `SessionDetailResponse`.

3. **Autocontinue Evaluation Engine (`src/seamus/harness/daemons/autocontinue.py`)**:
   - Assemble evaluation payload:
     - Short recent conversation exchanges from thread events via `format_thread_history`.
     - Specific failure details: exception class name, error message, and traceback snippet.
     - Lineage and latest execution span history: ancestor lineage depth, prior parent session ID, error counts in current thread, and failed tool results.
   - System instructions instruct the supervisor to evaluate failure and return one of three strict outputs:
     - `retry`: For transient, recoverable, or intermittent failures.
     - `no`: For permanent or external failures (credit exhaustion, quota limits, offline network, invalid credentials, model unavailable).
     - `stop, its dead Jim`: For recurring failures across spans/lineage, persistent error loops, or frequent recent retries.
   - `parse_autocontinue_response(raw)`: Normalizes loose LLM text into `AutocontinueAction.RETRY`, `AutocontinueAction.NO`, or `AutocontinueAction.DEAD_JIM`.

4. **Last Fully Successful Bubble Slicing & Branching**:
   - `find_last_successful_bubble(thread: Thread) -> tuple[str, str] | None`:
     - Inspects thread events up to the fatal error to identify the last completed, fully successful bubble:
       - User messages (`"user_message"`).
       - Synthetic system events (`"system_event"`).
       - Assistant reasoning blocks (`"bot_thinking"`).
       - Completed tool call groups (`"tool_call"`) where all tools in the group finished without error.
   - When action is `RETRY`:
     - Calls `store.branch_session(..., target_id=target_id, position="after", item_type=item_type)`.
     - Granular branching slices event history right after the successful bubble, copies checkpoints, and immediately triggers background resumption of the turn in the child session (`AWAITING_LLM`).
   - When action is `DEAD_JIM`:
     - Calls `runner.session.disable()`, permanently disabling the session and disabling autocontinue on it.
   - When action is `NO`:
     - Leaves the session in `FAILED` status without retrying.

5. **Daemon Steerable Simulation Support (`src/seamus/harness/daemons/engine.py`, `src/seamus/harness/runner.py`)**:
   - Extend `invoke_daemon` and `_invoke_steerable_daemon` with `raw: bool = False` to return unparsed text for non-slug daemons.
   - Register session-scoped steerable instance `daemon_instance_id(session.id, daemon="autocontinue")` (`session:{id}:daemon:autocontinue`).

6. **Web UI Updates (`ui/src/`)**:
   - `ConfigModal.tsx`: Add Autocontinue Daemon configuration section with status toggle, model identifier input with presets (`openai/gpt-oss-120b`, `openai/gpt-oss-20b`, etc.), and custom provider configuration.
   - `ChatArea.tsx`: When `sessionDisabled` is true, render a prominent "Stop, it's dead Jim" notice indicating that the session has been permanently disabled following persistent failures.

## Consequences

- Transient execution failures automatically recover by branching from the exact last successful conversational element without manual intervention or context loss.
- Permanent failures (credits, quotas, auth) fail fast without wasteful retries.
- Persistent error loops are halted by the "dead Jim" condition, preventing infinite branching cascades.

