# 0057: Deterministic End-to-End Test Suite with Steerable LLM and Stub Sandbox

- **Status**: Accepted
- **Date**: 2026-11-13
- **Branch**: `0057-e2e-test-suite`
- **Supersedes**: None

## Context

The repository's test suite was composed almost entirely of unit and route-level tests. Each
module was exercised in isolation with hand-built fixtures, and the only multi-component
coverage lived in `tests/test_session_branching_and_lifecycle.py` and
`tests/test_session_stream.py`, which drove the store and runner directly rather than through
the public HTTP surface.

That left a structural gap. The behaviours that matter most to a user — a conversation that
streams, a plan that opens and closes, a branch that slices history, a thread that is accepted
and merged — are *emergent*. They arise from the interaction between the config store, the
harness store, the runner, the artifact resolver, the workspace manager, and the FastAPI
routes. A unit test per module cannot observe them, and a route test with a mocked runner
cannot observe them either, because the behaviour lives precisely in the seam between the
modules.

Three backlog entries named this gap directly:

- *Comprehensive End-to-End Test Suite with Steerable LLM Mocking* (TODO)
- *Detailed End-to-End Testing of Thread Acceptance and Sync PR Lifecycle* (TODO)
- *Testing and Verification of Session Termination and Branching Lifecycle* (technical debt)
- *Rigorous and Detailed Automated Testing Matrix for Granular Bidirectional Session
  Branching* (technical debt)

The obstacle to closing them was inference randomness. An end-to-end test that drives a real
model is non-deterministic, slow, and costs money; a test that mocks the model at the HTTP
boundary stops exercising the runner, which is where most of the interesting behaviour lives.

## Decision

We introduce a dedicated end-to-end suite under `tests/e2e/` that drives the **real** Seamus
stack — config store, harness store, workspace manager, DeepAgent runner, artifact resolver,
and FastAPI routes — over the **real** HTTP API, with exactly two substitutions:

1. **The `steerable` inference provider replaces the live LLM.** The provider already exists
   ([0056-steerable-model-provider.md](./0056-steerable-model-provider.md)) and is a
   first-class inference format, not a test-only shim. Tests push scripted responses
   (text, reasoning, tool calls) onto a per-instance queue; the runner consumes them exactly
   as it would consume live model output. No API key, no network, no inference randomness.

2. **The OpenSandbox backend is replaced with an in-process host-filesystem stub**
   (`tests/e2e/stub_sandbox.py`). The stub implements the same filesystem and execution
   surface the runner consumes (`ls`, `read`, `write`, `edit`, `delete`, `glob`, `grep`,
   `execute`, `upload_files`, `download_files`, `destroy`, `reconfigure_mounts`,
   `get_skill_sources`), mapping `/workspace` to the session's `data/` directory and
   `/artifacts` to the session's `artifacts/` directory. This makes file writes, read-only
   mount policies, and exit codes observable without a live container.

Everything else is production code. The suite therefore observes emergent behaviour rather
than asserting against a mock's expectations.

### Test taxonomy

The suite is organised by the behaviour under test, not by the module under test:

| File | Scope |
| --- | --- |
| `tests/e2e/test_steerable_conversation.py` | Scripted turn execution, event recording, determinism |
| `tests/e2e/test_plan_lifecycle.py` | Plan artifact creation, phase transitions, blocking artifacts |
| `tests/e2e/test_session_lifecycle.py` | Termination, branching matrix, mode switching, thread acceptance |
| `tests/e2e/test_inspector_and_steerable.py` | Inspector report, steerable queue control surface |
| `tests/e2e/test_sync_pr_lifecycle.py` | Sync PR creation, diff scope, acceptance merge |
| `tests/e2e/test_telemetry_and_timestamps.py` | Span hierarchy, health-probe exclusion, event timestamps |

### Frontend component tests

The frontend gains a Node-native test runner (`node --test`) that loads **real** production
components from `ui/src` via esbuild and renders them to static markup. This avoids a
browser-automation dependency while still exercising the actual component code.

`ui/tests/messageItem.test.mjs` covers the branching affordances of `MessageItem`:
`BubbleBranchActions`, `BranchProvenanceSeparator`, `ToolGroupProvenanceIndicator`,
`SyntheticMessageBlock`, and `ReasoningBlock`.

`ui/tests/sequenceSource.test.mjs` exercises the real `ui/src/utils/sequence.ts` module. The
pre-existing `ui/tests/sequence.test.mjs` re-implemented that logic inline, which meant it
could pass while the production module drifted; the new file closes that gap.

### Known-failure documentation

The suite is allowed to contain tests that do not pass. Where a behaviour is specified but
not implemented, the test is marked `xfail(strict=False)` with a reason pointing at the
backlog entry that tracks the gap. This makes the suite a *specification* of intended
behaviour as well as a regression net, without blocking the pipeline on unimplemented work.

### CI integration

`.github/workflows/ci.yml` gains:

- a `test-e2e` job running `uv run pytest tests/e2e` in in-memory mode (no Gitea container
  required for the non-persistence scenarios);
- a `npm test` step in the existing `frontend` job.

## Consequences

### Positive

- Emergent behaviour across module boundaries is now observable and regression-protected.
- The suite is fast (the e2e suite runs in roughly 6 seconds) and free, so it can run on
  every push.
- The `steerable` provider is exercised by the same suite that exercises the product, so the
  provider itself cannot silently rot.
- The frontend tests run against real components, so a refactor that breaks rendering is
  caught without a browser.

### Negative

- The stub sandbox is a simplification. It refuses `execute` wholesale while the workspace is
  read-only rather than allowing read-only commands, and it copies bytes directly instead of
  streaming through the OpenSandbox API. It is not a security boundary. Tests must not
  over-claim what it proves.
- The four Sync PR lifecycle tests require Gitea-backed persistence and are therefore skipped
  in the in-memory `test-e2e` CI job. They run in the `test-docker` job, which executes the
  full suite against the ephemeral Gitea container.
- The suite covers the HTTP and runner layers, not the browser. Genuine client-side
  integration (real SSE consumption, real DOM interaction) remains uncovered.
- The `xfail` tests will start failing loudly if `strict=True` is ever used; they are
  deliberately non-strict so that implementing the behaviour flips them to passing without a
  test edit.

### Neutral

- The suite adds no production code. The only production-adjacent change is the CI workflow.

## Alternatives considered

- **Playwright / browser automation for the frontend.** Rejected for now: it adds a heavy
  dependency and a browser download to CI for coverage that static rendering already
  provides for the components under test. Real browser coverage remains a valid future step.
- **Mocking the runner at the route boundary.** Rejected: it would test the routes but not
  the behaviour, which is the entire point of the exercise.
- **A live model with recorded fixtures.** Rejected: non-deterministic, costly, and it would
  make the suite fail for reasons unrelated to the code under test.
- **Extending the existing unit suites instead of adding a new package.** Rejected: the
  fixtures required (a live app, a stubbed sandbox, a scripted model queue) are substantial
  and would have polluted the unit suites' focus.

## Provenance

- [0056-steerable-model-provider.md](./0056-steerable-model-provider.md) — the scripted
  provider this suite depends on.
- [0022-branching-out-and-session-lifecycle.md](./0022-branching-out-and-session-lifecycle.md)
- [0054-granular-bidirectional-session-branching.md](./0054-granular-bidirectional-session-branching.md)
- [0012-sync-prs-and-thread-accept.md](./0012-sync-prs-and-thread-accept.md)
- [0023-github-actions-ci-pipeline.md](./0023-github-actions-ci-pipeline.md)
- [REQ-052](../knowledge/requirements.md#req-052-deterministic-end-to-end-test-coverage-of-features-requirements-and-invariants)
- [INV-063](../knowledge/invariants.md#inv-063-deterministic-end-to-end-test-harness-isolation)
- [test_coverage.md](../knowledge/test_coverage.md) — the feature/requirement/invariant to test
  traceability map and the undertested report produced alongside this suite.
