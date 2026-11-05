# Modes and Personas Breakdown

Detailed specification and comparative analysis of Seamus operational modes, phases, and personas. While [threads_modes_personas.md](./threads_modes_personas.md) defines how these concepts interact across hierarchy boundaries and state lifecycles, this document details how each mode, phase, and persona is customized against the others: what behavioral posture it establishes, what prompt framing and instructions are injected, what tools are provisioned or walled off, and what filesystem mounting rules apply.

---

## 1. Dimensional Overview

Seamus structures agent configuration and execution along two distinct axes:

1. **Persona Axis (Agent-Level Identity)**: Defines *who* the agent is—its enduring identity, domain background, heuristics, default toolset, and communication tone.
2. **Operational Mode Axis (Thread/Turn-Level Posture)**: Defines *how* the agent behaves right now—its immediate goal, prompt framing, tool gating, workspace mutability, and conversational cadence.

Certain modes are multi-phased state machines (e.g., `plan` mode progresses through `discuss` $\to$ `make` $\to$ `execute`), where each phase applies specialized customizations while sharing the overarching mode lifecycle.

---

## 2. Operational Modes & Phases Breakdown

### 2.1 `chat` Mode
- **Primary Objective**: Free-form conversational dialogue, architectural brainstorming, answering technical questions, and exploring ideas without modifying repository deliverables.
- **Behavioral Posture**: Helpful, consultative, and communicative. The agent focuses on explaining concepts, discussing tradeoffs, and collaborating on requirements. It does not perform autonomous codebase modifications.
- **Prompt Framing & Injected Instructions**:
  - Injects instructions that position the agent as an advisory collaborator.
  - Guides the agent to ask clarifying questions when requirements are ambiguous.
  - Emphasizes that conversational suggestions are exploratory and that workspace changes are not deliverables destined for the production `main` branch.
- **Tool Availability**:
  - **Enabled**: Structured human interaction via `ask` (questionnaires) and `read_artifact_submission`. Read-only inquiry and general reasoning tools.
  - **Walled Off**: Plan-management tools (`plan`, `make_plan`, `update_plan`, `edit_plan`, `discard`). Production code delivery tools are deactivated or discouraged.
- **Filesystem & Mount Policy**:
  - Workspace `/workspace` is mounted read-write as an agent scratchpad for transient scripts or scratch calculations. Changes in `chat` mode are not intended for synchronization PRs.
- **Artifacts & Surfaces**:
  - Supports blocking human questionnaires created via `ask` rendered in the conversation stream.

---

### 2.2 `plan` Mode
A structured, multi-phase operational mode designed to prevent premature or unverified code modifications by enforcing a phased ritual: explore requirements, draft an actionable plan, gather user approval, and execute the verified plan.

All three phases share a single session-local plan artifact (`cadence="nonblocking"`, `exposition="tabbed"`) displayed in a dedicated UI tab alongside Changes.

```mermaid
flowchart LR
    Discuss["Discuss Phase<br/>(plan/discuss)<br/>Explore & Note"] -->|plan()| Make["Make Phase<br/>(plan/make)<br/>Draft Plan"]
    Make -->|"Proceed" (User)| Execute["Execute Phase<br/>(plan/execute)<br/>Implement & Test"]
    Discuss -->|discard()| Discuss
    Make -->|discard()| Discuss
    Execute -->|discard()| Discuss
```

#### Phase 1: `discuss` (`plan/discuss`)
- **Primary Objective**: Explore the existing codebase, understand the problem, ask clarifying questions, and document findings and decisions before drafting a plan.
- **Behavioral Posture**: Exploratory, investigative, and inquisitive. Code modification is strictly forbidden.
- **Prompt Framing & Injected Instructions**:
  - Explicitly informs the agent that code execution and codebase modification are prohibited during this phase.
  - Instructs the agent to inspect files, trace references, and read documentation using read-only search commands.
  - Directs the agent to formulate clarifying questions using `ask` (or conversational dialogue) whenever ambiguities exist.
  - Instructs the agent to record notes, architectural discoveries, and requirements in `/workspace/notes/`.
  - Prompts the agent to call `plan()` once all necessary context has been collected to advance to the plan-drafting phase.
- **Tool Availability**:
  - **Enabled**: `ask`, `read_artifact_submission`, `plan()` (transitions session to `plan/make`), `discard()` (resets planning state). Codebase inspection tools (`read_file`, `glob`, `grep`, `ls`).
  - **Walled Off**: Plan authoring tools (`make_plan`, `update_plan`, `edit_plan`). Code modification tools (`write_file`, `edit_file`, destructive shell commands).
- **Filesystem & Mount Policy**:
  - `/workspace` (`data/`): Mounted strictly **read-only** (`readOnly=True`). Code cannot be touched.
  - `/workspace/notes` (`data/notes/`): Mounted **read-write** (`readOnly=False`) as an overlay so notes, findings, and requirements persist, show up in Changes tab diffs, and survive subsequent phase transitions.
- **Artifacts & Surfaces**:
  - Blocking questionnaires via `ask` for structured multiple-choice requirement gathering.

#### Phase 2: `make` (`plan/make`)
- **Primary Objective**: Synthesize collected requirements into a complete, structured Markdown plan document for user review.
- **Behavioral Posture**: Methodical, drafting-focused, and plan-centric. The agent concentrates on formulating actionable steps, architecture decisions, and verification criteria.
- **Prompt Framing & Injected Instructions**:
  - Instructs the agent to author or refine the session's plan document using the specialized plan tools.
  - Injects the formal Plan Document Specification, defining required plan sections (user intent, architecture and scope, step-by-step implementation tasks, testing/verification steps, and rollback safeguards).
  - Injects active plan context if a draft already exists, instructing the agent to apply surgical updates or text replacements.
  - Prohibits switching into code implementation or conversational chatter until the plan is approved.
- **Tool Availability**:
  - **Enabled**: `make_plan(title, content)` (initial creation; once called, `make_plan` disappears and `update_plan` appears), `update_plan(content)` (replaces full Markdown content), `edit_plan(old_str, new_str)` (surgical text replacement), `discard()`. Read-only file inspection tools.
  - **Walled Off**: `plan()`, `ask`, and all file writing/editing tools.
- **Filesystem & Mount Policy**:
  - `/workspace`: Mounted **read-only**.
  - `/workspace/notes`: Mounted **read-only** (notes are finalized reference material).
- **Artifacts & Surfaces**:
  - A2UI non-blocking tabbed plan surface rendered in a dedicated tab to the right of Changes, displaying formatted Markdown and an interactive "Proceed" action button.

#### Phase 3: `execute` (`plan/execute`)
- **Primary Objective**: Faithfully execute, test, and verify the user-approved plan.
- **Behavioral Posture**: Action-oriented, disciplined, and rigorous. The agent works systematically through the plan tasks.
- **Prompt Framing & Injected Instructions**:
  - Injects the complete approved plan content directly into the dynamic system prompt as operational context.
  - Instructs the agent to implement each plan step in order, author surgical diffs, run verification tests, and resolve failures.
  - Reminds the agent to adhere to testing invariants and repository conventions before completing execution.
- **Tool Availability**:
  - **Enabled**: Full software engineering suite (`read_file`, `write_file`, `edit_file`, shell `execute`, inspector, todo-tracking). `discard()` remains enabled if the user explicitly orders aborting the plan.
  - **Walled Off**: Plan authoring tools (`make_plan`, `update_plan`, `edit_plan`, `plan()`) and `ask`.
- **Filesystem & Mount Policy**:
  - `/workspace`: Mounted **read-write** (`readOnly=False`). Surgical code modifications and test executions are fully enabled.
  - `/workspace/notes`: Mounted **read-only** (historical reference for the plan).
- **Artifacts & Surfaces**:
  - The plan tab remains accessible as an ongoing reference throughout execution until the thread is accepted or the session is reset.

---

### 2.3 `act` Mode (Planned)
- **Primary Objective**: Direct, prompt task execution without multi-phase planning rituals.
- **Behavioral Posture**: Direct, efficient, and surgical. Optimized for quick bug fixes, small self-contained additions, or tasks where requirements are already crystal-clear.
- **Prompt Framing & Injected Instructions**:
  - Emphasizes immediate execution, targeted diffs, and verification without prolonged conversational preliminaries.
  - Injects testing discipline and repository conventions.
- **Tool Availability**:
  - **Enabled**: Full software engineering tool suite (`read_file`, `write_file`, `edit_file`, `execute`).
  - **Walled Off**: Phased planning tools (`plan`, `make_plan`, `update_plan`, `edit_plan`) and questionnaires (`ask`).
- **Filesystem & Mount Policy**:
  - `/workspace`: Mounted **read-write** for production code changes targeting the session's Sync PR.

---

### 2.4 `analyse` Mode (Planned)
- **Primary Objective**: In-depth codebase investigation, architecture review, security auditing, performance profiling, and call-graph tracing without making changes.
- **Behavioral Posture**: Analytical, diagnostic, and thorough. Explains root causes, cites precise file paths and line ranges, and outlines architectural relationships.
- **Prompt Framing & Injected Instructions**:
  - Informs the agent that its sole role is analysis, code review, or auditing.
  - Explicitly forbids proposing or writing file modifications.
  - Guides the agent to perform comprehensive exploration using search, symbols, and diagnostics before answering.
- **Tool Availability**:
  - **Enabled**: File reading, search (`grep`, `glob`, `ls`), code review graph queries, symbol navigation.
  - **Walled Off**: All mutation tools (`write_file`, `edit_file`, modifying shell commands, planning tools).
- **Filesystem & Mount Policy**:
  - `/workspace`: Mounted strictly **read-only**.

---

### 2.5 `routing` Mode (Planned)
- **Primary Objective**: Automated intent triage and mode dispatch for incoming user prompts.
- **Behavioral Posture**: Fast, classification-focused classifier.
- **Prompt Framing & Injected Instructions**:
  - Specialized classification instructions instructing the model to categorize the user's intent into `plan`, `act`, `chat`, or `analyse`.
- **Tool Availability**:
  - **Enabled**: Internal dispatch tool or structured output schema.
  - **Walled Off**: All filesystem, shell, and conversational tools.
- **Filesystem & Mount Policy**:
  - No workspace mount required.

---

## 3. Personas Breakdown

A **Persona** represents an agent's enduring identity, operational philosophy, domain heuristics, and baseline tool capabilities. While near-term development focuses on the **Coder** persona for Seamus self-development, the architecture supports arbitrary domain personas.

### 3.1 `coder` Persona (Core / Primary Dogfooding Focus)
- **Domain Specialization**: Autonomous software engineering, system architecture, test-driven development, and debugging.
- **Identity & Tone**: Rigorous, pragmatic, precise, and concise. Speaks in terms of code, interfaces, invariants, and test results.
- **Injected Persona Instructions**:
  - Injects `<engineering_discipline>`: requires test-driven verification, running linters and type checkers, authoring surgical diffs, avoiding unrelated code modifications or speculative abstractions, and preserving existing comments and docstrings.
  - Enforces repository invariants: Python 3.12, `uv`, `ruff`, `mypy`, `pytest`, document-relative Markdown links, and append-only decision logs.
  - Directs the agent to produce actionable code changes backed by automated tests rather than speculative advice.
- **Baseline Tool Suite**:
  - In-sandbox filesystem manipulation (`read_file`, `write_file`, `edit_file`, `glob`, `grep`, `ls`), terminal command runner (`execute`), todo-list tracking (`write_todos`), and codebase search.
- **Interaction with Modes**:
  - In `plan` mode: Focuses on component dependencies, interface contracts, error handling, and test plans.
  - In `execute` and `act` modes: Focuses on clean implementation, running test suites, and resolving static analysis errors.

---

### 3.2 `office_worker` Persona (Specialized / Example)
- **Domain Specialization**: Administrative coordination, project scheduling, task decomposition, document synthesis, and stakeholder communication.
- **Identity & Tone**: Organized, diplomatic, proactive, and clear. Avoids technical software jargon; communicates with bulleted summaries, action items, and deadlines.
- **Injected Persona Instructions**:
  - Emphasizes structured organization: breaking large initiatives into actionable milestones with owners and dates.
  - Guides the agent to draft clear executive summaries, identify blockers, and structure correspondence.
- **Baseline Tool Suite**:
  - Document parsers, spreadsheets/tables, task management (`write_todos`), calendar/email integrations, search tools.
- **Interaction with Modes**:
  - In `plan` mode: Structures project roadmaps, resource allocations, and risk matrices.
  - In `chat` mode: Drafts memos, clarifies action items, and coordinates schedules.

---

### 3.3 `designer` Persona (Specialized / Example)
- **Domain Specialization**: UI/UX design, design systems, visual hierarchy, user ergonomics, accessibility, and interactive aesthetics.
- **Identity & Tone**: Visual, user-centric, empathetic, and aesthetic. Evaluates systems through usability, accessibility, spacing, and rhythm.
- **Injected Persona Instructions**:
  - Emphasizes design system consistency: color palettes, typography scales, spacing tokens, responsive layouts, and WCAG contrast compliance.
  - Guides the agent to critique user flows and propose ergonomics improvements.
- **Baseline Tool Suite**:
  - Frontend stylesheet and component editors (CSS, Tailwind, React/HTML), SVG/canvas generators, visual artifact inspectors.
- **Interaction with Modes**:
  - In `plan` mode: Outlines wireframes, component hierarchies, and interactive states.
  - In `execute` mode: Fine-tunes CSS styling, transitions, and layout proportions.

---

### 3.4 `data_scientist` Persona (Specialized / Example)
- **Domain Specialization**: Exploratory data analysis, statistical modeling, machine learning, and reproducible data pipelines.
- **Identity & Tone**: Empirical, hypothesis-driven, statistical, and rigorous. Evaluates problems through distributions, baselines, metrics, and confidence intervals.
- **Injected Persona Instructions**:
  - Injects data discipline: verifying data hygiene, checking distributions, establishing baselines before modeling, and ensuring pipeline reproducibility.
  - Guides the agent to generate data visualizations and explain statistical confidence.
- **Baseline Tool Suite**:
  - Python data analysis execution environment, dataset inspectors (Pandas, Polars, DuckDB, SQL), charting/plotting libraries, artifact report generators.
- **Interaction with Modes**:
  - In `plan` mode: Designs experimental methodologies, evaluation metrics, and feature pipelines.
  - In `analyse` mode: Diagnoses model bias, data drift, and performance anomalies.

---

## 4. Customization Matrix

| Mode / Phase | Persona Customization | `/workspace` Mount | `/workspace/notes` Mount | Enabled Special Tools | Gated / Walled Tools | Primary Surface |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **`chat`** | General advisor / brainstorming | Read-Write (scratchpad) | N/A | `ask`, `read_artifact_submission` | `plan`, `make_plan`, `update_plan`, `edit_plan`, `discard` | Conversation stream |
| **`plan/discuss`** | Exploratory investigator | **Read-Only** | **Read-Write** | `ask`, `read_artifact_submission`, `plan()`, `discard()` | `make_plan`, `update_plan`, `edit_plan`, `write_file`, `edit_file` | Stream + Notes |
| **`plan/make`** | Methodical plan author | **Read-Only** | **Read-Only** | `make_plan`, `update_plan`, `edit_plan`, `discard()` | `plan()`, `ask`, `write_file`, `edit_file` | A2UI Tabbed Plan |
| **`plan/execute`** | Disciplined implementer | **Read-Write** | **Read-Only** | `discard()`, full engineering suite | `plan()`, `make_plan`, `update_plan`, `edit_plan`, `ask` | A2UI Tabbed Plan + Changes Diff |
| **`act`** *(planned)* | Direct, prompt implementer | **Read-Write** | N/A | Full engineering suite | `plan`, `make_plan`, `update_plan`, `edit_plan`, `ask` | Changes Diff |
| **`analyse`** *(planned)* | Diagnostic auditor / reviewer | **Read-Only** | N/A | Search, call graphs, inspection | All mutation tools (`write_file`, `edit_file`, shell writes) | Diagnostic Report |
| **`routing`** *(planned)* | Intent classifier | None | N/A | Intent dispatch tool | All workspace and file tools | Internal Dispatch |

---

## 5. Cross-References

- [threads_modes_personas.md](./threads_modes_personas.md)
- [architecture.md](./architecture.md)
- [abstractions.md](./abstractions.md)
- [invariants.md](./invariants.md)
- [requirements.md](./requirements.md)
- [vocabulary.md](./vocabulary.md)
- [0019-threads-modes-personas-architecture.md](../decisions/0019-threads-modes-personas-architecture.md)
- [0030-operational-modes-and-plan-mode.md](../decisions/0030-operational-modes-and-plan-mode.md)

