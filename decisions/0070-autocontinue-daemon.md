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

2. **Autocontinue Evaluation Engine (`src/seamus/harness/daemons/autocontinue.py`)**:
   - Assemble evaluation payload:
     - Short recent conversation messages from thread events via `format_thread_history`.
     - Specific failure details: exception class name, error message, and formatted traceback.
     - Lineage and latest execution span history: ancestor lineage depth, prior parent session ID, error counts in current thread, and failed tool results.
   - Instruct the supervisor daemon to evaluate failure and return a boolean answer:
     - `yes` (or `true`): If the failure appears transient, intermittent, or recoverable (e.g. temporary timeout, momentary network glitch, transient tool execution hiccup, rate limit).
     - `no` (or `false`): If the failure is unrecoverable, permanent, or external (e.g. credits depleted, quota exhausted, network down, 401 unauthorized, syntax errors, or if repeated retries have already occurred across spans and lineage).
   - `parse_autocontinue_response(raw) -> bool`: Robust, smart boolean parser accepting truthy values (`yes`, `true`, `True`, `1`, `retry`, `y`, `t`) and rejecting falsy/negative values (`no`, `false`, `False`, `0`, `stop`, empty/None).

3. **Last Fully Successful Bubble Slicing & Branching**:
   - `find_last_successful_bubble(thread: Thread) -> tuple[str, str] | None`:
     - Inspects thread events up to the fatal error to identify the last completed, fully successful bubble:
       - User messages (`"user_message"`).
       - Synthetic system events (`"system_event"`).
       - Assistant reasoning blocks (`"bot_thinking"`).
       - Completed tool call groups (`"tool_call"`) where all tools in the group finished without error.
   - When decision is `True` (retry):
     - Calls `store.branch_session(..., target_id=target_id, position="after", item_type=item_type)`.
     - Granular branching slices event history right after the successful bubble, copies checkpoints, and immediately triggers background resumption of the turn in the child session (`AWAITING_LLM`).
   - When decision is `False` (no retry):
     - Leaves the session in `FAILED` status without retrying or branching.

4. **Daemon Steerable Simulation & Invocations Inspection (`src/seamus/harness/daemons/engine.py`, `src/seamus/harness/steerable.py`)**:
   - Extend `invoke_daemon` and `_invoke_steerable_daemon` with `raw: bool = False` to return unparsed text for non-slug daemons.
   - Register session-scoped steerable instance `daemon_instance_id(session.id, daemon="autocontinue")` (`session:{id}:daemon:autocontinue`).
   - Add `invocations` and `record_invocation` to `SteerableInstance`, allowing deterministic test suites to inspect and verify the exact input payload passed into the daemon.

5. **Web UI Updates (`ui/src/`)**:
   - `ConfigModal.tsx`: Add Autocontinue Daemon configuration section with status toggle, model identifier input with presets (`openai/gpt-oss-120b`, `openai/gpt-oss-20b`, etc.), and custom provider configuration.

## Consequences

- Transient execution failures automatically recover by branching from the exact last successful conversational element without manual intervention or context loss.
- Permanent failures (credits, quotas, auth) and repeated retry spirals across spans/lineage fail fast with a simple `no` decision without wasteful branching cascades.
- Steerable testing allows full verification of daemon input payloads and multi-turn retry lifecycles.

