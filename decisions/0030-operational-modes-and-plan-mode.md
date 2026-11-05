# 0030: Operational Modes, Multi-Phase Plan Mode, and Tabbed Non-Blocking Artifacts

- **Date**: 2026-11-05
- **Status**: Accepted
- **Supersedes**: None

## Context

In [0019-threads-modes-personas-architecture.md](./0019-threads-modes-personas-architecture.md), we established the architectural triad of **Persona** (Agent), **Workspace** (Session), and **Operational Mode** (Thread). Up until now, all threads operated implicitly in a single default posture.

We now want to formalize **Operational Modes** as first-class domain and runtime constructs, naming our existing conversational/coding posture **Chat** mode (`chat`) and introducing **Plan** mode (`plan`) as a three-phase workflow (**Discuss** -> **Make** -> **Execute**).

Each mode and phase governs:
1. **Name and Short Description**: For UI presentation (`<mode>` or `<mode>/<phase>` thread labels) and future routing/dispatch.
2. **System Prompt Composition**: Structured LM-XML sections (`<operational_mode>`, `<plan_document_specification>`, `<active_plan_context>`) injected into `SystemPromptDocument` and serialized via `lmxml` without raw string concatenation.
3. **Dynamic Tool Availability**: Exposing only the tools appropriate to the active mode, phase, and session plan state, with `read_artifact_submission` exposed if and only if at least one artifact-producing tool (`ask`, `form`, `make_plan`, `update_plan`, `edit_plan`) is available.
4. **Filesystem Mount Policies**: Read-write vs. read-only access to the operational workspace (`/workspace`) and persistent session notes directory (`/workspace/notes`).
5. **Thread-per-Phase Boundaries**: Every mode switch and phase transition closes the current thread and spawns a new thread with a clean checkpoint history, using `/workspace/notes` and `/artifacts` for cross-phase state handoff.

## Decisions

### 1. Mode and Phase Descriptors (`seamus.domain.modes`)
- **`ModeDescriptor` and `PhaseDescriptor`**: Declarative descriptors specifying `name`, `description`, `mount_policy` (`MountPolicy`), and `tools`.
- **`chat` Mode**: Single-phase mode where `/workspace` (`<session_workspace>/data/`) is mounted `RW` and notes is an unconstrained directory. Exposes `ask` (and consequently `read_artifact_submission`).
- **`plan` Mode**: Multi-phase mode comprising three sequential phases, each executing in its own dedicated thread:
  1. **`discuss` (`plan/discuss`)**:
     - **Mounts**: `/workspace` = `RO`, `/workspace/notes` = `RW`.
     - **Tools**: `ask` (embedded + blocking questionnaire), `form` (tabbed + non-blocking questionnaire), `read_artifact_submission`, `plan()`, and `discard()`.
     - **Behavior**: The agent explores `/workspace` in read-only mode, clarifies ambiguities with the user (via `ask`, `form`, or conversational prose), and records durable notes/requirements in `/workspace/notes`. Calling `plan()` closes the `discuss` thread, opens a new `plan/make` thread, and automatically wakes the agent.
  2. **`make` (`plan/make`)**:
     - **Mounts**: `/workspace` = `RO`, `/workspace/notes` = `RO`.
     - **Tools**: Initially exposes `make_plan(content: str, name: str = "Plan")`. Once a plan is created for the session (`session.active_plan_id`), `make_plan` disappears and `update_plan(content: str)` + `edit_plan(old_string: str, new_string: str)` appear; plus `read_artifact_submission` and `discard()`.
     - **Behavior**: Synthesizes `/workspace/notes` and `/workspace` findings into a comprehensive Markdown implementation plan artifact (`exposition="tabbed"`, `cadence="nonblocking"`). There is no agent tool to advance to `execute`; instead, the user reviews the rendered Markdown plan in its dedicated tab and clicks the **Proceed** button, which closes the `make` thread, opens a new `plan/execute` thread, and automatically wakes the agent.
  3. **`execute` (`plan/execute`)**:
     - **Mounts**: `/workspace` = `RW`, `/workspace/notes` = `RO`.
     - **Tools**: Standard workspace coding/shell tools plus `discard()` (no inquiry or plan-authoring tools, and therefore no `read_artifact_submission`).
     - **Behavior**: Reads the approved plan artifact under `/artifacts/plans/<active_plan_id>/` and `/workspace/notes`, and implements and verifies the changes in `/workspace`.
- **`discard()` Tool**: Available across all three `plan` phases (`discuss`, `make`, `execute`). Must only be invoked on explicit user command. When called, it closes/discards any active session plan (`deleteSurface.json`), clears `session.active_plan_id`, closes the current thread, and opens a fresh thread back in `plan/discuss` awaiting user input.

### 2. Persistent Session Notes (`/workspace/notes`) and Sandbox Mount Reconfiguration
- Each session workspace on `session/{session_id}` initializes a Git-tracked `data/notes/` directory inside `data/` (`/workspace/notes`), making all notes changes directly visible in the Changes tab and diff viewer.
- In `plan/discuss`, `/workspace` is mounted `RO` while `/workspace/notes` is mounted `RW` on top of it, ensuring the codebase cannot be accidentally mutated while requirements are recorded.
- `SeamusOpenSandboxBackend.reconfigure_mounts(...)` compares the desired `(workspace_readonly, notes_mounted, notes_readonly)` policy against the active container's mounts on every mode/phase transition and recreates the container if the mount policy changes.

### 3. Tabbed and Non-Blocking Artifacts (`forms` and `plans`)
- **`forms`**: Share the A2UI schema of `questionnaires` (`QuestionnaireBuilder`) with default class manifest `exposition="tabbed", cadence="nonblocking"`. Batched during a turn via the `form` tool.
- **`plans`**: Managed by `PlanBuilder` under `/artifacts/plans/<plan_id>/` with default class manifest `exposition="tabbed", cadence="nonblocking"` and instance `manifest.json` storing `title` (from `make_plan(..., name="Plan")`). Rendered in A2UI v0.9 as a Markdown `Text` body component (`MarkdownComponentContext` bridged to `MarkdownRenderer`) followed by a primary `Button` (`action: proceed_plan`) labeled **Proceed**.
- **Non-Blocking to Blocking Promotion**: Calling `read_artifact_submission(artifact_id)` on an open non-blocking artifact promotes its instance `manifest.json` to `cadence="blocking"` and halts the turn so the UI blocks further chat input until the user submits the artifact.
- **Accepting Sync PR in `plan/execute`**: Accepting a thread in `HarnessStore.accept_thread` first closes any active session plan (`PlanBuilder.close_plan`, emitting `ARTIFACT_CLOSED`), merges the Sync PR (`data/` only) into `main`, and opens the next thread (resetting `plan` mode back to `plan/discuss`).

### 4. LM-XML System Prompt Composition (`seamus.harness.prompt`)
- Inspired by structured mode/phase prompt separation in Antigravity, Claude Code, and Cursor (`coder` persona), `SystemPromptDocument` injects typed Pydantic models:
  - `OperationalModeSection` (`<operational_mode>`) with mode/phase descriptions, mount summary, and phase workflow rules.
  - `PlanDocumentSpec` (`<plan_document_specification>`) in `plan/make`, instructing the agent to structure plans with `# <Title>`, `## Goal & Context`, `## Architectural Decisions & Trade-offs`, `## Proposed Changes`, and `## Verification Plan`.
  - `ActivePlanPromptContext` (`<active_plan_context>`) when `session.active_plan_id` is set.
- `DynamicSystemPromptMiddleware` dynamically filters `request.tools` per turn via `tools_provider` and injects synthetic auto-wake trigger prompts on phase transitions via `messages_provider`.

### 5. Web UI Integration (`ui/src/`)
- **Sidebar Thread Mode Labels**: Each thread item in the navigation tree displays a left-aligned layout (`<icon><label><ID or name>`) with a mode badge showing `<mode>` (`chat`) or `<mode>/<phase>` (`plan/discuss`, `plan/make`, `plan/execute`).
- **Empty Thread Reuse**: When switching modes or creating a thread on an empty thread (`thread.is_empty`), the existing empty thread is updated in place rather than creating an extra orphaned thread (particularly when switching newly created agents from `chat` to `plan`).
- **Mode Switcher**: `ChatArea` provides a `Chat` | `Plan` mode selector in the top bar (calling `POST /api/v-alpha/agent/{agent}/session/{session}/mode`) and displays the active thread's mode/phase badge.
- **Tabbed Artifacts**: Open artifacts with `exposition="tabbed"` (`plans`, `forms`) render as tabs to the right of `Changes` in `.main-panel-tabs` using their `title` (defaulting to `Plan` or `Form`). When closed or discarded (`deleteSurface.json` / `ARTIFACT_CLOSED`), the tab automatically disappears.

## Consequences

- **Benefits**: Cleanly separates requirement discovery (`plan/discuss`), specification authoring (`plan/make`), and code mutation (`plan/execute`) into isolated thread checkpoints with hardware-enforced container mount permissions (`RO` vs `RW`).
- **Follow-ups**:
  - Richer plan presentation (including inline section commenting) is recorded as **Deferred** in `./knowledge/backlog.md`.
  - Rethinking safe session branching across session-local non-blocking artifacts (`plan`) and future multi-repository Git mounts is recorded under **Technical debt** in `./knowledge/backlog.md`.

## Cross-References
- [0018-dynamic-system-prompt-architecture.md](./0018-dynamic-system-prompt-architecture.md)
- [0019-threads-modes-personas-architecture.md](./0019-threads-modes-personas-architecture.md)
- [0029-a2ui-questionnaire-artifacts.md](./0029-a2ui-questionnaire-artifacts.md)
- [threads_modes_personas.md](../knowledge/threads_modes_personas.md)
- [vocabulary.md](../knowledge/vocabulary.md)
- [architecture.md](../knowledge/architecture.md)
- [abstractions.md](../knowledge/abstractions.md)
- [requirements.md](../knowledge/requirements.md)
- [invariants.md](../knowledge/invariants.md)
- [backlog.md](../knowledge/backlog.md)

