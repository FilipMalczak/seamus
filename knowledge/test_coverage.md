# Test Coverage Traceability

Maps the user-facing features in [`FEATURES.md`](../FEATURES.md), the requirements in
[`requirements.md`](./requirements.md), and the invariants in [`invariants.md`](./invariants.md)
onto the tests that confirm them, and records where coverage is thin.

This document answers "is this behaviour actually tested?" — not "how many lines of code are
executed?". Line coverage is not a project metric; a behaviour that is never asserted is a
behaviour that can silently regress.

## Method

Four coverage tiers are used:

| Tier | Meaning |
| --- | --- |
| **E2E** | The behaviour is observed through the public HTTP surface with the real config store, harness store, runner, artifact resolver, and workspace manager. Only the LLM (via the `steerable` provider) and the sandbox container (via an in-process stub) are substituted. |
| **Unit** | The behaviour is observed at a module boundary with hand-built fixtures. |
| **Frontend** | The behaviour is observed by rendering the real production component from `ui/src` to static markup. |
| **None** | No test asserts the behaviour. |

A requirement or invariant is considered *covered* when at least one test would fail if the
behaviour regressed. Entries marked **None** are the undertested surface.

Every mapping below was re-derived by collecting the actual test IDs
(`pytest --collect-only`) and the actual frontend test names, then checking each claim
against the test body. Claims that did not survive that check were corrected — see
[Corrections from the re-derivation](#corrections-from-the-re-derivation).

## Test Inventory

| Suite | Location | Count | Notes |
| --- | --- | --- | --- |
| End-to-end | `tests/e2e/` | 38 | 31 pass in-memory, 4 require Gitea, 3 `xfail` |
| Unit / route | `tests/` | 317 | Pre-existing suite |
| Frontend | `ui/tests/` | 69 | Node-native, renders real production components |
| **Total (Python)** | `tests/` | **355** | Docker mode: 352 passed, 3 `xfailed`. In-memory mode: 348 passed, 4 skipped, 3 `xfailed` |

The four skipped tests are the Gitea-backed Sync PR lifecycle tests, which require a live
Gitea instance and therefore run only in the Docker CI job.

### End-to-end suite breakdown

| File | Tests | Scope |
| --- | --- | --- |
| `tests/e2e/test_steerable_conversation.py` | 7 | Scripted turn execution, event recording, replay, determinism |
| `tests/e2e/test_plan_lifecycle.py` | 7 | Plan artifact creation, phase transitions, blocking artifacts |
| `tests/e2e/test_session_lifecycle.py` | 9 | Termination, branching matrix, mode switching, thread acceptance |
| `tests/e2e/test_inspector_and_steerable.py` | 7 | Inspector report, steerable queue control surface |
| `tests/e2e/test_sync_pr_lifecycle.py` | 4 | Sync PR creation, diff scope, acceptance merge (Gitea-backed) |
| `tests/e2e/test_telemetry_and_timestamps.py` | 4 | Span hierarchy, health-probe exclusion, event timestamps |

### Frontend suite breakdown

| File | Tests | Loads |
| --- | --- | --- |
| `ui/tests/messageItem.test.mjs` | 21 | `ui/src/components/MessageItem.tsx` (real component) |
| `ui/tests/sequenceSource.test.mjs` | 13 | `ui/src/utils/sequence.ts` (real module) |
| `ui/tests/sequence.test.mjs` | 10 | Inline re-implementation — **does not** load production code |
| `ui/tests/steerable.test.mjs` | 25 | `ui/src/utils/steerable.ts` (real module) |

## Feature → Test Mapping

| # | Feature (`FEATURES.md`) | Tier | Confirming tests |
| --- | --- | --- | --- |
| 1 | Agent, Session & Thread Architecture | E2E + Unit | `e2e/test_steerable_conversation.py::test_agent_creation_yields_default_session_and_open_thread`, `e2e/test_session_lifecycle.py`, `tests/test_entities.py`, `tests/test_harness_store.py`, `tests/test_resolution.py` |
| 2 | Multi-Container Execution & Filesystem Sandboxing | Unit | `tests/test_sandbox.py`, `tests/test_bundled_skills.py`; e2e uses an in-process stub, so container provisioning itself is **not** covered end-to-end |
| 3 | Git-Native Persistence, Checkpointing & Provenance | E2E + Unit | `e2e/test_sync_pr_lifecycle.py`, `tests/test_workspace.py`, `tests/test_checkpointer.py`, `tests/test_harness_store_persistence.py` |
| 4 | Operational Modes & Structured Plan Lifecycle | E2E + Unit | `e2e/test_plan_lifecycle.py` (7), `e2e/test_session_lifecycle.py` (mode switch), `tests/test_modes_and_plan.py`, `tests/test_artifacts.py` |
| 5 | Adaptive UI (A2UI v1.0) & Dynamic Artifacts | E2E + Unit | `e2e/test_plan_lifecycle.py` (plan, questionnaire, click, blocking), `tests/test_artifacts.py` (39), `tests/test_artifact_routes.py` |
| 6 | Native LM-XML Skills System & Precedence Engine | Unit | `tests/test_skills.py`, `tests/test_bundled_skills.py`, `tests/test_inspector.py` |
| 7 | Enterprise Secrets Vault (OpenBao KV v2) | Unit | `tests/vault/` (19), `tests/test_vault_routes.py` (4) |
| 8 | Developer Web UI & Workspace Ergonomics | Frontend (partial) | `ui/tests/messageItem.test.mjs`, `ui/tests/sequenceSource.test.mjs`, `ui/tests/steerable.test.mjs`; `Sidebar`, `ChatArea`, `ChangesViewer`, `ConfigModal`, `SettingsModal`, `A2UIArtifactRenderer`, `TerminalView`, `MarkdownRenderer`, `AgentInspector` are **not** covered |
| 9 | DeepAgent Runtime Introspection & Inspector | E2E + Unit | `e2e/test_inspector_and_steerable.py` (7), `tests/test_inspector.py` (13) |
| 10 | Telemetry & Observability | E2E + Unit | `e2e/test_telemetry_and_timestamps.py`, `tests/test_telemetry.py` (10) |
| 11 | 1-Click Zero-Friction Stack Launch | None | `run.sh` and `docker-compose.yml` are not exercised by any test |
| 12 | Local Model Inference & Active Ollama Lifecycle | Unit | `tests/test_runner.py` (7 `ensure_ollama_model_*`), `tests/test_config.py::test_ollama_inference_config_completeness` |
| 13 | Non-Agentic Daemons & Automated Naming | Unit | `tests/test_daemons.py` (12) — daemon execution *is* covered (`test_execute_thread_naming_single_thread_session`, `test_execute_session_naming_multi_thread`); the *runner-loop trigger* and the daemon's own steerable queue are **not** covered end-to-end |
| 14 | Steerable Model Provider & Inspector Queue Editor | E2E + Unit + Frontend | `e2e/test_inspector_and_steerable.py` (7), `e2e/test_steerable_conversation.py::test_agent_and_daemon_queues_are_independent`, `tests/test_steerable.py` (19), `ui/tests/steerable.test.mjs` (25) |

## Requirement → Test Mapping

| Requirement | Tier | Confirming tests |
| --- | --- | --- |
| REQ-001 Python 3.12 & uv | Unit | `tests/test_smoke.py::test_version`; enforced by `pyproject.toml` and CI |
| REQ-002 Code quality & static verification | Unit | Enforced by CI (`ruff format --check`, `ruff check`, `mypy`) |
| REQ-003 Traceable documentation | Unit | Enforced by CI link check; `knowledge/` is the artefact |
| REQ-004 Config template singleton & derivation | Unit | `tests/test_config.py`, `tests/test_server.py` |
| REQ-005 Hierarchical REST API & dual identifiers | E2E + Unit | `e2e/*` (all), `tests/test_server.py`, `tests/test_resolution.py::test_resolve_session_and_thread` |
| REQ-006 Thread redirection, streaming & status | E2E + Unit | `e2e/test_steerable_conversation.py::test_thread_stream_replays_history_after_turn`, `::test_session_stream_replays_all_threads`, `tests/test_session_stream.py`, `tests/test_server.py::test_user_input_and_streaming` |
| REQ-007 Safe non-destructive API surface | E2E + Unit | `tests/test_server.py::test_no_delete_invariant_on_routes`, `e2e/test_inspector_and_steerable.py::test_steerable_queue_can_be_replaced_and_cleared` (clear = replacement, not DELETE) |
| REQ-008 Web UI with tree, streaming & JSON editor | Frontend (partial) | `ui/tests/`; the tree, streaming hook, and config editor are **not** covered |
| REQ-009 Default session & open thread creation | E2E + Unit | `e2e/test_steerable_conversation.py::test_agent_creation_yields_default_session_and_open_thread`, `tests/test_entities.py` |
| REQ-010 Containerized launch & clean reset | None | No test drives `run.sh` or the compose topology |
| REQ-011 Inline renaming & session status | None | No frontend test covers `Sidebar` renaming or status pills |
| REQ-012 Logfire hierarchical spans | E2E + Unit | `e2e/test_telemetry_and_timestamps.py::test_scripted_turn_emits_agent_session_thread_spans`, `tests/test_telemetry.py::test_store_entity_lifecycle_spans` |
| REQ-013 External links & telemetry guard | E2E + Unit | `e2e/test_telemetry_and_timestamps.py::test_api_request_emits_span_but_health_probe_does_not`, `tests/test_telemetry.py::test_is_logfire_enabled_and_service_name` |
| REQ-014 AG-UI reasoning exposure | E2E + Unit | `e2e/test_steerable_conversation.py::test_scripted_turn_emits_full_event_sequence` (asserts `REASONING*` events), `tests/test_runner.py::test_runner_reasoning_events_and_replay` |
| REQ-015 Gitea-backed persistence & isolation | E2E + Unit | `e2e/test_sync_pr_lifecycle.py`, `tests/test_workspace.py`, `tests/test_harness_store_persistence.py` |
| REQ-016 UI Markdown rendering | None | `MarkdownRenderer` has no frontend test |
| REQ-017 OpenSandbox execution & mount | Unit | `tests/test_sandbox.py` (11) |
| REQ-018 Inspection console & branch provenance | E2E + Unit | `e2e/test_inspector_and_steerable.py::test_inspect_report_exposes_tools_without_secrets`, `::test_inspect_report_reflects_conversation_history`, `tests/test_inspector.py` |
| REQ-019 Sync PRs & thread acceptance | E2E + Unit | `e2e/test_sync_pr_lifecycle.py` (4), `e2e/test_session_lifecycle.py::test_thread_acceptance_closes_thread_and_spawns_successor`, `tests/test_server.py::test_accept_thread_endpoint`, `tests/test_workspace.py::test_sync_pr_data_scoped_merge_lifecycle` |
| REQ-020 Tool call lifecycle visibility | E2E + Unit | `e2e/test_steerable_conversation.py::test_scripted_tool_call_executes_and_reports_result` (asserts `TOOL_CALL_START`/`TOOL_CALL_RESULT`), `tests/test_runner.py` |
| REQ-021 Sync PR diff & changes tab | E2E + Unit | `e2e/test_sync_pr_lifecycle.py::test_sync_pr_diff_exposes_only_data_deliverables`, `tests/test_server.py::test_session_diff_endpoint`; the `ChangesViewer` component is **not** covered |
| REQ-022 Restrict merges to `data/` | E2E + Unit | `e2e/test_sync_pr_lifecycle.py::test_acceptance_merges_data_deliverable_into_main`, `tests/test_artifacts.py::test_filter_sync_pr_diff_keeps_data_and_artifacts`, `tests/test_workspace.py::test_sync_pr_data_scoped_merge_lifecycle` |
| REQ-023 Dynamic LM-XML system prompt | Unit | `tests/test_prompt.py` (18), `tests/test_modes_and_plan.py::test_system_prompt_lmxml_composition` |
| REQ-024 Agent personas & archetypes | None | Personas are configuration-only; no test asserts their effect |
| REQ-025 Operational modes & transitions | E2E + Unit | `e2e/test_session_lifecycle.py::test_mode_switch_spawns_new_thread_and_closes_plan`, `::test_mode_switch_closes_open_blocking_questionnaire`, `tests/test_modes_and_plan.py` |
| REQ-026 Turn-level branching & lineage | E2E + Unit | `e2e/test_session_lifecycle.py` (4 branching tests), `tests/test_session_branching_and_lifecycle.py::test_granular_branch_before_and_after_tool_calls_and_reasoning` |
| REQ-027 Terminal session states & teardown | E2E + Unit | `e2e/test_session_lifecycle.py::test_killed_session_rejects_further_input`, `::test_killed_session_cannot_switch_mode`, `tests/test_session_branching_and_lifecycle.py::test_kill_session_mid_tool_cleans_up_and_errors`, `::test_kill_session_while_thinking_cleans_up_and_errors` |
| REQ-028 CI via GitHub Actions | Unit | `.github/workflows/ci.yml` runs the suites |
| REQ-029 Task planning & todo middleware | Unit | `tests/test_todos.py` (8), `tests/test_runner.py`, `tests/test_inspector.py::test_inspector_todo_implementation_toggle` |
| REQ-032 URL state, live refresh, error diagnostics | Unit (backend half) | `tests/test_runner.py::test_session_agent_runner_unhandled_error_includes_type_and_traceback` covers `RUN_ERROR` persistence; the **UI** half (URL sync, live refresh, error panel) is **not** covered |
| REQ-033 A2UI artifact model | E2E + Unit | `e2e/test_plan_lifecycle.py` (7), `tests/test_artifacts.py` (39) |
| REQ-034 Multi-phase plan lifecycle | E2E + Unit | `e2e/test_plan_lifecycle.py::test_discuss_to_make_transition_creates_new_thread`, `::test_proceed_advances_to_execute_phase`, `::test_workspace_is_read_only_during_make_phase`, `tests/test_modes_and_plan.py` |
| REQ-035 OpenBao vault integration | Unit | `tests/vault/` (19), `tests/test_vault_routes.py` (4) |
| REQ-036 External Git repositories | Unit | `tests/test_external_repos.py` (8) |
| REQ-037 Interactive web terminal | Unit | `tests/test_terminal.py` (5); the `TerminalView` component is **not** covered |
| REQ-038 Ollama provider & lifecycle | Unit | `tests/test_runner.py` (7 `ensure_ollama_model_*`), `tests/test_config.py` |
| REQ-039 Non-agentic daemons & naming | Unit | `tests/test_daemons.py` (12) — includes daemon execution with a mocked LLM; the runner-loop trigger and daemon steerable queue are **not** covered end-to-end |
| REQ-040 Coolname slug generation | Unit | `tests/test_daemons.py::test_agent_coolname_slug_generation_and_fallback` |
| REQ-041 Config model & UI symmetry | Unit | `tests/test_config.py` (14), `tests/test_server.py` |
| REQ-042 Context discovery & prompt injection | Unit | `tests/test_prompt.py` (18) |
| REQ-043 Native LM-XML skills | Unit | `tests/test_skills.py` (6), `tests/test_bundled_skills.py` (6) |
| REQ-044 Web search & enum guard | Unit | `tests/test_web_search.py` (13), `tests/test_inspector.py::test_inspector_web_search_filtering`, `tests/test_runner.py::test_runner_get_active_tools_web_search_filtering` |
| REQ-045 Chat timestamps & sequence indexing | E2E (xfail) + Frontend | `e2e/test_telemetry_and_timestamps.py` (2 `xfail` — backend does not stamp events), `ui/tests/sequenceSource.test.mjs` (13, real module) |
| REQ-046 A2UI v1.0 & UAX #31 validation | Unit | `tests/test_artifacts.py` (39) |
| REQ-047 Reasoning effort tiers | **None** | No test references `reasoning_effort` anywhere in `tests/` — the forwarding rule is entirely unasserted |
| REQ-048 Tool categorization & labeling | Unit | `tests/test_inspector.py::test_tool_labeling_resource_and_labels` |
| REQ-049 Cross-phase retained skills | Unit | `tests/test_skills.py::test_skill_stashing_across_thread_creation` |
| REQ-050 Artifacts implementation toggle | Unit | `tests/test_config.py::test_agent_config_artifacts_implementation_validation`, `tests/test_modes_and_plan.py::test_available_harness_tools_resolution_artifacts_none`, `tests/test_bundled_skills.py::test_bundled_skills_excluded_when_artifacts_implementation_none` |
| REQ-051 Steerable provider & queue editor | E2E + Unit + Frontend | `e2e/test_inspector_and_steerable.py` (7), `e2e/test_steerable_conversation.py::test_agent_and_daemon_queues_are_independent`, `tests/test_steerable.py` (19), `ui/tests/steerable.test.mjs` (25) |
| REQ-052 Deterministic e2e coverage | E2E | `tests/e2e/` (this document) |

## Invariant → Test Mapping

| Invariant | Tier | Confirming tests |
| --- | --- | --- |
| INV-001 uv & Python 3.12 | Unit | CI toolchain |
| INV-002 Zero tooling failures | Unit | CI gates |
| INV-003 Knowledge synchronization | Unit | CI link check |
| INV-004 Config completeness | Unit | `tests/test_config.py::test_agent_config_completeness` |
| INV-005 Single open thread | E2E + Unit | `e2e/test_steerable_conversation.py::test_agent_creation_yields_default_session_and_open_thread`, `tests/test_entities.py::test_session_single_open_thread_invariant` |
| INV-006 Slug format & scope uniqueness | Unit | `tests/test_entities.py::test_validate_slug_valid`, `::test_validate_slug_invalid`, `tests/test_resolution.py`, `tests/test_daemons.py::test_parse_loose_slug_collision_resolution` |
| INV-007 No resource deletion | E2E + Unit | `tests/test_server.py::test_no_delete_invariant_on_routes`, `e2e/test_inspector_and_steerable.py::test_steerable_queue_can_be_replaced_and_cleared` |
| INV-008 UI client-side busy guard | None | No frontend test covers the busy guard |
| INV-009 Default session & open thread | E2E + Unit | `e2e/test_steerable_conversation.py::test_agent_creation_yields_default_session_and_open_thread`, `tests/test_entities.py` |
| INV-010 Display name fallback | None | The only "fallback" test (`test_agent_coolname_slug_generation_and_fallback`) covers *slug* fallback (INV-050), not the UI's name→UUID display fallback |
| INV-011 Zero-prompt creation & auto-focus | None | Auto-focus is a frontend behaviour with no test |
| INV-012 User message recording & replay | E2E + Unit | `e2e/test_steerable_conversation.py::test_thread_stream_replays_history_after_turn`, `::test_session_stream_replays_all_threads`, `tests/test_session_stream.py` |
| INV-013 Inline editing & session status | None | No frontend test covers `Sidebar` |
| INV-014 Hierarchical execution spans | E2E + Unit | `e2e/test_telemetry_and_timestamps.py::test_scripted_turn_emits_agent_session_thread_spans`, `tests/test_telemetry.py::test_store_entity_lifecycle_spans` |
| INV-015 External links & telemetry guard | E2E + Unit | `e2e/test_telemetry_and_timestamps.py::test_api_request_emits_span_but_health_probe_does_not`, `tests/test_telemetry.py::test_is_logfire_enabled_and_service_name` |
| INV-016 Reasoning stream & span alignment | E2E + Unit | `e2e/test_steerable_conversation.py::test_scripted_turn_emits_full_event_sequence`, `tests/test_runner.py::test_reasoning_chat_openai_extracts_reasoning_fields`, `tests/test_telemetry.py::test_langgraph_multi_turn_no_duplicate_user_message` |
| INV-017 Git-tracked workspace & config boundary | Unit | `tests/test_workspace.py` (10) |
| INV-018 Atomic checkpoint persistence | Unit | `tests/test_checkpointer.py` (4), `tests/test_workspace.py::test_session_workspace_and_checkpoint_commits` |
| INV-019 Client-side markdown & content safety | None | `MarkdownRenderer` has no frontend test |
| INV-020 Runtime-managed sandbox auth | Unit | `tests/test_sandbox.py::test_get_or_create_sandbox_api_key_autogenerates_and_reuses`, `::test_get_or_create_sandbox_api_key_prefers_env_var` |
| INV-021 Inspection & credential redaction | E2E + Unit | `e2e/test_inspector_and_steerable.py::test_inspect_report_exposes_tools_without_secrets`, `tests/test_inspector.py` |
| INV-022 Thread acceptance & sync PR lifecycle | E2E + Unit | `e2e/test_sync_pr_lifecycle.py` (4), `e2e/test_session_lifecycle.py::test_thread_acceptance_closes_thread_and_spawns_successor`, `tests/test_workspace.py::test_sync_pr_data_scoped_merge_lifecycle` |
| INV-023 Tool call lifecycle & state | E2E + Unit | `e2e/test_steerable_conversation.py::test_scripted_tool_call_executes_and_reports_result`, `tests/test_runner.py` |
| INV-024 Session changes diff & acceptance placement | E2E + Unit | `e2e/test_sync_pr_lifecycle.py::test_sync_pr_diff_exposes_only_data_deliverables`, `tests/test_server.py::test_session_diff_endpoint`; the `ChangesViewer` component is **not** covered |
| INV-025 Merges scoped to `data/` | E2E + Unit | `e2e/test_sync_pr_lifecycle.py::test_acceptance_merges_data_deliverable_into_main`, `tests/test_artifacts.py::test_filter_sync_pr_diff_keeps_data_and_artifacts` |
| INV-026 Test persistence & host isolation | E2E | `tests/e2e/conftest.py` (per-test workspace roots), `tests/conftest.py` |
| INV-027 LM-XML prompt assembly | Unit | `tests/test_prompt.py` (18) |
| INV-028 Mode transition thread boundary | E2E + Unit | `e2e/test_session_lifecycle.py::test_mode_switch_spawns_new_thread_and_closes_plan`, `::test_branch_preserves_mode_and_phase`, `tests/test_modes_and_plan.py` |
| INV-029 Terminal immutability & teardown | E2E + Unit | `e2e/test_session_lifecycle.py::test_killed_session_rejects_further_input`, `::test_killed_session_cannot_switch_mode`, `tests/test_session_branching_and_lifecycle.py::test_kill_session_mid_tool_cleans_up_and_errors`, `::test_kill_session_while_thinking_cleans_up_and_errors` |
| INV-030 Branching isolation & provenance | E2E + Unit | `e2e/test_session_lifecycle.py` (4 branching tests), `tests/test_session_branching_and_lifecycle.py::test_granular_branch_before_and_after_tool_calls_and_reasoning`, `ui/tests/messageItem.test.mjs` (10 provenance tests) |
| INV-031 Read-only system skill sandboxing | Unit | `tests/test_sandbox.py::test_sandbox_build_skill_volumes_read_only`, `::test_sandbox_build_skill_volumes_tilde_expansion_and_missing_skipped` |
| INV-032 System repository persistence | Unit | `tests/test_workspace.py` |
| INV-033 Configurable todo/skills middleware | Unit | `tests/test_runner.py`, `tests/test_todos.py` (8), `tests/test_config.py::test_agent_config_todo_and_skills_implementation_validation` |
| INV-034 Dynamic runner recompilation | Unit | `tests/test_runner.py` |
| INV-035 Skill precedence & isolation | Unit | `tests/test_skills.py::test_discover_session_skills_precedence_and_shadowing`, `tests/test_bundled_skills.py::test_bundled_skills_precedence_in_skill_sources` |
| INV-047 Bundled skills shared volume | Unit | `tests/test_bundled_skills.py` (6) |
| INV-036 Workspace sync & auto-pull | Unit | `tests/test_workspace.py` |
| INV-039 Verbose `RUN_ERROR` persistence | Unit (backend half) | `tests/test_runner.py::test_session_agent_runner_unhandled_error_includes_type_and_traceback` asserts the event is appended to `thread.events` with `error_type` and `traceback` **and** broadcast live; the **UI** half (error panel, URL sync, live refresh) is **not** covered |
| INV-040 Artifact hierarchy & interaction lifecycle | E2E + Unit | `e2e/test_plan_lifecycle.py` (7), `tests/test_artifacts.py` (39), `tests/test_artifact_routes.py` |
| INV-041 Mount policy & recursion limit | E2E + Unit | `e2e/test_plan_lifecycle.py::test_workspace_is_read_only_during_make_phase`, `tests/test_modes_and_plan.py::test_notes_directory_and_sandbox_mount_policy`, `tests/test_runner.py` |
| INV-042 Secret evaluation & version watching | Unit | `tests/vault/test_client_and_interpolator.py` (8), `tests/vault/test_parser.py` (11) |
| INV-043 External repo isolation & credential safety | Unit | `tests/test_external_repos.py` (8) |
| INV-044 Multi-repo checkpoint ordering | Unit | `tests/test_external_repos.py::test_dual_index_checkpoint_and_restoration` |
| INV-045 Ephemeral working-tree semantics | Unit | `tests/test_external_repos.py` |
| INV-046 Terminal streaming & cwd continuity | Unit | `tests/test_terminal.py` (5) |
| INV-048 Ollama healthcheck & lifecycle | Unit | `tests/test_runner.py` (7 `ensure_ollama_model_*`), `tests/test_config.py` |
| INV-049 Daemon execution & stepback | Unit | `tests/test_daemons.py::test_is_stepback_trigger`, `::test_execute_thread_naming_single_thread_session`, `::test_execute_session_naming_multi_thread`, `::test_parallel_slug_model_thread_and_session` |
| INV-050 Deterministic slug generation | Unit | `tests/test_daemons.py::test_agent_coolname_slug_generation_and_fallback` |
| INV-051 Config model & UI symmetry | Unit | `tests/test_config.py` (14) |
| INV-052 Context discovery & injection | Unit | `tests/test_prompt.py` (18) |
| INV-053 Pure tag LM-XML skills | Unit | `tests/test_skills.py::test_lmxml_skills_prompt_serialization_no_attributes` |
| INV-054 Thread-scoped skills & tool gating | Unit | `tests/test_skills.py::test_runner_skills_prompt_and_tool_gating`, `::test_seamus_skills_middleware_load_and_unload` |
| INV-055 Web search guard & suppression | Unit | `tests/test_web_search.py` (13), `tests/test_inspector.py::test_inspector_web_search_filtering`, `tests/test_runner.py::test_runner_get_active_tools_web_search_filtering` |
| INV-056 Chat timestamps & sequence indexing | E2E (xfail) + Frontend | `e2e/test_telemetry_and_timestamps.py` (2 `xfail` — backend does not stamp events), `ui/tests/sequenceSource.test.mjs` (13, real module) |
| INV-057 A2UI UAX #31 identifiers | Unit | `tests/test_artifacts.py` (39) |
| INV-058 Model reasoning effort forwarding | **None** | No test references `reasoning_effort` anywhere in `tests/` |
| INV-059 Tool labeling JSON alignment | Unit | `tests/test_inspector.py::test_tool_labeling_resource_and_labels` |
| INV-060 Skill retention & token leakage | Unit | `tests/test_skills.py::test_skill_stashing_across_thread_creation` |
| INV-061 Artifacts capability gating | Unit | `tests/test_bundled_skills.py::test_bundled_skills_excluded_when_artifacts_implementation_none`, `tests/test_modes_and_plan.py::test_available_harness_tools_resolution_artifacts_none`, `tests/test_config.py::test_agent_config_artifacts_implementation_validation` |
| INV-062 Steerable isolation & credential freedom | E2E + Unit | `e2e/test_inspector_and_steerable.py` (7), `e2e/test_steerable_conversation.py::test_agent_and_daemon_queues_are_independent`, `tests/test_steerable.py` (19) |
| INV-063 Deterministic e2e harness isolation | E2E | `tests/e2e/conftest.py`, `tests/e2e/stub_sandbox.py` |

## Coverage Summary

| Tier | Requirements | Invariants |
| --- | --- | --- |
| E2E involved | 21 / 50 | 21 / 61 |
| Unit / Frontend only | 24 / 50 | 34 / 61 |
| **None** | **5 / 50** | **6 / 61** |

The five uncovered requirements are **REQ-010** (launch automation), **REQ-011** (inline
renaming & session status), **REQ-016** (UI Markdown rendering), **REQ-024** (personas), and
**REQ-047** (reasoning effort tiers). The six uncovered invariants are **INV-008** (UI busy
guard), **INV-010** (display name fallback), **INV-011** (zero-prompt creation & auto-focus),
**INV-013** (inline editing & session status), **INV-019** (client-side markdown & content
safety), and **INV-058** (reasoning effort forwarding).

Every requirement and invariant in [`requirements.md`](./requirements.md) and
[`invariants.md`](./invariants.md) appears in exactly one row of the tables above — 50 of 50
and 61 of 61, with no unmapped entries and no rows referring to identifiers that do not
exist.

## Undertested Report

The following are the areas where the behaviour is specified but not asserted by a test that
would fail on regression. They are ordered by user impact.

### 1. Frontend components beyond `MessageItem`, `sequence.ts`, and `steerable.ts` — **high**

Only `MessageItem` (branching affordances), `utils/sequence.ts`, and `utils/steerable.ts` are
covered. The components that carry the most user-visible behaviour have no test at all:

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

### 2. Model reasoning effort forwarding — **high**

`REQ-047` / `INV-058` specify that `reasoning_effort` is omitted from provider payloads when
set to `default` and forwarded verbatim for every other tier. **No test in the repository
references `reasoning_effort` at all.** A regression that always forwards the parameter, or
drops a non-default tier, would not fail any test. This is a one-line-per-tier unit test
against `ReasoningChatOpenAI` construction.

### 3. Backend event timestamps — **high**

`INV-056` / `REQ-045` require AG-UI events to carry an authoritative backend emission
timestamp. The backend does not stamp them, so the UI falls back to client-side render time.
Two e2e tests document this as `xfail(strict=False)`. The frontend sequence-indexing tests
pass because they exercise the client-side fallback, which means the *current* behaviour is
locked in while the *specified* behaviour is not implemented.

### 4. Daemon execution through the runner loop — **medium**

`tests/test_daemons.py` *does* execute the naming daemons (`execute_thread_naming`,
`execute_session_naming`) with the LLM call mocked, and asserts the resulting slugs and the
parallel-slug fallback. What is **not** covered is the daemon firing from inside
`SessionAgentRunner._run_loop` on the geometric stepback schedule, and the daemon consuming
its own `steerable` queue (`daemon_instance_id`) independently of the agent's queue. The
e2e suite asserts queue *independence* but never lets a daemon produce a slug.

### 5. Container provisioning and mount policy — **medium**

`tests/test_sandbox.py` covers `SeamusOpenSandboxBackend` against a mocked OpenSandbox API.
The e2e suite substitutes an in-process stub, so real container provisioning, the
`/workspace` ↔ `data/` mount, and the read-only `plan/make` policy are never exercised
against a live container. The stub enforces the read-only rule but does not prove the
production backend does.

### 6. UI error state and URL synchronisation — **medium**

`INV-039`'s backend half is covered: `tests/test_runner.py::test_session_agent_runner_unhandled_error_includes_type_and_traceback`
asserts the `RUN_ERROR` event is appended to `thread.events` with `error_type` and
`traceback` and is broadcast live. The **UI** half is not: no test asserts that the error
panel renders the diagnostics, that the active agent/session/thread/tab stay synchronised
with the URL query parameters, or that the Changes diff and sidebar tree auto-refresh across
turns. There is also no e2e test that drives a failing turn through the HTTP surface.

### 7. Launch automation — **low**

`run.sh`, `docker-compose.yml`, and the Dockerfile topology are untested. This is
infrastructure rather than product behaviour, so the cost of covering it is high relative to
its value; it is recorded here for completeness.

### 8. Personas — **low**

`REQ-024` specifies agent personas and baseline archetypes. They are configuration values
with no asserted effect on prompt assembly or behaviour.

## Corrections from the re-derivation

Re-deriving the map against the collected test IDs and test bodies corrected four claims
that the first pass had made:

| Item | First pass claimed | Verified reality |
| --- | --- | --- |
| REQ-047 / INV-058 (reasoning effort) | Covered by `tests/test_runner.py`, `tests/test_config.py` | **Not covered at all** — `grep -rn "reasoning_effort" tests/` returns nothing. The earlier mapping matched on the word "reasoning" and picked up reasoning-*content* tests. |
| REQ-039 / INV-049 (daemon execution) | "never executes a daemon" | Daemon execution **is** unit-covered (`test_execute_thread_naming_single_thread_session`, `test_execute_session_naming_multi_thread`). The real gap is the runner-loop trigger and the daemon's own steerable queue. |
| REQ-032 / INV-039 (`RUN_ERROR`) | "None" | The **backend** half is unit-covered (`test_session_agent_runner_unhandled_error_includes_type_and_traceback`). Only the UI half and the e2e path are uncovered. |
| INV-010 (display name fallback) | Covered by `tests/test_daemons.py` | That test covers *slug* fallback (INV-050), not the UI's name→UUID display fallback. INV-010 is **uncovered**. |

Two further claims were narrowed rather than reversed: REQ-050 / INV-061 (artifacts toggle) is
**Unit**-only — the e2e suite does not exercise the toggle — and INV-015 (telemetry guard) is
**E2E + Unit**, because the health-probe exclusion is asserted end-to-end.

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
