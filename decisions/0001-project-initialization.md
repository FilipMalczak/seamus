# 0001. Project Initialization and Scaffolding

Date: 2026-10-28
Status: Accepted

## Context

The Seamus project aims to build a deep agent harness that is fully owned and customizable. To begin development with strong engineering hygiene, the project requires a baseline setup covering package layout, dependency management, code quality tooling, testing infrastructure, and documentation practices.

## Decision

1. **Python Version and Runtime**: Standardize on Python 3.12.
2. **Environment and Package Manager**: Use `uv` exclusively for dependency resolution, virtual environment management (`.venv`), and script execution (`uv run`).
3. **Project Layout**: Adopt the standard `src/` layout with `src/seamus` and PEP 561 marker `py.typed`. Tests live under `tests/`.
4. **Code Quality and Tooling**:
   - `ruff` for linting and code formatting.
   - `mypy` in strict mode for static type checking.
   - `pytest` for unit and functional testing.
5. **Knowledge and Architecture Records**:
   - Maintain append-only architectural decision records in `./decisions/`.
   - Maintain durable implementation knowledge in `./knowledge/` across `vocabulary.md`, `requirements.md`, `invariants.md`, `architecture.md`, `abstractions.md`, and `conventions.md`.

## Consequences

- All developers and agents must use `uv run` to execute tools.
- CI/verification checks (`ruff`, `mypy`, `pytest`) must pass cleanly before any task can be considered complete.
- Architecture and requirements are consistently documented and cross-linked across `./knowledge/` and `./decisions/`.
