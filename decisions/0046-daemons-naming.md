# 0046. Non-Agentic Daemons & Geometric Stepback Thread/Session Naming

Date: 2026-11-08

## Status

Accepted

## Context

Agents in Seamus run full execution loops with tool calling, checkpointing, and conversational message state. However, routine background tasks such as generating descriptive slugs for threads and sessions do not require agentic capabilities, tool use, or multi-turn dialogues. Using full agentic loops or expensive flagship models for naming introduces unnecessary latency, cost, and complexity.

To solve this, Seamus requires a notion of **daemons**: lightweight, non-agentic, one-shot LLM utilities using plain `Instructions: ... Input: ... Output:` prefill prompts running on cheap or local models.

Key requirements for thread and session naming:
1. **Configuration**: Configured under `agent_config.daemons.naming` with `enabled`, `provider` (optional, inheriting the agent's main inference config by default), and `model` (mandatory when enabled). Configurations with `enabled: false` and explicit provider/model details must remain valid.
2. **Scheduling**: Stepback schedule doubling geometrically on full user/assistant exchanges ($1, 3, 7, 15, \dots$ / $2^k - 1$).
3. **Scope & Hierarchy**:
   - Thread naming counts exchanges per thread, summarizing thread messages and artifacts while avoiding occupied thread slugs in the session.
   - For single-thread sessions, the session slug mirrors the thread slug (sans conflicts with other sessions).
   - For multi-thread sessions, session naming runs based on aggregate exchanges across all threads in the session, synthesizing the broader objective from thread slugs while avoiding occupied session slugs under the agent.
4. **Parallel Slug Model**: User-assigned custom slugs must always take precedence over daemon-generated slugs. Daemon slugs must still be computed in parallel in the background, providing automatic fallback if a user clears their custom slug.
5. **Preemptive Loose Parsing**: Small or dumb models frequently ignore negative formatting instructions (e.g., emitting markdown code blocks, quotes, or conversational noise). Output parsing must defensively clean and normalize output into valid slugs.

## Decision

1. **Configuration Schema (`src/seamus/config/models.py`)**:
   - Add `DaemonNamingConfig` with fields `enabled: bool = False`, `provider: InferenceConfig | None = None`, and `model: str | None = None`. Validate that `model` is provided when `enabled: True`.
   - Add `DaemonsConfig` containing `naming: DaemonNamingConfig`.
   - Add `daemons: DaemonsConfig = Field(default_factory=DaemonsConfig)` to `AgentConfig`.
   - Update `AgentConfig.copy_with_overrides()` to merge daemon configurations.

2. **Parallel Slug Storage (`src/seamus/domain/entities.py`)**:
   - In `Thread` and `Session`, store `custom_name: str | None = None` and `daemon_name: str | None = None`.
   - Implement `@computed_field @property def name(self) -> str | None` returning `custom_name or daemon_name or None`.
   - Implement `@name.setter` setting `custom_name`. Assigning `None` clears the custom slug and exposes `daemon_name`.
   - Add `exchange_count: int = 0` on `Thread`, and `@property def total_exchange_count(self) -> int` on `Session`.

3. **Preemptive Loose Parsing & Daemon Engine (`src/seamus/harness/daemons/`)**:
   - `parser.py`: Implement `parse_loose_slug(raw_output, occupied_slugs, max_length=50)`. Defensive unwrapping of fenced code blocks (`` ``` ``), triple quotes (`"""`, `'''`), single/double quotes, and markdown blockquotes (`>`). Strips label prefixes (`Output:`, `Slug:`) and sanitizes into `^[a-z0-9]+(?:-[a-z0-9]+)*$`. Resolves collisions against occupied slugs by appending numeric suffixes (`-2`, `-3`).
   - `formatter.py`: Formats thread messages and artifact events into clean prompt excerpts:
     - Assistant artifacts formatted as `[Artifact: <kind> "<title>"] <details>`.
     - User unblocking and button clicks formatted as `User: [Artifact Action: '<button>' on '<artifact>']`.
   - `engine.py`: `invoke_daemon(provider, model, instructions, input_payload, occupied_slugs)` executes single-turn one-shot inference using OpenAI-compatible endpoints with automatic Ollama model probing.
   - `naming.py`:
     - `is_stepback_trigger(count)`: Evaluates `count > 0 and ((count + 1) & count) == 0`.
     - `execute_thread_naming(runner, thread)`: Background task updating `thread.daemon_name` and mirroring to `session.daemon_name` for single-thread sessions.
     - `execute_session_naming(runner)`: Background task updating `session.daemon_name` for multi-thread sessions.

4. **Exchange Counting & Scheduling Integration (`src/seamus/harness/runner.py`)**:
   - In `_run_loop()`, when a turn finishes cleanly (`thread.status != AgentStatus.ERROR` and `session.is_active`):
     - Increment `thread.exchange_count += 1`.
     - If `is_stepback_trigger(thread.exchange_count)`, dispatch `execute_thread_naming`.
     - If `len(session.threads) > 1` and `is_stepback_trigger(session.total_exchange_count)`, dispatch `execute_session_naming`.

5. **Persistence & Deserialization (`src/seamus/persistence/workspace.py`, `src/seamus/harness/store.py`)**:
   - Persist `custom_name`, `daemon_name`, and `exchange_count` in session `config.json`.
   - Hydrate both custom and daemon slugs during repository reconstruction.

6. **Deferred Backlog Entry (`knowledge/backlog.md`)**:
   - Record generic daemon manifest extraction, custom event filters, and alternative selection strategies under Deferred.

## Consequences

- Sessions and threads receive human-readable, context-aware slugs automatically without manual user naming.
- Low-tier or local models can be targeted for daemons independently of the agent's main inference model, keeping operational costs minimal.
- User-specified custom slugs are strictly prioritized, with automatic fallback to daemon slugs if removed.
- Loose output parsing guarantees resilience against formatting idiosyncrasies common to smaller models.

