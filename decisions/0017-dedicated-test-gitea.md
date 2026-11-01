# 0017. Ephemeral Dedicated Gitea Container for Test Suite Isolation

Date: 2026-11-01
Status: Accepted

## Context

In Decision [0008](./0008-git-persistence.md), Seamus established Gitea-backed Git repositories for agent and session persistence. Components such as `GitWorkspaceManager`, `HarnessStore`, and FastAPI server endpoints interact with Gitea to provision repositories, create branches, and manage pull requests.

Previously, `PersistenceSettings` defaulted to `http://localhost:3001` with `SEAMUS_PERSISTENCE_ENABLED=True` and a default workspace path of `.seamus/workspaces`. When developers ran tests (`uv run pytest`) while their local development stack (`docker-compose.yml`) was active, tests creating agents or sessions directly called the live development Gitea instance on port 3001. This polluted the developer's Gitea environment with leftover repositories (`agent-<uuid>`), branches, and pull requests. Furthermore, running multiple test suites in parallel risked port or repository collisions.

## Decision

1. **Ephemeral Gitea Container with Dynamic Port and SQLite (`tests/conftest.py`)**:
   - For test sessions running in an environment with Docker available, spin up a dedicated, ephemeral Gitea container (`gitea/gitea:latest`) with `--rm`.
   - Use SQLite embedded database (`GITEA__database__DB_TYPE=sqlite3`) without requiring external PostgreSQL or external database infrastructure.
   - Bind to dynamic host port `127.0.0.1::3000` (`docker run -p 127.0.0.1::3000`), letting Docker allocate an unassigned high port. This ensures full concurrency and port-conflict elimination when running multiple test suites in parallel.
   - Automatically initialize the standard `seamus` service admin user via `docker exec`.
   - On pytest session teardown, execute `docker rm -f <container_name>`, completely purging the container and all created repositories.

2. **Test Persistence Environment Scoping**:
   - In `tests/conftest.py`, configure session-level environment variables pointing to the ephemeral container:
     - `GITEA_URL=http://127.0.0.1:<dynamic_port>`
     - `GITEA_EXTERNAL_URL=http://127.0.0.1:<dynamic_port>`
     - `SEAMUS_WORKSPACE_DIR=<tmp_path_factory.mktemp('test_workspaces')>`
     - `SEAMUS_PERSISTENCE_ENABLED=true`
   - Reset `get_persistence_settings` cache and workspace manager singletons before tests run.

3. **Workspace Manager Singleton Reset Support (`seamus.persistence`)**:
   - Introduce `reset_workspace_manager(manager: GitWorkspaceManager | None = None)` in `src/seamus/persistence/workspace.py` and export in `src/seamus/persistence/__init__.py`, aligning with existing singleton reset conventions (`reset_harness_store`, `reset_config_template_store`, `reset_runner_registry`).
   - Automatically reset the workspace manager between tests via an autouse fixture.

4. **Graceful Fallback When Docker Is Unavailable**:
   - If Docker is not available in the test execution environment, issue a test warning and set `SEAMUS_PERSISTENCE_ENABLED=false` to allow purely in-memory unit tests to execute without network connection attempts.

## Consequences

- The developer's live Gitea instance on port 3001 and local `.seamus/workspaces` directories are completely shielded from test pollution.
- Test suites can run in parallel without port conflicts or cross-test data pollution.
- Ephemeral test containers and all generated repositories are fully destroyed upon test session completion.
- When configuring future CI/CD pipelines (e.g. GitHub Actions), two distinct test runner jobs should be defined:
  1. A Docker-enabled runner job executing the full test suite with the ephemeral Gitea container.
  2. A fast in-memory runner job executing pure unit tests.

## Cross-References

- [0008-git-persistence.md](./0008-git-persistence.md)
- [0012-sync-prs-and-thread-accept.md](./0012-sync-prs-and-thread-accept.md)
- [0016-sync-pr-data-scope.md](./0016-sync-pr-data-scope.md)
- [../knowledge/invariants.md](../knowledge/invariants.md)
- [../knowledge/conventions.md](../knowledge/conventions.md)
- [../knowledge/backlog.md](../knowledge/backlog.md)

