# Conventions

Project-specific implementation, tooling, and development conventions not fully enforced by tooling.

## Python Standards
- Python 3.12+ language features (e.g., standard generic type annotations, pattern matching where appropriate).
- Avoid suppression of linter (`# noqa`) or type-checker (`# type: ignore`) warnings without explicit, documented rationale.
- Line length: 100 characters (enforced by `ruff`).

## REST API Conventions
- Base path prefix is `/api/v-alpha/`.
- Paths accept both UUID strings and slug names for identifiers `<A>`, `<S>`, and `<T>`.
- Slugs match `^[a-z0-9]+(?:-[a-z0-9]+)*$` and are unique within their parent scope.
- Updates are performed via `POST` sending the full updated object to the entity route (`POST .../config-template`, `POST .../agent/<A>`, `POST .../session/<S>`, `POST .../thread/<T>`). Passing `null` explicitly clears optional fields.
- No `DELETE` endpoints exist anywhere in the API.
- User chat input is dispatched via `POST .../session/<S>/input`. If the session agent is not in the `AWAITING_USER` state, return HTTP 409 Conflict.
- Session thread shortcut `GET .../session/<S>/thread` redirects with `307 Temporary Redirect` to the active open thread `.../thread/<T_open>`.
- Thread message streaming `GET .../thread/<T>` uses `text/event-stream` (SSE), first replaying past events from memory and then streaming live AG-UI events.

## Git and Workflow Conventions
- Feature branches formatted as `NNNN-short-task-description` branched from `master`.
- Numbering checked against decisions and local/remote branches.
- Commits require explicit user instruction or authorization in approved plan.
- All production and `./knowledge/` modifications staged prior to review.

## Testing Conventions
- Pytest test files named `test_*.py` located under `tests/`.
- Test observable behaviors and edge cases rather than private implementation details.
- Avoid external network calls during unit and integration test runs by using test doubles or mock run providers.

## Cross-References
- [0001-project-initialization.md](../decisions/0001-project-initialization.md)
- [0002-harness-server-mvp.md](../decisions/0002-harness-server-mvp.md)
- [abstractions.md](./abstractions.md)
- [invariants.md](./invariants.md)
