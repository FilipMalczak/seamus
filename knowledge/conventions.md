# Conventions

Project-specific implementation, tooling, and development conventions not fully enforced by tooling.

## Python Standards
- Python 3.12+ language features (e.g., standard generic type annotations, pattern matching where appropriate).
- Avoid suppression of linter (`# noqa`) or type-checker (`# type: ignore`) warnings without explicit, documented rationale.
- Line length: 100 characters (enforced by `ruff`).

## Git and Workflow Conventions
- Feature branches formatted as `NNNN-short-task-description` branched from `master`.
- Numbering checked against decisions and local/remote branches.
- Commits require explicit user instruction or authorization in approved plan.
- All production and `./knowledge/` modifications staged prior to review.

## Testing Conventions
- Pytest test files named `test_*.py` located under `tests/`.
- Test observable behaviors and edge cases rather than private implementation details.

## Cross-References
- [0001-project-initialization.md](../decisions/0001-project-initialization.md)
- [abstractions.md](./abstractions.md)
