# 0056. Steerable (Scripted) Model Provider & Inspector Queue Editor

Date: 2026-11-13

## Status

Accepted

## Context

Local development and manual verification of Seamus features (interactive A2UI
questionnaires, diff viewers, tool-call lifecycles, error handling) required a live
LLM endpoint. That made verification slow, non-deterministic, and costly, and it
made it impossible to reproduce a specific failure on demand.

The backlog called for a "steerable model" — a provider that lets a developer
script, step through, or interactively inject specific model responses (text,
reasoning, tool calls) into active sessions.

Existing provider support (`openai`, `ollama`) was organized around `InferenceConfig`
and `ReasoningChatOpenAI`, with the Agent Inspector exposing a read-only report of
the runtime state. There was no way to influence what the model says next, and no
place in the UI to author such responses.

## Decision

### 1. Steerable provider format (`src/seamus/config/models.py`)

- Add `InferenceFormat.STEERABLE = "steerable"` alongside `openai` and `ollama`.
- Add `SteerableConfig` nested on `InferenceConfig`:
  - `empty_queue_strategy: SteerableEmptyQueueStrategy` (`wait` | `error` | `repeat`),
    defaulting to `wait`
  - `default_response: str` — the text returned by the `repeat` strategy
  - `wait_timeout: float` — how long the `wait` strategy blocks before failing
- Steerable inference needs no API key. `InferenceConfig.requires_api_key()` is the
  single place that decides whether credentials are mandatory; it returns `False`
  for `steerable` and `ollama`. `AgentConfig.validate_complete()` reuses it, so a
  steerable agent passes validation with no credentials and no network access.

### 2. `SteerableChatModel` and the response queue (`src/seamus/harness/steerable.py`)

- `SteerableChatModel` is a `BaseChatModel` subclass that replays scripted
  responses instead of calling a provider. It implements `_generate`,
  `_agenerate`, `_stream`, and `_astream`; `_stream`/`_astream` emit discrete
  chunks (reasoning, text, tool-call name, tool-call arguments) rather than
  token-level streaming, matching how OpenAI-compatible providers stream tool
  calls and keeping the AG-UI event layer unchanged.
- `SteerableResponse` is one scripted assistant turn: optional `text`, optional
  `reasoning`, and a list of `SteerableToolCall` (`name`, `args`).
- Reasoning travels in `additional_kwargs["reasoning_content"]`, the same shape
  `ReasoningChatOpenAI` produces, so checkpointed messages and AG-UI snapshots
  treat scripted turns exactly like live ones.
- `SteerableInstance` owns the queue (`responses`), the strategy, and the known
  tool names captured by `bind_tools`. Queue mutation is guarded by a
  `threading.Condition`; the `wait` strategy blocks the model call until a
  response is pushed or `wait_timeout` elapses.
- The default empty-queue strategy is `wait`. A freshly armed instance therefore
  holds the model turn instead of failing it, which is what makes the Inspector a
  remote control: the operator queues the next response from the UI and the
  blocked turn resumes with it. `error` and `repeat` remain available for tests
  that want a turn to fail or to fall back to a canned answer.
- `SteerableModelRegistry` is a process-wide singleton mapping stable instance ids
  to instances. Ids are session scoped: `session:{session_id}:agent` for the
  session's main model and `session:{session_id}:daemon:{daemon}` for a daemon
  (currently `naming`). The registry owns the queue so the Inspector can read and
  edit it while the model consumes from it.

### 3. Wiring (`src/seamus/harness/runner.py`, `src/seamus/harness/daemons/`)

- `SessionAgentRunner._build_deep_agent()` builds a `SteerableChatModel` when the
  session's inference format is `steerable`, and registers the session's daemon
  instance eagerly so daemon responses can be queued before the daemon fires.
- `_apply_resolved_config_to_llm()` skips steerable models — they have no
  credentials to refresh.
- `invoke_daemon()` accepts a `steerable_instance_id` and routes to a steerable
  model when the daemon provider format is `steerable`. The naming daemon passes
  `session:{session_id}:daemon:naming`, so agent and daemon are steered
  independently.
- `_resolve_daemon_api_key()` returns `None` for steerable models.

### 4. Inspector and API

- `AgentInspectReport` gains `steerable_models: list[SteerableInspectInfo]`
  (instance id, role, strategy, default response, wait timeout, pending count,
  known tools, queued responses). The report lists every instance of the session,
  so the agent model and the daemon model get separate entries.
- New routes under the session family:
  - `GET   .../steerable` — list the session's steerable instances
  - `POST  .../steerable/{instance_id}/responses` — append scripted responses
  - `PUT   .../steerable/{instance_id}/responses` — replace the whole queue; an
    empty list clears it
  - `PATCH .../steerable/{instance_id}/strategy` — change the empty-queue strategy
- These routes deliberately expose no `DELETE` method: clearing the queue is
  expressed as a replacement with an empty list, preserving [INV-007](../knowledge/invariants.md#inv-007-no-resource-deletion-invariant)
  (zero HTTP DELETE routes). The `INV-007` enforcement test now inspects the
  OpenAPI schema rather than `app.routes`, because the latter does not surface
  routes mounted through nested routers and therefore could not see them.

### 5. Web UI (`ui/src/components/SteerableInspector.tsx`)

- The Agent Inspector gains a "Steerable" sub-tab, rendered only when the session
  has steerable instances. Each instance gets its own card (agent and daemon are
  separate cards) showing the queued responses in order, the empty-queue strategy
  selector, a composer for text / reasoning / tool calls (with JSON argument
  validation and known-tool suggestions), per-item removal, and clear-queue.
- A single queued response may carry several tool calls. The composer holds a
  list of tool-call rows (name plus JSON arguments) instead of a single pair of
  fields, and the whole composer — text, reasoning, and every tool-call row — is
  reset once the response is queued, so the next response does not silently
  repeat the previous tool calls.
- The queue of an instance can be exported to a JSON file and imported back.
  The exported envelope records the originating instance id, the export time, and
  the strategy, alongside the responses. An uploaded file may also be a bare list
  of responses, which makes hand-written scripts usable.
- Each instance card carries an upload-mode toggle with two options: `Replace`
  (the default) swaps the whole queue for the uploaded responses, while `Extend`
  keeps the current responses and appends the uploaded ones after them. The two
  modes map onto the existing API operations — a replacement (`PUT`) and an
  append (`POST`) — so extending a queue never has to re-send the responses that
  are already in it, and a response pushed by the model between the upload and
  the request is not lost.
- The parsing and serialization rules live in `ui/src/utils/steerable.ts` as
  pure functions, so they are covered by the UI test suite independently of the
  component.
- `ConfigModal` offers `steerable (Scripted Responses)` as an inference format for
  both the agent and the naming daemon.

### 6. Queue lifetime

The queue lives in memory, in the process-wide registry. It is intentionally not
persisted: it is a live steering surface for the current process, and persisting it
would drag the in-memory store's known multi-worker consistency caveats into the
inspector. Optional persistence is tracked in the backlog.

## Consequences

- A developer can reproduce any agent turn — text, reasoning, tool calls, and
  tool errors — deterministically and without inference costs.
- The `wait` strategy turns the Inspector into a live remote control: the model
  blocks until a response is queued, letting a human drive a session turn by turn.
  It is the default, so an unconfigured steerable instance waits rather than
  failing the turn.
- Agent and daemon models are steered independently, so a developer can script a
  daemon's naming slug separately from the agent's turns.
- The steerable provider is a distinct format rather than a mode of an existing
  one, so the live-provider code paths stay untouched.
- Queued responses are lost on backend restart; a scripted session must be
  re-armed after a restart.
- Streaming of scripted responses is chunk-granular, not token-granular.
