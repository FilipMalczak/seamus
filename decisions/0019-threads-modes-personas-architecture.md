# 0019. Threads, Modes, and Personas Architecture

Date: 2026-11-01

## Status

Accepted

## Context

In initial designs, Seamus primarily modeled agents as homogeneous coding assistants, with execution state tracked along sequential threads within sessions ([0001-v0-agent-core.md](./0001-v0-agent-core.md), [0012-sync-prs-and-thread-accept.md](./0012-sync-prs-and-thread-accept.md)). Threads were primarily seen as sub-conversation segments closed upon explicit user acceptance of a Sync PR.

As the harness evolves to support broader autonomous tasks (code authoring, architecture, open-ended research, administrative/office workflows, and code review), three core dimensions of agent configuration and interaction must be cleanly disentangled:
1. **Agent Archetype vs. Turn-by-Turn Operational Behavior**: An agent's persistent role, domain specialization, and default tool catalog (e.g., Coder vs. Office Worker vs. Designer) are fundamentally distinct from how the user wants the agent to interact right now (e.g., plan first vs. chat casually vs. analyze read-only vs. act directly).
2. **The Role of the Workspace**: Depending on user intent, the mounted `/workspace` directory serves completely different roles:
   - In direct implementation, it is the primary production codebase subject to Git version control and Sync PRs.
   - In conversational or advisory tasks, it serves merely as a transient scratchpad for the agent's notes or temporary test scripts.
   - In analysis or code review, it is an immutable reference inspected with read-only tools without producing modifying commits.
3. **Thread Boundaries as Lifecycle and Mode Triggers**: In existing implementations, thread transitions were only triggered by explicit human thread acceptance (`POST /sessions/{id}/accept`). However, switching execution posture (such as moving from a planning phase to an execution phase, or switching from conversational discussion to active coding) requires clean conversational and checkpoint boundaries.

## Decision

We establish an architectural triad defining the relationships, boundaries, and lifecycles across **Personas**, **Modes**, and **Threads**:

```
Agent (configured with Persona)
  └── Session (dedicated workspace & branch)
        └── Thread (executing in specific Mode)
```

### 1. Personas (Agent-Level Archetypes)
- **Definition**: A **Persona** defines what an agent *is*. It is configured during Agent creation and persists across all sessions spawned under that agent.
- **Responsibilities**:
  - Sets the canonical `<identity>` and domain framing (e.g., `Coder`, `Office Worker`, `Designer`, `Data Scientist`, `Researcher`).
  - Determines available tool palettes and backend environments provisioned for the agent.
  - Establishes baseline behavioral invariants and domain-specific rules.

### 2. Operational Modes (Thread/Session-Level Posture)
- **Definition**: A **Mode** defines what the agent *does right now*. It governs interaction style, prompt framing, tool permissions, and the operational role of the `/workspace`:
  - `plan`: Formulates a thorough, structured plan first. Read-only inspection tools are encouraged; writes are restricted to planning scratchpads until approved. Transitioning to execution triggers a mode switch.
  - `chat`: Conversational orientation. Dialogue is primary; the workspace is not the primary deliverable, serving merely as an agent scratchpad for calculations or temporary files.
  - `act`: Direct execution mode. Follows user commands immediately, authoring focused diffs and executing tasks without upfront planning overhead.
  - `analyse`: Read-only workspace investigation. Answers questions, analyzes architecture, and verifies behaviors without modifying persistent codebase files.

### 3. Threads as Execution Boundaries and Mode-Switching Triggers
- **Core Principle**: A **Thread** is the atomic conversational and checkpoint boundary for an agent executing in a specific Mode.
- **Mode Switching Spawns New Threads**: Whenever a session switches between operational modes (e.g., from `chat` to `act`, or `analyse` to `plan`), the active thread is closed and a new thread is automatically spawned on the session branch.
- **Mode-Specific Thread Triggers**: In addition to manual mode changes and explicit Sync PR acceptance:
  - In `plan` mode: Formulating a new plan executes in a planning thread; approving the plan and initiating implementation transitions the mode to `act` (or plan execution) and opens a new thread.
  - In `analyse` mode: Focusing on a distinct inquiry scope or hypothesis opens a dedicated thread, preserving distinct analytical reasoning streams.
  - In `chat` mode: Exploratory discussions remain isolated in their own thread, preventing scratchpad debris from polluting the execution thread or Git Sync PR diffs.

### 4. Integration with Git Persistence and State Checkpointing
- Checkpoint event streams and LangGraph state continue to be recorded per-thread under `agent/state/threads/{thread_id}/` ([0008-git-persistence.md](./0008-git-persistence.md)).
- Thread closure seals the AG-UI event log and state history for that phase.
- Only threads that introduce persistent changes under `data/` contribute to the session's active Sync PR targeting `main`.

## Consequences

### Positive
- Clarifies vocabulary and prevents conflating agent domain identity (Persona) with active execution posture (Mode).
- Provides deterministic boundaries in conversation transcripts and Git history by mapping mode transitions and phase shifts directly to Threads.
- Allows conversational and analytical interactions without polluting production repository diffs with scratchpad noise.
- Prepares the harness for structured multi-modal workflows (e.g. Plan -> Approve -> Execute -> Review).

### Negative / Trade-offs
- Requires UI support to visualize active modes, persona badges, and mode-transition thread triggers.
- Frontend navigation and state resolution must track thread-specific active modes and preserve mode history across closed threads.

