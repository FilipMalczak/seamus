# 0023. GitHub Actions Continuous Integration Pipeline

Date: 2026-11-02

## Status

Accepted

## Context

Prior to this decision, code quality, static type safety, frontend bundle compilation, and automated test suites for Seamus were executed solely via manual local developer invocation (`uv run ruff`, `uv run mypy`, `uv run pytest`, and `npm run build` in `ui/`). Without automated continuous integration, commits pushed to branches or pull requests risked undetected regressions, lint violations, type mismatches, or UI build breakages.

An automated CI workflow is needed to execute per commit on pushes and pull requests. Linux (`ubuntu-latest`) is the primary deployment target and must pass strictly, whereas macOS and Windows support is desirable for cross-platform visibility but optional/non-blocking. Package publishing and releases are not required at this stage. Furthermore, dual in-memory vs. dockerized test runner segmentation in CI (tracked in the backlog) is intentionally deferred to avoid premature harness complexity.

## Decision

1. **GitHub Actions Workflow (`.github/workflows/ci.yml`)**:
   - Establish a GitHub Actions workflow triggered on `push` and `pull_request` across all branches.
   - Configure concurrency cancellation (`cancel-in-progress: true`) grouped by workflow name and reference to terminate stale runs on rapid pushes.

2. **Job Topology**:
   - **`lint-and-typecheck` (Linux)**:
     - Runs on `ubuntu-latest`.
     - Utilizes `astral-sh/setup-uv@v5` with caching and Python 3.12.
     - Synchronizes dependencies strictly via `uv sync --frozen`.
     - Executes `uv run ruff format --check`, `uv run ruff check`, and `uv run mypy`.
   - **`frontend` (Linux)**:
     - Runs on `ubuntu-latest`.
     - Configures Node.js 22 with `actions/setup-node@v4` with caching based on `ui/package-lock.json`.
     - Runs `npm ci` followed by `npm run build` (invoking `tsc -b && vite build`) within the `ui/` directory.
   - **`test-docker` (Linux, Docker-Enabled)**:
     - Runs `pytest` on `ubuntu-latest` with Docker daemon active.
     - Automatically provisions the session-scoped ephemeral Gitea container fixture with SQLite, validating full Git persistence and Sync PR lifecycles.
   - **`test-in-memory` (Linux, In-Memory)**:
     - Runs `pytest` on `ubuntu-latest` in parallel with `SEAMUS_TEST_IN_MEMORY=true`.
     - Explicitly bypasses Docker daemon availability, validating pure unit and in-memory fallback behavior with sub-5-second test execution.

3. **Scope Boundaries**:
   - Publishing and deployment artifacts are omitted.
   - Cross-platform macOS and Windows runner support is tracked as technical debt in `backlog.md`.

## Consequences

### Positive
- Immediate, automated feedback on every commit across both Python backend and TypeScript React frontend.
- Strict enforcement of Ruff formatting, linting rules, and strict Mypy typing in CI.
- Cross-platform sanity checks on macOS and Windows without risking pipeline blocking.
- Fast dependency resolution and caching via `setup-uv` and `setup-node`.

### Negative / Trade-offs
- Multi-OS matrix increases GitHub Actions concurrency and minute consumption.
- Full containerized persistence tests only execute on runners with a live Docker daemon.

