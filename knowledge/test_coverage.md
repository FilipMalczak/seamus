# Test Coverage Traceability

Maps the user-facing features in [`FEATURES.md`](../FEATURES.md), the requirements in
[`requirements.md`](./requirements.md), and the invariants in [`invariants.md`](./invariants.md)
onto the tests that confirm them, and records where coverage is thin.

This document answers "is this behaviour actually tested?" — not "how many lines of code are
executed?". Line coverage is not a project metric; a behaviour that is never asserted is a
behaviour that can silently regress.

## Method

Three coverage tiers are used:

| Tier | Meaning |
| --- | --- |
| **E2E** | The behaviour is observed through the public HTTP surface with the real config store, harness store, runner, artifact resolver, and workspace manager. Only the LLM (via the `steerable` provider) and the sandbox container (via an in-process stub) are substituted. |
| **Unit** | The behaviour is observed at a module boundary with hand-built fixtures. |
| **None** | No test asserts the behaviour. |

A requirement or invariant is considered *covered* when at least one test would fail if the
behaviour regressed. Requirements marked **None** are the undertested surface.

## Test Inventory

| Suite | Location | Count | Notes |
| --- | --- | --- | --- |
| End-to-end | `tests/e2e/` | 38 | 31 pass in-memory, 4 require Gitea, 3 `xfail` |
| Unit / route | `tests/` | 317 | Pre-existing suite |
| Frontend | `ui/tests/` | 69 | Node-native, renders real production components |

## Feature → Test Mapping

| # | Feature (`FEATURES.md`) | Tier | Confirming tests |
| --- | --- | --- | --- |
| 1 | Agent, Session & Thread Architecture | E2E + Unit | `tests/e2e/test_steerable_conversation.py`, `tests/e2e/test_session_lifecycle.py`, `tests/test_entities.py`, `tests/test_harness_store.py`, `tests/test_resolution.py` |
| 2 | Multi-Container Execution & Filesystem Sandboxing | Unit | `tests/test_sandbox.py`, `tests/test_bundled_skills.py`; e2e uses an in-process stub, so container provisioning itself is **not** covered end-to-end |
| 3 | Git-Native Persistence, Checkpointing & Provenance | E2E + Unit | `tests/e2e/test_sync_pr_lifecycle.py`, `tests/test_workspace.py`, `tests/test_checkpointer.py`, `tests/test_harness_store_persistence.py` |
| 4 | Operational Modes & Structured Plan Lifecycle | E2E + Unit | `tests/e2e/test_plan_lifecycle.py`, `tests/e2e/test_session_lifecycle.py`, `tests/test_modes_and_plan.py`, `tests/test_artifacts.py` |
| 5 | Adaptive UI (A2UI v1.0) & Dynamic Artifacts | E2E + Unit | `tests/e2e/test_plan_lifecycle.py`, `tests/test_artifacts.py`, `tests/test_artifact_routes.py` |
| 6 | Native LM-XML Skills System & Precedence Engine | Unit | `tests/test_skills.py`, `tests/test_bundled_skills.py`, `tests/test_inspector.py` |
| 7 | Enterprise Secrets Vault (OpenBao KV v2) | Unit | `tests/vault/`, `tests/test_vault_routes.py` |
| 8 | Developer Web UI & Workspace Ergonomics | Unit (frontend) | `ui/tests/messageItem.test.mjs`, `ui/tests/sequenceSource.test.mjs`, `ui/tests/sequence.test.mjs`; the remaining UI components are **not** covered |
| 9 | DeepAgent Runtime Introspection & Inspector | E2E + Unit | `tests/e2e/test_inspector_and_steerable.py`, `tests/test_inspector.py` |
| 10 | Telemetry & Observability | E2E + Unit | `tests/e2e/test_telemetry_and_timestamps.py`, `tests/test_telemetry.py` |
| 11 | 1-Click Zero-Friction Stack Launch | None | `run.sh` and `docker-compose.yml` are not exercised by any test |
| 12 | Local Model Inference & Active Ollama Lifecycle | Unit | `tests/test_runner.py` (`ensure_ollama_model_success`), `tests/test_config.py` |
| 13 | Non-Agentic Daemons & Automated Naming | Unit | `tests/test_daemons.py`; the daemon *execution* path is **not** covered end-to-end |
| 14 | Steerable Model Provider & Inspector Queue Editor | E2E + Unit | `tests/e2e/test_inspector_and_steerable.py`, `tests/test_steerable.py`, `ui/tests/steerable.test.mjs` |

## Requirement → Test Mapping

| Requirement | Tier | Confirming tests |
| --- | --- | --- |
| REQ-001 Python 3.12 & uv | Unit | `tests/test_smoke.py`; enforced by `pyproject.toml` and CI |
| REQ-002 Code quality & static verification | Unit | Enforced by CI (`ruff format --check`, `ruff check`, `mypy`) |
| REQ-003 Traceable documentation | Unit | Enforced by CI link check; `knowledge/` is the artefact |
| REQ-004 Config template singleton & derivation | Unit | `tests/test_config.py`, `tests/test_server.py` |
| REQ-005 Hierarchical REST API & dual identifiers | E2E + Unit | `tests/e2e/*`, `tests/test_server.py`, `tests/test_resolution.py` |
| REQ-006 Thread redirection, streaming & status | E2E + Unit | `tests/e2e/test_steerable_conversation.py`, `tests/test_session_stream.py` |
| REQ-007 Safe non-destructive API surface | E2E + Unit | `tests/test_server.py` (`no_delete_invariant_on_routes`), `tests/e2e/test_inspector_and_steerable.py` |
| REQ-008 Web UI with tree, streaming & JSON editor | Unit (frontend) | `ui/tests/`; the tree, streaming hook, and config editor are **not** covered |
| REQ-009 Default session & open thread creation | E2E + Unit | `tests/e2e/test_steerable_conversation.py`, `tests/test_entities.py` |
| REQ-010 Containerized launch & clean reset | None | No test drives `run.sh` or the compose topology |
| REQ-011 Inline renaming & session status | None | No frontend test covers `Sidebar` renaming or status pills |
| REQ-012 Logfire hierarchical spans | E2E + Unit | `tests/e2e/test_telemetry_and_timestamps.py`, `tests/test_telemetry.py` |
| REQ-013 External links & telemetry guard | Unit | `tests/test_telemetry.py` |
| REQ-014 AG-UI reasoning exposure | E2E + Unit | `tests/e2e/test_steerable_conversation.py`, `tests/test_runner.py` |
| REQ-015 Gitea-backed persistence & isolation | E2E + Unit | `tests/e2e/test_sync_pr_lifecycle.py`, `tests/test_workspace.py` |
| REQ-016 UI Markdown rendering | None | `MarkdownRenderer` has no frontend test |
| REQ-017 OpenSandbox execution & mount | Unit | `tests/test_sandbox.py` |
| REQ-018 Inspection console & branch provenance | E2E + Unit | `tests/e2e/test_inspector_and_steerable.py`, `tests/test_inspector.py` |
| REQ-019 Sync PRs & thread acceptance | E2E + Unit | `tests/e2e/test_sync_pr_lifecycle.py`, `tests/test_server.py`, `tests/test_workspace.py` |
| REQ-020 Tool call lifecycle visibility | E2E + Unit | `tests/e2e/test_steerable_conversation.py`, `tests/test_runner.py` |
| REQ-021 Sync PR diff & changes tab | Unit | `tests/test_workspace.py`; the `ChangesViewer` component is **not** covered |
| REQ-022 Restrict merges to `data/` | E2E + Unit | `tests/e2e/test_sync_pr_lifecycle.py`, `tests/test_artifacts.py` |
| REQ-023 Dynamic LM-XML system prompt | Unit | `tests/test_prompt.py` |
| REQ-024 Agent personas & archetypes | None | Personas are configuration-only; no test asserts their effect |
| REQ-025 Operational modes & transitions | E2E + Unit | `tests/e2e/test_session_lifecycle.py`, `tests/test_modes_and_plan.py` |
| REQ-026 Turn-level branching & lineage | E2E + Unit | `tests/e2e/test_session_lifecycle.py`, `tests/test_session_branching_and_lifecycle.py` |
| REQ-027 Terminal session states & teardown | E2E + Unit | `tests/e2e/test_session_lifecycle.py`, `tests/test_session_branching_and_lifecycle.py` |
| REQ-028 CI via GitHub Actions | Unit | `.github/workflows/ci.yml` runs the suites |
| REQ-029 Task planning & todo middleware | Unit | `tests/test_todos.py`, `tests/test_runner.py` |
| REQ-032 URL state, live refresh, error diagnostics | None | `useThreadStream` error capture and URL sync are **not** covered |
| REQ-033 A2UI artifact model | E2E + Unit | `tests/e2e/test_plan_lifecycle.py`, `tests/test_artifacts.py` |
| REQ-034 Multi-phase plan lifecycle | E2E + Unit | `tests/e2e/test_plan_lifecycle.py`, `tests/test_modes_and_plan.py` |
| REQ-035 OpenBao vault integration | Unit | `tests/vault/`, `tests/test_vault_routes.py` |
| REQ-036 External Git repositories | Unit | `tests/test_external_repos.py` |
| REQ-037 Interactive web terminal | Unit | `tests/test_terminal.py`; the `TerminalView` component is **not** covered |
| REQ-038 Ollama provider & lifecycle | Unit | `tests/test_runner.py`, `tests/test_config.py` |
| REQ-039 Non-agentic daemons & naming | Unit | `tests/test_daemons.py` |
| REQ-040 Coolname slug generation | Unit | `tests/test_daemons.py` |
| REQ-041 Config model & UI symmetry | Unit | `tests/test_config.py`, `tests/test_server.py` |
| REQ-042 Context discovery & prompt injection | Unit | `tests/test_prompt.py` |
| REQ-043 Native LM-XML skills | Unit | `tests/test_skills.py` |
| REQ-044 Web search & enum guard | Unit | `tests/test_web_search.py`, `tests/test_inspector.py` |
| REQ-045 Chat timestamps & sequence indexing | E2E + Unit | `tests/e2e/test_telemetry_and_timestamps.py` (2 `xfail`), `ui/tests/sequenceSource.test.mjs` |
| REQ-046 A2UI v1.0 & UAX #31 validation | Unit | `tests/test_artifacts.py` |
| REQ-047 Reasoning effort tiers | Unit | `tests/test_runner.py`, `tests/test_config.py` |
| REQ-048 Tool categorization & labeling | Unit | `tests/test_inspector.py` |
| REQ-049 Cross-phase retained skills | Unit | `tests/test_skills.py` |
| REQ-050 Artifacts implementation toggle | E2E + Unit | `tests/e2e/test_plan_lifecycle.py`, `tests/test_runner.py`, `tests/test_config.py` |
| REQ-051 Steerable provider & queue editor | E2E + Unit | `tests/e2e/test_inspector_and_steerable.py`, `tests/test_steerable.py`, `ui/tests/steerable.test.mjs` |
| REQ-052 Deterministic e2e coverage | E2E | `tests/e2e/` (this document) |

## Invariant → Test Mapping

| Invariant | Tier | Confirming tests |
| --- | --- | --- |
| INV-001 uv & Python 3.12 | Unit | CI toolchain |
| INV-002 Zero tooling failures | Unit | CI gates |
| INV-003 Knowledge synchronization | Unit | CI link check |
| INV-004 Config completeness | Unit | `tests/test_config.py` |
| INV-005 Single open thread | E2E + Unit | `tests/e2e/test_steerable_conversation.py`, `tests/test_entities.py` |
| INV-006 Slug format & scope uniqueness | Unit | `tests/test_entities.py`, `tests/test_harness_store.py`, `tests/test_daemons.py` |
| INV-007 No resource deletion | E2E + Unit | `tests/test_server.py`, `tests/e2e/test_inspector_and_steerable.py` |
| INV-008 UI client-side busy guard | None | No frontend test covers the busy guard |
| INV-009 Default session & open thread | E2E + Unit | `tests/e2e/test_steerable_conversation.py`, `tests/test_entities.py` |
| INV-010 Display name fallback | Unit | `tests/test_daemons.py` |
| INV-011 Zero-prompt creation & auto-focus | None | Auto-focus is a frontend behaviour with no test |
| INV-012 User message recording & replay | E2E + Unit | `tests/e2e/test_steerable_conversation.py`, `tests/test_session_stream.py` |
| INV-013 Inline editing & session status | None | No frontend test covers `Sidebar` |
| INV-014 Hierarchical execution spans | E2E + Unit | `tests/e2e/test_telemetry_and_timestamps.py`, `tests/test_telemetry.py` |
| INV-015 External links & telemetry guard | Unit | `tests/test_telemetry.py` |
| INV-016 Reasoning stream & span alignment | E2E + Unit | `tests/e2e/test_steerable_conversation.py`, `tests/test_runner.py` |
| INV-017 Git-tracked workspace & config boundary | Unit | `tests/test_workspace.py` |
| INV-018 Atomic checkpoint persistence | Unit | `tests/test_checkpointer.py`, `tests/test_workspace.py` |
| INV-019 Client-side markdown & content safety | None | `MarkdownRenderer` has no frontend test |
| INV-020 Runtime-managed sandbox auth | Unit | `tests/test_sandbox.py` |
| INV-021 Inspection & credential redaction | E2E + Unit | `tests/e2e/test_inspector_and_steerable.py`, `tests/test_inspector.py` |
| INV-022 Thread acceptance & sync PR lifecycle | E2E + Unit | `tests/e2e/test_sync_pr_lifecycle.py`, `tests/test_workspace.py` |
| INV-023 Tool call lifecycle & state | E2E + Unit | `tests/e2e/test_steerable_conversation.py`, `tests/test_runner.py` |
| INV-024 Session changes diff & acceptance placement | Unit | `tests/test_server.py` (`session_diff_endpoint`); the `ChangesViewer` component is **not** covered |
| INV-025 Merges scoped to `data/` | E2E + Unit | `tests/e2e/test_sync_pr_lifecycle.py`, `tests/test_artifacts.py` |
| INV-026 Test persistence & host isolation | E2E | `tests/e2e/conftest.py` (per-test workspace roots) |
| INV-027 LM-XML prompt assembly | Unit | `tests/test_prompt.py` |
| INV-028 Mode transition thread boundary | E2E + Unit | `tests/e2e/test_session_lifecycle.py`, `tests/test_modes_and_plan.py` |
| INV-029 Terminal immutability & teardown | E2E + Unit | `tests/e2e/test_session_lifecycle.py`, `tests/test_session_branching_and_lifecycle.py` |
| INV-030 Branching isolation & provenance | E2E + Unit | `tests/e2e/test_session_lifecycle.py`, `tests/test_session_branching_and_lifecycle.py` |
| INV-031 Read-only system skill sandboxing | Unit | `tests/test_sandbox.py`, `tests/test_bundled_skills.py` |
| INV-032 System repository persistence | Unit | `tests/test_workspace.py` |
| INV-033 Configurable todo/skills middleware | Unit | `tests/test_runner.py`, `tests/test_todos.py` |
| INV-034 Dynamic runner recompilation | Unit | `tests/test_runner.py` |
| INV-035 Skill precedence & isolation | Unit | `tests/test_skills.py`, `tests/test_bundled_skills.py` |
| INV-047 Bundled skills shared volume | Unit | `tests/test_bundled_skills.py` |
| INV-036 Workspace sync & auto-pull | Unit | `tests/test_workspace.py` |
| INV-039 Verbose `RUN_ERROR` persistence | None | The error event is not asserted end-to-end |
| INV-040 Artifact hierarchy & interaction lifecycle | E2E + Unit | `tests/e2e/test_plan_lifecycle.py`, `tests/test_artifacts.py` |
| INV-041 Mount policy & recursion limit | E2E + Unit | `tests/e2e/test_plan_lifecycle.py`, `tests/test_modes_and_plan.py`, `tests/test_runner.py` |
| INV-042 Secret evaluation & version watching | Unit | `tests/vault/test_client_and_interpolator.py` |
| INV-043 External repo isolation & credential safety | Unit | `tests/test_external_repos.py` |
| INV-044 Multi-repo checkpoint ordering | Unit | `tests/test_external_repos.py` |
| INV-045 Ephemeral working-tree semantics | Unit | `tests/test_external_repos.py` |
| INV-046 Terminal streaming & cwd continuity | Unit | `tests/test_terminal.py` |
| INV-048 Ollama healthcheck & lifecycle | Unit | `tests/test_runner.py` |
| INV-049 Daemon execution & stepback | Unit | `tests/test_daemons.py` |
| INV-050 Deterministic slug generation | Unit | `tests/test_daemons.py` |
| INV-051 Config model & UI symmetry | Unit | `tests/test_config.py` |
| INV-052 Context discovery & injection | Unit | `tests/test_prompt.py` |
| INV-053 Pure tag LM-XML skills | Unit | `tests/test_skills.py` |
| INV-054 Thread-scoped skills & tool gating | Unit | `tests/test_skills.py` |
| INV-055 Web search guard & suppression | Unit | `tests/test_web_search.py`, `tests/test_inspector.py` |
| INV-056 Chat timestamps & sequence indexing | E2E + Unit | `tests/e2e/test_telemetry_and_timestamps.py` (2 `xfail` — backend does not stamp events), `ui/tests/sequenceSource.test.mjs` |
| INV-057 A2UI UAX #31 identifiers | Unit | `tests/test_artifacts.py` |
| INV-058 Reasoning effort forwarding | Unit | `tests/test_runner.py` |
| INV-059 Tool labeling JSON alignment | Unit | `tests/test_inspector.py` |
| INV-060 Skill retention & token leakage | Unit | `tests/test_skills.py` |
| INV-061 Artifacts capability gating | E2E + Unit | `tests/e2e/test_plan_lifecycle.py`, `tests/test_runner.py` |
| INV-062 Steerable isolation & credential freedom | E2E + Unit | `tests/e2e/test_inspector_and_steerable.py`, `tests/test_steerable.py` |
| INV-063 Deterministic e2e harness isolation | E2E | `tests/e2e/conftest.py`, `tests/e2e/stub_sandbox.py` |

## Undertested Report

The following are the areas where the behaviour is specified but not asserted by a test that
would fail on regression. They are ordered by user impact.

### 1. Frontend components beyond `MessageItem` and `sequence.ts` — **high**

Only `MessageItem` (branching affordances) and `utils/sequence.ts` are covered. The
components that carry the most user-visible behaviour have no test at all:

- `Sidebar` — tree rendering, inline renaming, status pills, external links (REQ-011, INV-013)
- `ChatArea` — message listing, streak/sequence computation, auto-scroll, error panel (REQ-032, INV-039)
- `useThreadStream` — SSE consumption, AG-UI event reduction, error diagnostics (REQ-032)
- `ChangesViewer` — diff rendering, file navigation, Accept placement (REQ-021, INV-024)
- `ConfigModal` / `SettingsModal` — structured form ↔ raw JSON symmetry (REQ-041, INV-051)
- `A2UIArtifactRenderer` — button clicks, comment pushes, disabled state (REQ-033)
- `TerminalView` — output buffer, history, interruption (REQ-037, INV-046)
- `MarkdownRenderer` — code blocks, tables, link safety (REQ-016, INV-019)
- `AgentInspector` — prompt decomposition, tool inventory, todo list (REQ-018)

The `node --test` harness already in `ui/tests/` makes these cheap to add: each is a
`loadModule` call plus static-markup assertions.

### 2. Backend event timestamps — **high**

`INV-056` / `REQ-045` require AG-UI events to carry an authoritative backend emission
timestamp. The backend does not stamp them, so the UI falls back to client-side render time.
Two e2e tests document this as `xfail(strict=False)`. The frontend sequence-indexing tests
pass because they exercise the client-side fallback, which means the *current* behaviour is
locked in while the *specified* behaviour is not implemented.

### 3. Daemon execution path — **medium**

`tests/test_daemons.py` covers slug parsing, stepback detection, and history formatting, but
never executes a daemon. The `steerable` provider supports daemon instances
(`daemon_instance_id`), so the naming daemon could be driven end-to-end with a scripted
response and asserted on the resulting thread/session slug.

### 4. Container provisioning and mount policy — **medium**

`tests/test_sandbox.py` covers `SeamusOpenSandboxBackend` against a mocked OpenSandbox API.
The e2e suite substitutes an in-process stub, so real container provisioning, the
`/workspace` ↔ `data/` mount, and the read-only `plan/make` policy are never exercised
against a live container. The stub enforces the read-only rule but does not prove the
production backend does.

### 5. `RUN_ERROR` persistence and UI error state — **medium**

`INV-039` requires verbose `RUN_ERROR` events to be persisted and surfaced. No test asserts
that a failing turn produces a persisted error event, nor that the UI renders it.

### 6. Launch automation — **low**

`run.sh`, `docker-compose.yml`, and the Dockerfile topology are untested. This is
infrastructure rather than product behaviour, so the cost of covering it is high relative to
its value; it is recorded here for completeness.

### 7. Personas — **low**

`REQ-024` specifies agent personas and baseline archetypes. They are configuration values
with no asserted effect on prompt assembly or behaviour.

## Deliberately Not Covered

- **Live inference.** Every e2e test uses the `steerable` provider. Real-provider behaviour
  (retries, rate limits, provider-specific quirks) is out of scope by design.
- **Browser automation.** The frontend suite renders components to static markup. Genuine
  client-side integration — real SSE consumption, real DOM interaction — is not covered.
- **Line coverage.** Not tracked as a metric. See the method note above.

## Cross-References

- [requirements.md](./requirements.md) — REQ-052 defines the coverage requirement itself
- [invariants.md](./invariants.md) — INV-063 defines the harness isolation invariant
- [backlog.md](./backlog.md) — outstanding coverage work
- [0057-e2e-test-suite.md](../decisions/0057-e2e-test-suite.md) — the decision that created
  the e2e suite
