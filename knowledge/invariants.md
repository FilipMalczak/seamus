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

## Cross-References
- [requirements.md](./requirements.md)
- [0001-project-initialization.md](../decisions/0001-project-initialization.md)
