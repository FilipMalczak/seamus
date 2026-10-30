# Invariants

Properties and rules that must always hold across the repository.

## Invariant Catalog

### INV-001: UV and Python 3.12 Consistency
- **Statement**: `pyproject.toml` and `uv.lock` must remain synchronized at all times. Python version requirement must be `>=3.12`.
- **Justification**: [REQ-001](./requirements.md#req-001-modern-python-312-runtime--uv-package-management), [0001-project-initialization.md](../decisions/0001-project-initialization.md).
- **Enforcement**: CI and pre-completion commands `uv run ...` and lockfile checks.

### INV-002: Zero Tooling Check Failures
- **Statement**: No task may finish or be submitted for review while any of `pytest`, `ruff check`, `ruff format --check`, or `mypy` fail.
- **Justification**: [REQ-002](./requirements.md#req-002-rigorous-code-quality--static-verification), [AGENTS.md](../AGENTS.md).
- **Enforcement**: Running full test, lint, format, and typecheck commands prior to marking task complete.

### INV-003: Knowledge Synchronization
- **Statement**: Every structural, architectural, or invariant change must be reflected in `./knowledge/` and `./decisions/` in the same branch before completion.
- **Justification**: [REQ-003](./requirements.md#req-003-traceable-architectural--durable-knowledge-documentation), [AGENTS.md](../AGENTS.md).
- **Enforcement**: Checklist in `AGENTS.md` and repository review workflow.

### INV-004: Config Completeness Invariant
- **Statement**: An Agent or Session configuration must contain a valid inference format, non-empty base URL, model name, and valid API key before a session's DeepAgent can be initialized or execute.
- **Justification**: [REQ-004](./requirements.md#req-004-config-template-singleton--derivation), [0002-harness-server-mvp.md](../decisions/0002-harness-server-mvp.md).
- **Enforcement**: Domain model validation in `AgentConfig.validate_complete()` and pre-initialization checks in session runner.

### INV-005: Single Open Thread Invariant
- **Statement**: Within any Session, exactly one thread—the most recently created one—is open (`is_open = True`). All previous threads must be closed (`is_open = False`).
- **Justification**: [REQ-006](./requirements.md#req-006-thread-redirection-event-streaming--status-tracking), [0002-harness-server-mvp.md](../decisions/0002-harness-server-mvp.md).
- **Enforcement**: Session thread management methods in `Session.create_thread()`.

### INV-006: Slug Format and Scope Uniqueness
- **Statement**: Any non-null entity name must be a slug matching `^[a-z0-9]+(?:-[a-z0-9]+)*$` and must be unique within its parent scope (agents globally, sessions per agent, threads per session).
- **Justification**: [REQ-005](./requirements.md#req-005-hierarchical-rest-api-with-dual-identifier-resolution), [0002-harness-server-mvp.md](../decisions/0002-harness-server-mvp.md).
- **Enforcement**: Slug validation in domain entities and scope check in the repository store.

### INV-007: No Resource Deletion Invariant
- **Statement**: The API surface must contain zero HTTP DELETE routes. Resources created in the harness cannot be removed via API calls.
- **Justification**: [REQ-007](./requirements.md#req-007-safe-non-destructive-api-surface), [0002-harness-server-mvp.md](../decisions/0002-harness-server-mvp.md).
- **Enforcement**: Server router definitions and automated route inspection in API test suite.

### INV-008: UI Client-Side Busy Guard
- **Statement**: The web UI must disable message submission and display active status when a thread's status is not `AWAITING_USER` or when a thread is marked closed (`is_open = False`), preventing unnecessary 409 Conflict round-trips.
- **Justification**: [REQ-008](./requirements.md#req-008-web-ui-with-navigation-tree-real-time-streaming--json-config-editor), [0003-react-web-ui.md](../decisions/0003-react-web-ui.md).
- **Enforcement**: Composer input validation and disabled state bindings in `ChatArea.tsx`.

## Cross-References
- [requirements.md](./requirements.md)
- [0001-project-initialization.md](../decisions/0001-project-initialization.md)
- [0002-harness-server-mvp.md](../decisions/0002-harness-server-mvp.md)
- [0003-react-web-ui.md](../decisions/0003-react-web-ui.md)
