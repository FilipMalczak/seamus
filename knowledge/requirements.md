# Requirements

Requirements, rationale, provenance, and stable IDs.

## Requirements Catalog

### REQ-001: Modern Python 3.12 Runtime & UV Package Management
- **Description**: The project must use Python 3.12 and `uv` for dependency and virtual environment management.
- **Rationale**: Ensures deterministic lockfiles, fast resolution, consistent environments across development, and modern language features.
- **Provenance**: [AGENTS.md](../AGENTS.md), [0001-project-initialization.md](../decisions/0001-project-initialization.md).
- **Linked Invariants**: [INV-001](./invariants.md#inv-001-uv-and-python-312-consistency), [INV-002](./invariants.md#inv-002-zero-tooling-check-failures).

### REQ-002: Rigorous Code Quality & Static Verification
- **Description**: All codebase modifications must be verified with `ruff` (linting and formatting), `mypy` (strict static typing), and `pytest`.
- **Rationale**: Prevents regression, guarantees type safety on public and internal boundaries, and enforces high code cleanliness.
- **Provenance**: [AGENTS.md](../AGENTS.md), [0001-project-initialization.md](../decisions/0001-project-initialization.md).
- **Linked Invariants**: [INV-002](./invariants.md#inv-002-zero-tooling-check-failures).

### REQ-003: Traceable Architectural & Durable Knowledge Documentation
- **Description**: Architectural decisions must be documented in `./decisions/` and durable implementation knowledge in `./knowledge/`, kept continuously synchronized with implementation changes.
- **Rationale**: Preserves long-term project memory, prevents architectural drift, and supports autonomous agent collaboration.
- **Provenance**: [AGENTS.md](../AGENTS.md), [0001-project-initialization.md](../decisions/0001-project-initialization.md).
- **Linked Invariants**: [INV-003](./invariants.md#inv-003-knowledge-synchronization).

### REQ-004: Config Template Singleton & Derivation
- **Description**: The harness must provide a singleton service-wide config template that may be partially complete. Creating an agent derives a copied config merged with agent overrides. Creating a session derives an isolated copy of the agent's config. Complete configuration is required to initialize a session's agent.
- **Rationale**: Decouples global defaults from individual agent and conversation instances while preventing configuration mutations across active sessions.
- **Provenance**: [0002-harness-server-mvp.md](../decisions/0002-harness-server-mvp.md).
- **Linked Invariants**: [INV-004](./invariants.md#inv-004-config-completeness-invariant).

### REQ-005: Hierarchical REST API with Dual Identifier Resolution
- **Description**: The server must expose a structured REST API under `/api/v-alpha/` for agents, sessions, and threads. Entities must support identification by UUID or slug name in all path parameters.
- **Rationale**: Enables human-readable URLs for clients while retaining globally unique machine-readable keys.
- **Provenance**: [0002-harness-server-mvp.md](../decisions/0002-harness-server-mvp.md).
- **Linked Invariants**: [INV-006](./invariants.md#inv-006-slug-format-and-scope-uniqueness).

### REQ-006: Thread Redirection, Event Streaming & Status Tracking
- **Description**: `GET .../thread` without a thread ID must issue an HTTP 307 redirect to the current open thread. `GET .../thread/<T>` must stream past AG-UI events (including user input messages and agent execution events) from history followed by live events over SSE. Execution status must be retrievable via `.../thread/<T>/status`.
- **Rationale**: Allows clients to easily bind to the active conversation context, recover full history on reload or thread switching, and display real-time execution state.
- **Provenance**: [0002-harness-server-mvp.md](../decisions/0002-harness-server-mvp.md), [0003-react-web-ui.md](../decisions/0003-react-web-ui.md).
- **Linked Invariants**: [INV-005](./invariants.md#inv-005-single-open-thread-invariant), [INV-012](./invariants.md#inv-012-user-message-event-recording--replay-invariant).

### REQ-007: Safe Non-Destructive API Surface
- **Description**: The API must not support HTTP DELETE methods on any resource. Resource updates must use HTTP POST with the full replacement object to support explicit clearing of values.
- **Rationale**: Eliminates catastrophic accidental data deletion at the API boundary and disambiguates partial updates from field deletions.
- **Provenance**: [0002-harness-server-mvp.md](../decisions/0002-harness-server-mvp.md).
- **Linked Invariants**: [INV-007](./invariants.md#inv-007-no-resource-deletion-invariant).

### REQ-008: Web UI with Navigation Tree, Real-Time Streaming & JSON Config Editor
- **Description**: The harness must provide a web user interface featuring:
  1. A hierarchical tree sidebar organizing Agents, Sessions, and Threads with operational status badges.
  2. A conversational workspace connecting to the SSE stream to display past messages, live streaming tokens, and tool calls.
  3. An in-browser modal for editing raw JSON configuration templates with format validation.
- **Rationale**: Provides developers and users with immediate visual control, conversational interaction, and simple configuration editing without requiring backend API tools.
- **Provenance**: [0003-react-web-ui.md](../decisions/0003-react-web-ui.md).
- **Linked Invariants**: [INV-008](./invariants.md#inv-008-ui-client-side-busy-guard).

### REQ-009: Default Session and Open Thread Automatic Creation, Zero-Prompt UX & Auto-Focus
- **Description**: Creating an entity (Agent, Session, Thread) must never prompt for a name during creation. Creating an agent immediately instantiates a default session (`name = None`), which instantiates an initial open thread (`name = None`). Creating an entity auto-selects down to the active open thread and automatically focuses the message composer input field. Entity names can be renamed later via explicit edit actions; non-empty names are displayed in the tree and breadcrumbs, falling back to full UUIDs when unset or empty.
- **Rationale**: Minimizes "time-to-typing-message" by eliminating modal prompt friction during creation while retaining optional renaming and unambiguous UUID identity.
- **Provenance**: [0003-react-web-ui.md](../decisions/0003-react-web-ui.md).
- **Linked Invariants**: [INV-009](./invariants.md#inv-009-default-session-and-open-thread-creation), [INV-010](./invariants.md#inv-010-entity-display-name-fallback).

### REQ-010: Containerized Launch Automation & Safe Service Restart
- **Description**: The repository must provide multi-container orchestration (`docker-compose.yml`) and an automated launch script (`run.sh`). Running `./run.sh` must ensure services are running and open the UI in the default browser. Running `./run.sh --restart` (`-r`) must rebuild container images and recreate running containers to apply latest code updates while strictly preserving persistent data volumes (avoiding data deletion).
- **Rationale**: Streamlines local execution and development iteration while ensuring service updates never inadvertently wipe stored data.
- **Provenance**: [0003-react-web-ui.md](../decisions/0003-react-web-ui.md).
- **Linked Invariants**: [INV-007](./invariants.md#inv-007-no-resource-deletion-invariant).

## Cross-References
- [invariants.md](./invariants.md)
- [0001-project-initialization.md](../decisions/0001-project-initialization.md)
- [0002-harness-server-mvp.md](../decisions/0002-harness-server-mvp.md)
- [0003-react-web-ui.md](../decisions/0003-react-web-ui.md)
