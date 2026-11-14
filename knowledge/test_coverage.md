# Test Coverage Traceability

Maps the user-facing features in [`FEATURES.md`](../FEATURES.md), the requirements in
[`requirements.md`](./requirements.md), and the invariants in [`invariants.md`](./invariants.md)
onto the tests that confirm them, and tracks the remaining gaps against the coverage floor
established in [0058-coverage-baseline-and-tiering.md](../decisions/0058-coverage-baseline-and-tiering.md).

This document answers "is this behaviour actually asserted?" — not "how many lines of code are
executed?". Line coverage is not a project metric; a behaviour without an assertion is a
behaviour that can silently regress.

## Method and Coverage Tiers

Per [0058-coverage-baseline-and-tiering.md](../decisions/0058-coverage-baseline-and-tiering.md),
four verification tiers are used:

| Tier | Definition |
| --- | --- |
| **E2E** | Asserted through the public HTTP surface of the running harness (`tests/e2e/`). Only the inference provider (`steerable`) and container runtime (in-process stub sandbox) are substituted. |
| **Frontend** | Asserted in Node (`ui/tests/`) by rendering real production components and hooks from `ui/src/` to DOM markup or executing real TypeScript utility modules. |
| **Unit** | Asserted at a module boundary (`tests/test_*.py`, `tests/vault/`) with focused fixtures or mocks. |
| **Config** | Asserted by static validation of repository deployment, packaging, CI, and documentation configuration (`docker-compose.yml`, `run.sh`, `.github/workflows/ci.yml`, `pyproject.toml`, `knowledge/`, `decisions/`). |

A requirement or invariant may be covered at multiple tiers. Tables below list the **highest**
tier reached alongside any additional confirming tiers, and the
[Coverage Summary](#coverage-summary) reports green end-to-end coverage separately from
non-strict `xfail` tests so headline numbers are never overstated.

Every mapping below was derived from the collected test identifiers (`uv run pytest --collect-only -q`
and `node --test` under `ui/tests/`) and verified against the test bodies.

## Test Inventory

| Suite | Location | Files | Count | Notes |
| --- | --- | ---: | ---: | --- |
| End-to-end | `tests/e2e/` | 22 | 158 | Docker mode: 152 pass, 6 `xfail`. In-memory mode: 148 pass, 4 skipped (`test_sync_pr_lifecycle.py`), 6 `xfail` |
| Unit & Config | `tests/` | 34 | 366 | 364 pass, 2 `xfail` (`test_personas.py`) |
| **Total (Python)** | `tests/` | **56** | **524** | **Docker mode: 516 pass, 8 `xfail`. In-memory mode: 512 pass, 4 skipped, 8 `xfail`** |
| **Frontend** | `ui/tests/` | **16** | **247** | Node-native suite; 247 pass, 0 failed |

The four skipped Python tests in `SEAMUS_TEST_IN_MEMORY=true` mode are the four Gitea-backed
tests in `tests/e2e/test_sync_pr_lifecycle.py`, which require live Gitea persistence and run in
the Docker pytest job.

### End-to-end suite breakdown (`tests/e2e/`)

| File | Tests | Passing | `xfail` | Scope |
| --- | ---: | ---: | ---: | --- |
| `tests/e2e/test_a2ui_validation.py` | 6 | 6 | 0 | A2UI UAX #31 ID normalization, surface rejection, workspace persistence, listing |
| `tests/e2e/test_agent_lifecycle.py` | 8 | 8 | 0 | Coolname slugs, uniqueness, runner recompilation on session config update, persistence |
| `tests/e2e/test_agents.py` | 10 | 10 | 0 | Template derivation, agent overrides, duplicate slug 409, CRUD aliases & errors |
| `tests/e2e/test_artifact_routes.py` | 10 | 9 | 1 | Artifact list/detail/click routes, UUID family lookup; `/submit` pinned `xfail` |
| `tests/e2e/test_capability_gating.py` | 11 | 11 | 0 | `artifacts_implementation`, `todo_implementation`, `skills_implementation`, `web_search`, skill `allowed_tools` gating |
| `tests/e2e/test_config_settings_system.py` | 7 | 7 | 0 | Singleton template, settings persistence, `/system/info`, `/health` |
| `tests/e2e/test_daemon_naming.py` | 4 | 4 | 0 | Naming daemon dispatch via its own steerable queue, session slug mirroring, loose parsing |
| `tests/e2e/test_error_diagnostics.py` | 5 | 3 | 2 | `RUN_ERROR` emission/replay/status; `error_type` & `traceback` propagation pinned `xfail` |
| `tests/e2e/test_external_repos.py` | 6 | 6 | 0 | `/projects/<mount>`, collision suffixes, credential redaction, sandbox mounts & prompt |
| `tests/e2e/test_harness_tools.py` | 9 | 9 | 0 | Real `create`/`edit`/`delete_todo_item`, `load_skill`/`unload_skill`, `web_search` tool execution |
| `tests/e2e/test_inspector_and_steerable.py` | 7 | 6 | 1 | `/inspect` report, credential redaction, steerable queue/strategy routes; checkpoint history `xfail` |
| `tests/e2e/test_plan_lifecycle.py` | 7 | 7 | 0 | `discuss -> make -> execute`, `plan.md`, read-only `make`, questionnaires, `wait_for_click` |
| `tests/e2e/test_prompt_composition.py` | 7 | 7 | 0 | LM-XML composite prompt, dynamic context, `AGENTS.md` discovery, pure-tag skills |
| `tests/e2e/test_session_lifecycle.py` | 9 | 9 | 0 | Kill teardown & 409/400 guards, branching before/after & lineage, mode switch, accept |
| `tests/e2e/test_steerable_conversation.py` | 7 | 7 | 0 | Default session/thread, reasoning & tool events, SSE replay, queue isolation, determinism |
| `tests/e2e/test_sync_pr_lifecycle.py` | 4 | 4 | 0 | Sync PR open, `data/`-scoped diff filtering, thread acceptance merge & PR renewal (Gitea) |
| `tests/e2e/test_telemetry_and_timestamps.py` | 4 | 2 | 2 | Hierarchical agent/session/thread spans, `/health` exclusion; emission timestamps pinned `xfail` |
| `tests/e2e/test_terminal_stream.py` | 6 | 6 | 0 | Terminal info, 404, SSE stdout/exit streaming, non-zero exit codes, `cd` cwd continuity |
| `tests/e2e/test_threads.py` | 12 | 12 | 0 | Single open thread reuse/close, slug conflicts, status, rename, 307 redirect, SSE replay |
| `tests/e2e/test_vault.py` | 8 | 8 | 0 | OpenBao token endpoint, secret write/read/update/list via HTTP without echoing values |
| `tests/e2e/test_web_search_tools.py` | 2 | 2 | 0 | Scripted `web_search` tool execution and tool absence when disabled |
| `tests/e2e/test_workspace_and_skills.py` | 9 | 9 | 0 | `data/` vs `agent/config/` separation, skill shadowing, bundled mounts, ro/rw policy, `retained_skills` |

### Frontend suite breakdown (`ui/tests/`)

| File | Tests | Production target loaded | Scope |
| --- | ---: | --- | --- |
| `ui/tests/a2uiArtifactRenderer.test.mjs` | 13 | `ui/src/components/A2UIArtifactRenderer.tsx` | Badges, collapse toggle, read-only vs interactive surfaces, submitting overlay, plan fallback title |
| `ui/tests/agentInspector.test.mjs` | 18 | `ui/src/components/AgentInspector.tsx` | Prompt layers & copy, semantic tool badges & filter, schema reveal, todos, skills, steerable tab |
| `ui/tests/changesViewer.test.mjs` | 16 | `ui/src/components/ChangesViewer.tsx` | Sync PR link/badge, file tree & filter, unified/split diff, header Accept button & busy/closed guards |
| `ui/tests/chatArea.test.mjs` | 12 | `ui/src/components/ChatArea.tsx` | Composer busy/closed/error guards, autofocus, `RUN_ERROR` diagnostic panel & traceback toggle |
| `ui/tests/configModal.test.mjs` | 21 | `ui/src/components/ConfigModal.tsx` | Form ↔ JSON view sync, `reasoning_effort` tiers, secret masking/reveal, enum/daemon validation |
| `ui/tests/header.test.mjs` | 7 | `ui/src/components/Header.tsx` | Config template model/base URL display, AG-UI indicator, settings & template triggers |
| `ui/tests/markdownRenderer.test.mjs` | 12 | `ui/src/components/MarkdownRenderer.tsx` | HTML rendering, GFM tables, fenced code blocks & copy, external link `rel`, XSS/raw-HTML safety |
| `ui/tests/messageItem.test.mjs` | 22 | `ui/src/components/MessageItem.tsx` | Bubbles, timestamps, sequence badges, branching actions, provenance separators, reasoning/tools |
| `ui/tests/sequence.test.mjs` | 10 | Reference specification (standalone) | Independent baseline spec for bubble streak indexing and timestamp formatting |
| `ui/tests/sequenceSource.test.mjs` | 14 | `ui/src/utils/sequence.ts` | Production `extractBubblesFromMessages`, `computeBubbleSequenceIndices`, `formatBubbleTime`, `formatFullDate` |
| `ui/tests/settingsModal.test.mjs` | 19 | `ui/src/components/SettingsModal.tsx` | Skill directories CRUD + JSON view, secrets list without echoing values, token reveal, save/cancel |
| `ui/tests/sidebar.test.mjs` | 22 | `ui/src/components/Sidebar.tsx` | Tree rendering, UUID fallback, inline rename + `<Check />` without `prompt()`, status icons, create flow |
| `ui/tests/steerable.test.mjs` | 23 | `ui/src/utils/steerable.ts` | Draft parsing/validation, queue JSON serialization, replace/extend upload planning |
| `ui/tests/terminalView.test.mjs` | 13 | `ui/src/components/TerminalView.tsx` | Terminal info fetch, SSE stream stdout/stderr/exit codes, cwd continuity, history navigation, shortcuts |
| `ui/tests/toolCallItem.test.mjs` | 13 | `ui/src/components/ToolCallItem.tsx` | Pending/WIP/Done/Failed badges, auto-collapse on completion, args/result blocks, web tool icon |
| `ui/tests/useAgentsTree.test.mjs` | 12 | `ui/src/hooks/useAgentsTree.ts` | Tree hydration, URL slug/UUID synchronization, Back navigation, auto-selection hierarchy |

## Feature → Test Mapping

| # | Feature (`FEATURES.md`) | Highest tier (all tiers) | Confirming tests |
| ---: | --- | --- | --- |
| 1 | Agent, Session & Thread Architecture | **E2E** (E2E + Unit + Frontend) | `e2e/test_agents.py` (10), `e2e/test_threads.py` (12), `e2e/test_steerable_conversation.py`, `e2e/test_session_lifecycle.py` (9), `tests/test_entities.py` (5), `tests/test_resolution.py` (2), `ui/tests/useAgentsTree.test.mjs` (12) |
| 2 | Multi-Container Execution & Filesystem Sandboxing | **E2E** (E2E + Unit) | `e2e/test_workspace_and_skills.py` (`test_the_workspace_is_read_only_during_the_make_phase`, `test_the_workspace_is_writable_in_chat_mode`, `test_the_sandbox_receives_the_session_skill_mounts`), `e2e/test_external_repos.py`, `tests/test_sandbox.py` (11), `tests/test_bundled_skills.py` (6) |
| 3 | Git-Native Persistence, Checkpointing & Provenance | **E2E** (E2E + Unit + Frontend) | `e2e/test_sync_pr_lifecycle.py` (4), `e2e/test_workspace_and_skills.py`, `e2e/test_session_lifecycle.py`, `tests/test_workspace.py` (10), `tests/test_checkpointer.py` (4), `tests/test_harness_store_persistence.py` (2), `ui/tests/changesViewer.test.mjs` (16) |
| 4 | Operational Modes & Structured Plan Lifecycle | **E2E** (E2E + Unit + Frontend) | `e2e/test_plan_lifecycle.py` (7), `e2e/test_session_lifecycle.py` (mode switches), `e2e/test_prompt_composition.py`, `tests/test_modes_and_plan.py` (8), `tests/test_artifacts.py`, `ui/tests/a2uiArtifactRenderer.test.mjs` |
| 5 | Adaptive UI (A2UI v1.0) & Dynamic Artifacts | **E2E** (E2E + Unit + Frontend) | `e2e/test_a2ui_validation.py` (6), `e2e/test_artifact_routes.py` (9 pass, 1 `xfail`), `e2e/test_plan_lifecycle.py`, `e2e/test_capability_gating.py`, `tests/test_artifacts.py` (39), `ui/tests/a2uiArtifactRenderer.test.mjs` (13) |
| 6 | Native LM-XML Skills System & Precedence Engine | **E2E** (E2E + Unit + Frontend) | `e2e/test_workspace_and_skills.py` (shadowing, bundled, mounts, `retained_skills`), `e2e/test_harness_tools.py` (`load_skill`/`unload_skill`), `e2e/test_capability_gating.py`, `e2e/test_prompt_composition.py`, `tests/test_skills.py` (6), `tests/test_bundled_skills.py` (6), `ui/tests/agentInspector.test.mjs`, `ui/tests/settingsModal.test.mjs` |
| 7 | Enterprise Secrets Vault (OpenBao KV v2) | **E2E** (E2E + Unit + Frontend) | `e2e/test_vault.py` (8), `tests/vault/` (19), `tests/test_vault_routes.py` (4), `ui/tests/settingsModal.test.mjs`, `ui/tests/configModal.test.mjs` |
| 8 | Developer Web UI & Workspace Ergonomics | **Frontend** | `ui/tests/sidebar.test.mjs` (22), `ui/tests/chatArea.test.mjs` (12), `ui/tests/changesViewer.test.mjs` (16), `ui/tests/configModal.test.mjs` (21), `ui/tests/settingsModal.test.mjs` (19), `ui/tests/header.test.mjs` (7), `ui/tests/markdownRenderer.test.mjs` (12), `ui/tests/messageItem.test.mjs` (22), `ui/tests/toolCallItem.test.mjs` (13), `ui/tests/terminalView.test.mjs` (13), `ui/tests/a2uiArtifactRenderer.test.mjs` (13), `ui/tests/useAgentsTree.test.mjs` (12), `ui/tests/sequenceSource.test.mjs` (14) |
| 9 | DeepAgent Runtime Introspection & Inspector | **E2E** (E2E + Unit + Frontend) | `e2e/test_inspector_and_steerable.py` (6 pass, 1 `xfail`), `e2e/test_prompt_composition.py`, `e2e/test_capability_gating.py`, `e2e/test_external_repos.py`, `tests/test_inspector.py` (13), `ui/tests/agentInspector.test.mjs` (18) |
| 10 | Telemetry & Observability (Pydantic Logfire & OpenTelemetry) | **E2E** (E2E + Unit + Frontend) | `e2e/test_telemetry_and_timestamps.py` (2 pass, 2 `xfail`), `tests/test_telemetry.py` (10), `ui/tests/header.test.mjs` |
| 11 | 1-Click Zero-Friction Stack Launch | **Config** | `tests/test_launch_automation.py` (23 compose/`run.sh` tests) |
| 12 | Local Model Inference & Active Ollama Lifecycle Management | **Unit** | `tests/test_runner.py` (`test_ensure_ollama_model_*`), `tests/test_config.py::test_ollama_inference_config_completeness` |
| 13 | Non-Agentic Daemons & Automated Naming | **E2E** (E2E + Unit + Frontend) | `e2e/test_daemon_naming.py` (4), `tests/test_daemons.py` (12), `ui/tests/configModal.test.mjs` |
| 14 | Steerable Model Provider & Inspector Queue Editor | **E2E** (E2E + Unit + Frontend) | `e2e/test_inspector_and_steerable.py`, `e2e/test_steerable_conversation.py`, `tests/test_steerable.py` (19), `ui/tests/steerable.test.mjs` (23), `ui/tests/agentInspector.test.mjs` |

## Requirement → Test Mapping

All 50 requirements from [`requirements.md`](./requirements.md) (`REQ-001`–`REQ-052`, excluding unused IDs `REQ-030` and `REQ-031`) are mapped below. Zero requirements remain uncovered.

| Requirement | Highest tier (all tiers) | Confirming tests |
| --- | --- | --- |
| `REQ-001` Modern Python 3.12 Runtime & UV Package Management | **Config** (Unit + Config) | `tests/test_launch_automation.py::test_pyproject_and_uv_lock_require_python_312`, `tests/test_smoke.py::test_version` |
| `REQ-002` Rigorous Code Quality & Static Verification | **Config** | `tests/test_launch_automation.py::test_ci_workflow_runs_static_verification_checks`, `::test_ci_workflow_runs_the_python_and_frontend_suites` |
| `REQ-003` Traceable Architectural & Durable Knowledge Documentation | **Config** | `tests/test_launch_automation.py::test_knowledge_and_decisions_exist_and_use_relative_links` |
| `REQ-004` Config Template Singleton & Derivation | **E2E** (E2E + Unit) | `e2e/test_agents.py::test_agent_creation_derives_its_config_from_the_template`, `::test_agent_creation_applies_config_overrides`, `e2e/test_config_settings_system.py::test_config_template_exposes_the_seeded_template`, `::test_config_template_update_replaces_the_singleton`, `tests/test_config.py` |
| `REQ-005` Hierarchical REST API with Dual Identifier Resolution | **E2E** (E2E + Unit + Frontend) | `e2e/test_agents.py` (10), `e2e/test_agent_lifecycle.py::test_a_generated_agent_can_be_addressed_by_its_slug`, `e2e/test_threads.py` (12), `tests/test_server.py`, `tests/test_resolution.py::test_resolve_session_and_thread`, `ui/tests/useAgentsTree.test.mjs` |
| `REQ-006` Thread Redirection, Event Streaming & Status Tracking | **E2E** (E2E + Unit) | `e2e/test_threads.py::test_thread_status_reports_the_current_status`, `::test_thread_collection_redirects_to_the_open_thread`, `::test_thread_stream_replays_recorded_events`, `e2e/test_steerable_conversation.py::test_thread_stream_replays_history_after_turn`, `::test_session_stream_replays_all_threads`, `tests/test_session_stream.py` (2) |
| `REQ-007` Safe Non-Destructive API Surface | **E2E** (E2E + Unit) | `e2e/test_inspector_and_steerable.py::test_steerable_queue_can_be_replaced_and_cleared`, `e2e/test_agent_lifecycle.py::test_an_agent_update_keeps_the_agent_usable`, `tests/test_server.py::test_no_delete_invariant_on_routes` |
| `REQ-008` Web UI with Navigation Tree, Real-Time Streaming & JSON Config Editor | **Frontend** | `ui/tests/sidebar.test.mjs` (22), `ui/tests/chatArea.test.mjs` (12), `ui/tests/configModal.test.mjs` (21), `ui/tests/header.test.mjs` (7), `ui/tests/useAgentsTree.test.mjs` (12) |
| `REQ-009` Default Session and Open Thread Automatic Creation, Zero-Prompt UX & Auto-Focus | **E2E** (E2E + Unit + Frontend) | `e2e/test_steerable_conversation.py::test_agent_creation_yields_default_session_and_open_thread`, `tests/test_entities.py`, `ui/tests/sidebar.test.mjs`, `ui/tests/chatArea.test.mjs` |
| `REQ-010` Containerized Launch Automation, Safe Service Restart & Clean Reset | **Config** | `tests/test_launch_automation.py` (23 compose and `run.sh` tests) |
| `REQ-011` Inline Tree Node Renaming and Session Node Status Visibility | **Frontend** | `ui/tests/sidebar.test.mjs` (inline edit `<Check />` without `prompt()`, Esc/Enter/clear, status icons across `AgentStatus`) |
| `REQ-012` Logfire Tracing with Agent, Session, and Thread Hierarchical Spans | **E2E** (E2E + Unit) | `e2e/test_telemetry_and_timestamps.py::test_scripted_turn_emits_agent_session_thread_spans`, `tests/test_telemetry.py::test_runner_hierarchical_spans`, `::test_store_entity_lifecycle_spans` |
| `REQ-013` External System Navigation Links & Telemetry Visibility Guard | **E2E** (E2E + Unit + Frontend) | `e2e/test_telemetry_and_timestamps.py::test_api_request_emits_span_but_health_probe_does_not`, `e2e/test_config_settings_system.py::test_system_info_reports_every_integration`, `tests/test_telemetry.py::test_is_logfire_enabled_and_service_name`, `ui/tests/header.test.mjs` |
| `REQ-014` AG-UI Reasoning Exposure & Multi-Turn Trace Message Alignment | **E2E** (E2E + Unit + Frontend) | `e2e/test_steerable_conversation.py::test_scripted_turn_emits_full_event_sequence`, `tests/test_runner.py::test_reasoning_chat_openai_extracts_reasoning_fields`, `::test_runner_reasoning_events_and_replay`, `tests/test_telemetry.py::test_langgraph_multi_turn_no_duplicate_user_message`, `ui/tests/messageItem.test.mjs` |
| `REQ-015` Gitea-Backed Versioned Agent Persistence & Workspace Isolation | **E2E** (E2E + Unit) | `e2e/test_sync_pr_lifecycle.py` (4), `e2e/test_workspace_and_skills.py` (`test_session_workspace_separates_deliverables_from_harness_state`, `test_a_turn_writes_its_deliverable_into_the_data_directory`), `tests/test_workspace.py` (10), `tests/test_persistence_client.py` (19), `tests/test_harness_store_persistence.py` (2) |
| `REQ-016` UI Markdown Rendering | **Frontend** | `ui/tests/markdownRenderer.test.mjs` (12 tests: GFM tables, fenced code blocks with language badge & copy button, variants) |
| `REQ-017` Containerized OpenSandbox Execution & Operational Directory Mount | **E2E** (E2E + Unit) | `e2e/test_workspace_and_skills.py::test_the_workspace_is_read_only_during_the_make_phase`, `::test_the_workspace_is_writable_in_chat_mode`, `tests/test_sandbox.py` (11) |
| `REQ-018` DeepAgent Inspection Console & Branch State Provenance | **E2E** (E2E + Unit + Frontend) | `e2e/test_inspector_and_steerable.py::test_inspect_report_exposes_tools_without_secrets` (+ `::test_inspect_report_reflects_conversation_history` `xfail`), `e2e/test_prompt_composition.py::test_scaffold_and_composite_prompts_differ`, `tests/test_inspector.py` (13), `ui/tests/agentInspector.test.mjs` (18) |
| `REQ-019` Gitea Sync PRs and Thread Acceptance Lifecycle | **E2E** (E2E + Unit) | `e2e/test_session_lifecycle.py::test_thread_acceptance_closes_thread_and_spawns_successor`, `e2e/test_sync_pr_lifecycle.py` (4), `tests/test_server.py::test_accept_thread_endpoint`, `tests/test_workspace.py::test_sync_pr_data_scoped_merge_lifecycle` |
| `REQ-020` Tool Call Lifecycle Visibility & Accurate UI Stream Rendering | **E2E** (E2E + Unit + Frontend) | `e2e/test_steerable_conversation.py::test_scripted_tool_call_executes_and_reports_result`, `tests/test_runner.py::test_tool_call_lifecycle_status_transitions`, `ui/tests/toolCallItem.test.mjs` (13) |
| `REQ-021` Sync PR Diff Inspection and Changes Tab | **E2E** (E2E + Unit + Frontend) | `e2e/test_sync_pr_lifecycle.py::test_sync_pr_diff_exposes_only_data_deliverables`, `tests/test_server.py::test_session_diff_endpoint`, `ui/tests/changesViewer.test.mjs` (16) |
| `REQ-022` Restrict Sync PRs and Thread Acceptance to `data/` Deliverables | **E2E** (E2E + Unit) | `e2e/test_sync_pr_lifecycle.py::test_sync_pr_diff_exposes_only_data_deliverables`, `::test_acceptance_merges_data_deliverable_into_main`, `tests/test_artifacts.py::test_filter_sync_pr_diff_keeps_data_and_artifacts`, `tests/test_workspace.py::test_sync_pr_data_scoped_merge_lifecycle` |
| `REQ-023` Dynamic LM-XML Structured System Prompt Architecture | **E2E** (E2E + Unit) | `e2e/test_prompt_composition.py::test_composite_prompt_is_lm_xml`, `::test_composite_prompt_carries_the_dynamic_context`, `tests/test_prompt.py` (18), `tests/test_modes_and_plan.py::test_system_prompt_lmxml_composition` |
| `REQ-024` Agent Personas and Baseline Archetypes | **Unit** (3 pass + 2 `xfail`) | `tests/test_personas.py` (`test_default_identity_is_the_coder_persona`, `test_default_identity_reaches_the_effective_system_prompt`, `test_custom_instructions_are_appended_to_the_system_prompt`; configurable persona field pinned by 2 non-strict `xfail` tests) |
| `REQ-025` Operational Modes and Thread Transition Triggers | **E2E** (E2E + Unit) | `e2e/test_plan_lifecycle.py::test_discuss_to_make_transition_creates_new_thread`, `e2e/test_session_lifecycle.py::test_mode_switch_spawns_new_thread_and_closes_plan`, `e2e/test_prompt_composition.py::test_prompt_reflects_the_operational_mode`, `tests/test_modes_and_plan.py` (8) |
| `REQ-026` Exact Turn-Level Session Branching and Lineage Provenance | **E2E** (E2E + Unit + Frontend) | `e2e/test_session_lifecycle.py` (4 branching & lineage tests), `tests/test_session_branching_and_lifecycle.py` (17), `ui/tests/messageItem.test.mjs` |
| `REQ-027` Terminal Session Lifecycle States and Teardown Guard | **E2E** (E2E + Unit) | `e2e/test_session_lifecycle.py::test_killed_session_rejects_further_input`, `::test_killed_session_cannot_switch_mode`, `tests/test_session_branching_and_lifecycle.py::test_kill_session_mid_tool_cleans_up_and_errors`, `::test_kill_session_while_thinking_cleans_up_and_errors` |
| `REQ-028` Automated Continuous Integration via GitHub Actions | **Config** | `tests/test_launch_automation.py::test_ci_workflow_runs_the_python_and_frontend_suites`, `::test_ci_workflow_runs_static_verification_checks`, `::test_ci_workflow_runs_the_end_to_end_suite` |
| `REQ-029` Task Planning, Progress Tracking, and TodoList Middleware Integration | **E2E** (E2E + Unit + Frontend) | `e2e/test_harness_tools.py` (5 todo tool tests), `e2e/test_capability_gating.py::test_disabling_the_todo_middleware_removes_the_todo_tools`, `::test_disabling_the_todo_middleware_is_reported_by_the_inspector`, `tests/test_todos.py` (8), `ui/tests/agentInspector.test.mjs`, `ui/tests/configModal.test.mjs` |
| `REQ-032` UI URL State Synchronization, Live Refresh, and Verbose Error Diagnostics | **E2E** (E2E + Unit + Frontend) | `e2e/test_error_diagnostics.py` (3 pass + 2 `xfail`), `tests/test_runner.py::test_session_agent_runner_unhandled_error_includes_type_and_traceback`, `ui/tests/chatArea.test.mjs`, `ui/tests/useAgentsTree.test.mjs` (12) |
| `REQ-033` Mature A2UI Subset Artifact Model, Opinionated Persistence, and Atomic Generation | **E2E** (E2E + Unit + Frontend) | `e2e/test_plan_lifecycle.py`, `e2e/test_a2ui_validation.py`, `e2e/test_artifact_routes.py` (9 pass, 1 `xfail`), `e2e/test_capability_gating.py::test_artifact_tools_are_bound_by_default`, `tests/test_artifacts.py` (39), `ui/tests/a2uiArtifactRenderer.test.mjs` (13) |
| `REQ-034` Operational Modes, Multi-Phase Plan Lifecycle, Tabbed Plan Artifacts, and Recursion Limit | **E2E** (E2E + Unit) | `e2e/test_plan_lifecycle.py::test_make_plan_creates_plan_artifact_on_disk`, `::test_proceed_advances_to_execute_phase`, `::test_workspace_is_read_only_during_make_phase`, `tests/test_modes_and_plan.py` (8), `tests/test_runner.py::test_session_agent_runner_recursion_limit_configuration` |
| `REQ-035` OpenBao Secrets Vault Integration, Per-Inference Version Watching, and Checkpoint Explosion | **E2E** (E2E + Unit + Frontend) | `e2e/test_vault.py` (8), `tests/vault/test_client_and_interpolator.py` (8), `tests/vault/test_parser.py` (11), `tests/test_vault_routes.py` (4), `ui/tests/configModal.test.mjs`, `ui/tests/settingsModal.test.mjs` |
| `REQ-036` Mount External Git Repositories into Agent Sandboxes with Dual-Index Persistence | **E2E** (E2E + Unit) | `e2e/test_external_repos.py` (6), `tests/test_external_repos.py` (8) |
| `REQ-037` Real-Time Interactive Web Terminal & Shell Emulator for Agent Sandbox | **E2E** (E2E + Unit + Frontend) | `e2e/test_terminal_stream.py` (6), `tests/test_terminal.py` (5), `ui/tests/terminalView.test.mjs` (13) |
| `REQ-038` Ollama Local Model Provider Support & Active Model Execution Management | **Unit** | `tests/test_runner.py` (`test_ensure_ollama_model_*`), `tests/test_config.py::test_ollama_inference_config_completeness` |
| `REQ-039` Non-Agentic Daemons & Geometric Stepback Thread/Session Naming | **E2E** (E2E + Unit + Frontend) | `e2e/test_daemon_naming.py` (4), `tests/test_daemons.py` (12), `ui/tests/configModal.test.mjs` |
| `REQ-040` Deterministic Agent Slug Generation via Coolname | **E2E** (E2E + Unit) | `e2e/test_agent_lifecycle.py::test_an_unnamed_agent_receives_a_generated_slug`, `::test_a_named_agent_keeps_its_name`, `tests/test_daemons.py::test_agent_coolname_slug_generation_and_fallback` |
| `REQ-041` Configuration Model and UI Symmetry Across Scopes | **E2E** (E2E + Unit + Frontend) | `e2e/test_config_settings_system.py`, `e2e/test_agent_lifecycle.py::test_the_update_is_persisted_with_the_session`, `::test_an_incomplete_update_is_rejected`, `e2e/test_prompt_composition.py::test_custom_instructions_reach_the_composite_prompt`, `tests/test_config.py` (14), `ui/tests/configModal.test.mjs` (21), `ui/tests/settingsModal.test.mjs`, `ui/tests/header.test.mjs` |
| `REQ-042` Dynamic Workspace and Project Context Discovery and LM-XML Prompt Injection | **E2E** (E2E + Unit) | `e2e/test_prompt_composition.py::test_discovered_context_file_is_injected_into_the_prompt`, `tests/test_prompt.py` (context discovery tests), `tests/test_inspector.py::test_inspector_skills_discovery_and_project_rules` |
| `REQ-043` Native LM-XML Skills System with Explicit Load/Unload Tools | **E2E** (E2E + Unit + Frontend) | `e2e/test_capability_gating.py` (3 skills gating tests), `e2e/test_harness_tools.py` (3 `load_skill`/`unload_skill` tests), `e2e/test_workspace_and_skills.py`, `tests/test_skills.py` (6), `tests/test_bundled_skills.py` (6), `ui/tests/agentInspector.test.mjs`, `ui/tests/settingsModal.test.mjs` |
| `REQ-044` Web Search Capability & Enum Configuration Guard | **E2E** (E2E + Unit + Frontend) | `e2e/test_web_search_tools.py` (2), `e2e/test_capability_gating.py` (2 web search tests), `e2e/test_harness_tools.py::test_web_search_tool_is_bound_to_the_agent`, `tests/test_web_search.py` (13), `ui/tests/agentInspector.test.mjs`, `ui/tests/configModal.test.mjs` |
| `REQ-045` Chat Bubble Timestamps and Autonomous Sequence Indexing | **E2E (`xfail`)** + **Frontend** | `e2e/test_telemetry_and_timestamps.py` (2 `xfail` pinning unimplemented backend timestamps), `ui/tests/sequenceSource.test.mjs` (14), `ui/tests/sequence.test.mjs` (10), `ui/tests/messageItem.test.mjs` |
| `REQ-046` Adaptive UI (A2UI) v1.0 Specification Upgrade & Strict UAX #31 Identifier Validation | **E2E** (E2E + Unit) | `e2e/test_a2ui_validation.py` (`test_an_invalid_component_identifier_is_normalized`, `test_an_unknown_component_type_is_rejected`, `test_a_dangling_child_reference_is_rejected`, `test_an_empty_component_list_is_rejected`), `tests/test_artifacts.py::test_uax31_identifier_normalization_and_validation` |
| `REQ-047` Configurable Model Reasoning Effort Tiers | **Unit** (Unit + Frontend) | `tests/test_reasoning_effort.py` (16 parametrized/unit cases), `ui/tests/configModal.test.mjs` (4 `REQ-047` tests) |
| `REQ-048` Semantic Tool Categorization, Color Labeling & Filtering in Agent Inspector | **Unit** (Unit + Frontend) | `tests/test_inspector.py::test_tool_labeling_resource_and_labels`, `ui/tests/agentInspector.test.mjs` (semantic label badge, category filter, schema reveal) |
| `REQ-049` Cross-Phase Retained Skills Continuity Across Thread Rollovers | **E2E** (E2E + Unit) | `e2e/test_workspace_and_skills.py::test_a_retained_skill_survives_a_phase_transition`, `tests/test_skills.py::test_skill_stashing_across_thread_creation` |
| `REQ-050` Configurable Artifacts Implementation Toggle & Gating Guard | **E2E** (E2E + Unit + Frontend) | `e2e/test_capability_gating.py` (`test_disabling_artifacts_removes_the_artifact_tools`, `test_disabling_artifacts_keeps_the_plan_lifecycle_tools`, `test_disabling_artifacts_is_reported_by_the_inspector`), `tests/test_modes_and_plan.py::test_available_harness_tools_resolution_artifacts_none`, `tests/test_bundled_skills.py::test_bundled_skills_excluded_when_artifacts_implementation_none`, `ui/tests/configModal.test.mjs` |
| `REQ-051` Steerable (Scripted) Model Provider & Inspector Queue Editor | **E2E** (E2E + Unit + Frontend) | `e2e/test_inspector_and_steerable.py` (steerable tests), `e2e/test_steerable_conversation.py::test_agent_and_daemon_queues_are_independent`, `tests/test_steerable.py` (19), `ui/tests/steerable.test.mjs` (23), `ui/tests/agentInspector.test.mjs` |
| `REQ-052` Deterministic End-to-End Test Coverage of Features, Requirements, and Invariants | **E2E** (E2E + Config) | `tests/e2e/` (158 deterministic tests), `e2e/test_steerable_conversation.py::test_repeated_scripted_scenarios_are_deterministic`, `tests/test_launch_automation.py::test_ci_workflow_runs_the_end_to_end_suite` |

## Invariant → Test Mapping

All 61 invariants from [`invariants.md`](./invariants.md) (`INV-001`–`INV-063`, excluding unused IDs `INV-037` and `INV-038`) are mapped below. Zero invariants remain uncovered.

| Invariant | Highest tier (all tiers) | Confirming tests |
| --- | --- | --- |
| `INV-001` UV and Python 3.12 Consistency | **Config** | `tests/test_launch_automation.py::test_pyproject_and_uv_lock_require_python_312` |
| `INV-002` Zero Tooling Check Failures | **Config** | `tests/test_launch_automation.py::test_ci_workflow_runs_static_verification_checks` |
| `INV-003` Knowledge Synchronization | **Config** | `tests/test_launch_automation.py::test_knowledge_and_decisions_exist_and_use_relative_links` |
| `INV-004` Config Completeness Invariant | **E2E** (E2E + Unit) | `e2e/test_agent_lifecycle.py::test_an_incomplete_update_is_rejected`, `e2e/test_config_settings_system.py::test_config_template_update_rejects_an_invalid_payload`, `tests/test_config.py::test_agent_config_completeness` |
| `INV-005` Single Open Thread Invariant | **E2E** (E2E + Unit) | `e2e/test_threads.py::test_thread_creation_reuses_an_empty_open_thread`, `::test_thread_creation_closes_a_non_empty_open_thread`, `e2e/test_steerable_conversation.py::test_agent_creation_yields_default_session_and_open_thread`, `tests/test_entities.py::test_session_single_open_thread_invariant` |
| `INV-006` Slug Format and Scope Uniqueness | **E2E** (E2E + Unit) | `e2e/test_agent_lifecycle.py::test_two_agents_never_share_a_generated_slug`, `e2e/test_agents.py::test_agent_creation_rejects_a_duplicate_name`, `::test_agent_update_rejects_a_duplicate_name`, `e2e/test_threads.py::test_thread_creation_rejects_a_duplicate_name`, `tests/test_entities.py`, `tests/test_harness_store.py` |
| `INV-007` No Resource Deletion Invariant | **E2E** (E2E + Unit) | `e2e/test_inspector_and_steerable.py::test_steerable_queue_can_be_replaced_and_cleared`, `tests/test_server.py::test_no_delete_invariant_on_routes` |
| `INV-008` UI Client-Side Busy Guard | **Frontend** | `ui/tests/chatArea.test.mjs` (composer/send disabled when busy or closed, no POST while busy, `ERROR` not treated as busy) |
| `INV-009` Default Session and Open Thread Creation | **E2E** (E2E + Unit) | `e2e/test_steerable_conversation.py::test_agent_creation_yields_default_session_and_open_thread`, `tests/test_entities.py` |
| `INV-010` Entity Display Name Fallback | **Frontend** | `ui/tests/sidebar.test.mjs` (4 `INV-010` tests: unnamed/blank agent, session, and thread fall back to full UUID) |
| `INV-011` Zero-Prompt Creation and Auto-Focus Invariant | **Frontend** | `ui/tests/chatArea.test.mjs` (2 `INV-011` composer auto-focus tests), `ui/tests/sidebar.test.mjs` (`creating an agent and a session never prompts for a name`) |
| `INV-012` User Message Event Recording & Replay Invariant | **E2E** (E2E + Unit) | `e2e/test_steerable_conversation.py::test_thread_stream_replays_history_after_turn`, `::test_session_stream_replays_all_threads`, `e2e/test_threads.py::test_thread_stream_replays_recorded_events`, `tests/test_session_stream.py`, `tests/test_server.py::test_thread_switching_replays_user_messages` |
| `INV-013` Inline Tree Editing & Session Status Invariant | **Frontend** | `ui/tests/sidebar.test.mjs` (no `prompt()` call, inline `<Check />` editing, standard session status icons including terminal overrides) |
| `INV-014` Hierarchical Agent-Session-Thread Execution Spans | **E2E** (E2E + Unit) | `e2e/test_telemetry_and_timestamps.py::test_scripted_turn_emits_agent_session_thread_spans`, `tests/test_telemetry.py::test_runner_hierarchical_spans`, `::test_store_entity_lifecycle_spans` |
| `INV-015` External System Link Visibility & Telemetry Guard | **E2E** (E2E + Unit + Frontend) | `e2e/test_telemetry_and_timestamps.py::test_api_request_emits_span_but_health_probe_does_not`, `e2e/test_config_settings_system.py::test_system_info_reports_every_integration`, `tests/test_telemetry.py::test_is_logfire_enabled_and_service_name`, `ui/tests/header.test.mjs` |
| `INV-016` AG-UI Reasoning Stream & Multi-Turn Span Message Alignment | **E2E** (E2E + Unit + Frontend) | `e2e/test_steerable_conversation.py::test_scripted_turn_emits_full_event_sequence`, `tests/test_runner.py::test_reasoning_chat_openai_extracts_reasoning_fields`, `tests/test_telemetry.py::test_langgraph_multi_turn_no_duplicate_user_message`, `ui/tests/messageItem.test.mjs` |
| `INV-017` Git-Tracked Agent Workspace & Config Boundary | **E2E** (E2E + Unit) | `e2e/test_workspace_and_skills.py::test_session_workspace_separates_deliverables_from_harness_state`, `tests/test_workspace.py` (10) |
| `INV-018` Atomic Checkpoint Data & State Persistence & Commit Delineation | **E2E** (E2E + Unit) | `e2e/test_workspace_and_skills.py::test_session_configuration_is_persisted_next_to_the_deliverables`, `::test_a_turn_writes_its_deliverable_into_the_data_directory`, `tests/test_checkpointer.py` (4), `tests/test_workspace.py::test_session_workspace_and_checkpoint_commits` |
| `INV-019` Client-Side Markdown Rendering & Content Safety | **Frontend** | `ui/tests/markdownRenderer.test.mjs` (5 `INV-019` tests: external `target="_blank" rel="noopener noreferrer"`, protocol-relative, relative links, unsafe URL schemes, raw HTML sanitization) |
| `INV-020` Runtime-Managed OpenSandbox Authentication | **Unit** | `tests/test_sandbox.py::test_get_or_create_sandbox_api_key_autogenerates_and_reuses`, `::test_get_or_create_sandbox_api_key_prefers_env_var` |
| `INV-021` Agent Inspection & Credential Redaction Invariant | **E2E** (E2E + Unit + Frontend) | `e2e/test_inspector_and_steerable.py::test_inspect_report_exposes_tools_without_secrets` (+ `::test_inspect_report_reflects_conversation_history` `xfail`), `tests/test_inspector.py`, `ui/tests/agentInspector.test.mjs` |
| `INV-022` Thread Acceptance and Sync PR Lifecycle | **E2E** (E2E + Unit) | `e2e/test_session_lifecycle.py::test_thread_acceptance_closes_thread_and_spawns_successor`, `e2e/test_sync_pr_lifecycle.py::test_session_creation_opens_sync_pr`, `::test_thread_acceptance_merges_sync_pr_and_renews_it`, `tests/test_workspace.py::test_sync_pr_workspace_operations` |
| `INV-023` Tool Call Lifecycle and State Representation | **E2E** (E2E + Unit + Frontend) | `e2e/test_steerable_conversation.py::test_scripted_tool_call_executes_and_reports_result`, `tests/test_runner.py::test_tool_call_lifecycle_status_transitions`, `ui/tests/toolCallItem.test.mjs` (13) |
| `INV-024` Session Changes Diff and Acceptance Placement | **E2E** (E2E + Unit + Frontend) | `e2e/test_sync_pr_lifecycle.py::test_sync_pr_diff_exposes_only_data_deliverables`, `tests/test_server.py::test_session_diff_endpoint`, `ui/tests/changesViewer.test.mjs` (5 `INV-024` Accept placement & busy/closed guard tests) |
| `INV-025` Scope Sync PRs and Thread Acceptance Merges to `data/` Deliverables | **E2E** (E2E + Unit) | `e2e/test_sync_pr_lifecycle.py::test_sync_pr_diff_exposes_only_data_deliverables`, `::test_acceptance_merges_data_deliverable_into_main`, `tests/test_artifacts.py::test_filter_sync_pr_diff_keeps_data_and_artifacts` |
| `INV-026` Test Suite Persistence and Host Workspace Isolation | **E2E** (E2E + Unit) | `tests/e2e/conftest.py` (per-test isolated stores and workspace roots), `tests/conftest.py` |
| `INV-027` LM-XML Dynamic System Prompt Assembly | **E2E** (E2E + Unit) | `e2e/test_prompt_composition.py::test_composite_prompt_is_lm_xml`, `tests/test_prompt.py` (18) |
| `INV-028` Mode Transition Thread-Spawning Boundary | **E2E** (E2E + Unit) | `e2e/test_plan_lifecycle.py::test_discuss_to_make_transition_creates_new_thread`, `e2e/test_session_lifecycle.py::test_mode_switch_spawns_new_thread_and_closes_plan`, `::test_branch_preserves_mode_and_phase`, `e2e/test_threads.py::test_thread_creation_reuses_an_empty_open_thread`, `tests/test_modes_and_plan.py` |
| `INV-029` Session Terminal Immutability & Resource Teardown | **E2E** (E2E + Unit) | `e2e/test_session_lifecycle.py::test_killed_session_rejects_further_input`, `::test_killed_session_cannot_switch_mode`, `tests/test_session_branching_and_lifecycle.py::test_kill_session_mid_tool_cleans_up_and_errors`, `::test_kill_session_while_thinking_cleans_up_and_errors` |
| `INV-030` Session Branching Turn Isolation & Provenance Tracking | **E2E** (E2E + Unit + Frontend) | `e2e/test_session_lifecycle.py` (4 branching tests), `tests/test_session_branching_and_lifecycle.py::test_granular_branch_before_and_after_tool_calls_and_reasoning`, `ui/tests/messageItem.test.mjs` |
| `INV-031` Read-Only System Skill Sandboxing & Clean Missing Directory Handling | **E2E** (E2E + Unit) | `e2e/test_workspace_and_skills.py::test_the_sandbox_receives_the_session_skill_mounts`, `tests/test_sandbox.py::test_sandbox_build_skill_volumes_read_only`, `::test_sandbox_build_skill_volumes_tilde_expansion_and_missing_skipped` |
| `INV-032` System Repository Persistence Lifecycle | **E2E** (E2E + Unit) | `e2e/test_config_settings_system.py::test_settings_update_is_persisted_in_the_store`, `e2e/test_workspace_and_skills.py::test_session_configuration_is_persisted_next_to_the_deliverables`, `tests/test_workspace.py::test_system_repo_persistence` |
| `INV-033` Configurable Todo and Skills Middleware and System Prompt Composition | **E2E** (E2E + Unit) | `e2e/test_capability_gating.py` (todo & skills toggles), `e2e/test_harness_tools.py`, `tests/test_todos.py` (8), `tests/test_runner.py`, `tests/test_config.py::test_agent_config_todo_and_skills_implementation_validation` |
| `INV-034` Dynamic Session Runner Recompilation on Save | **E2E** (E2E + Unit) | `e2e/test_agent_lifecycle.py::test_updating_the_session_recompiles_the_runner`, `tests/test_runner.py::test_runner_registry_reload_session_runner` |
| `INV-035` Skill Precedence Hierarchy and In-Sandbox Isolation | **E2E** (E2E + Unit) | `e2e/test_workspace_and_skills.py::test_a_session_skill_shadows_the_bundled_skill`, `tests/test_skills.py::test_discover_session_skills_precedence_and_shadowing`, `tests/test_bundled_skills.py::test_bundled_skills_precedence_in_skill_sources` |
| `INV-036` Purposeful Workspace Synchronization & Auto-Pull | **Unit** | `tests/test_workspace.py::test_sync_session_workspace_auto_pulls_external_changes` |
| `INV-039` Verbose `RUN_ERROR` Event Persistence & UI State Synchronization | **E2E** (E2E + Unit + Frontend) | `e2e/test_error_diagnostics.py` (3 pass + 2 `xfail`), `tests/test_runner.py::test_session_agent_runner_unhandled_error_includes_type_and_traceback`, `ui/tests/chatArea.test.mjs`, `ui/tests/useAgentsTree.test.mjs` |
| `INV-040` Artifact Hierarchy, Read-Only Sandboxing, and Atomic Interaction Lifecycle | **E2E** (E2E + Unit) | `e2e/test_plan_lifecycle.py` (blocking questionnaire & click), `e2e/test_session_lifecycle.py::test_mode_switch_closes_open_blocking_questionnaire`, `e2e/test_a2ui_validation.py::test_a_valid_artifact_is_written_to_the_workspace`, `e2e/test_artifact_routes.py` (9 pass, 1 `xfail`), `tests/test_artifacts.py` (39) |
| `INV-041` Operational Mode Mount Policy, Non-Blocking Tabbed Plans, and Recursion Limit | **E2E** (E2E + Unit) | `e2e/test_plan_lifecycle.py::test_workspace_is_read_only_during_make_phase`, `e2e/test_workspace_and_skills.py::test_the_workspace_is_read_only_during_the_make_phase`, `tests/test_modes_and_plan.py::test_notes_directory_and_sandbox_mount_policy`, `tests/test_runner.py::test_session_agent_runner_recursion_limit_configuration` |
| `INV-042` In-Memory Secret Evaluation, Per-Inference Version Watching, and Session Config Explosion | **Unit** (Unit + Frontend) | `tests/vault/test_client_and_interpolator.py` (8), `tests/vault/test_parser.py` (11), `tests/test_vault_routes.py::test_config_template_rejects_version_in_secret_expression`, `ui/tests/settingsModal.test.mjs` |
| `INV-043` External Git Repository Sandbox Isolation, Dual-Index Persistence, and Credential Safety | **E2E** (E2E + Unit) | `e2e/test_external_repos.py` (6), `tests/test_external_repos.py` (8) |
| `INV-044` Multi-Repository Checkpoint Ordering, Atomic Manifest Commit, and Exact Historical Restoration | **Unit** | `tests/test_external_repos.py::test_dual_index_checkpoint_and_restoration` |
| `INV-045` Ephemeral Working-Tree Semantics Across Repository Unmount/Remount | **Unit** | `tests/test_external_repos.py::test_provision_session_working_copy_checks_out_configured_branch` |
| `INV-046` Real-Time Sandbox Terminal Streaming and Working Directory Continuity | **E2E** (E2E + Unit + Frontend) | `e2e/test_terminal_stream.py` (6), `tests/test_terminal.py` (5), `ui/tests/terminalView.test.mjs` (13) |
| `INV-047` Bundled Platform Skills Shared Volume Sandboxing | **E2E** (E2E + Unit) | `e2e/test_workspace_and_skills.py::test_the_bundled_skills_are_discovered`, `::test_the_sandbox_receives_the_session_skill_mounts`, `tests/test_bundled_skills.py` (6) |
| `INV-048` Ollama Healthcheck and Active Model Execution Management | **Unit** | `tests/test_runner.py` (6 `test_ensure_ollama_model_*`), `tests/test_config.py::test_ollama_inference_config_completeness` |
| `INV-049` Non-Agentic Daemon Execution, Geometric Stepback, and Parallel Slug Priority | **E2E** (E2E + Unit) | `e2e/test_daemon_naming.py` (4), `tests/test_daemons.py` (11 daemon tests) |
| `INV-050` Deterministic Agent Slug Generation and Parallel Fallback | **E2E** (E2E + Unit) | `e2e/test_agent_lifecycle.py::test_an_unnamed_agent_receives_a_generated_slug`, `::test_a_named_agent_keeps_its_name`, `::test_two_agents_never_share_a_generated_slug`, `tests/test_daemons.py::test_agent_coolname_slug_generation_and_fallback` |
| `INV-051` Configuration Model and UI Symmetry Across Scopes | **E2E** (E2E + Unit + Frontend) | `e2e/test_config_settings_system.py`, `e2e/test_agent_lifecycle.py`, `tests/test_config.py` (14), `ui/tests/configModal.test.mjs` (21), `ui/tests/settingsModal.test.mjs` |
| `INV-052` Dynamic Workspace and Project Context Discovery and LM-XML Injection | **E2E** (E2E + Unit) | `e2e/test_prompt_composition.py::test_discovered_context_file_is_injected_into_the_prompt`, `tests/test_prompt.py` (context discovery tests) |
| `INV-053` Pure Tag Structure for LM-XML Skills Serialization | **E2E** (E2E + Unit) | `e2e/test_prompt_composition.py::test_discovered_skills_are_serialized_as_pure_tags`, `tests/test_skills.py::test_lmxml_skills_prompt_serialization_no_attributes` |
| `INV-054` Thread-Scoped Active Skills Lifecycle and Dynamic Tool Gating | **E2E** (E2E + Unit) | `e2e/test_capability_gating.py::test_disabling_the_skills_middleware_removes_the_skill_tools`, `::test_a_skill_tool_is_gated_until_the_skill_is_loaded`, `e2e/test_harness_tools.py` (3 skill tool tests), `tests/test_skills.py` |
| `INV-055` Web Search Capability Guard and Dynamic Tool Suppression | **E2E** (E2E + Unit) | `e2e/test_capability_gating.py::test_disabling_web_search_removes_the_web_tools`, `::test_web_search_is_reported_by_the_inspector`, `e2e/test_web_search_tools.py` (2), `tests/test_web_search.py` (13), `tests/test_runner.py::test_runner_get_active_tools_web_search_filtering` |
| `INV-056` Chat Bubble Timestamps and Autonomous Sequence Indexing | **E2E (`xfail`)** + **Frontend** | `e2e/test_telemetry_and_timestamps.py` (2 `xfail`), `ui/tests/sequenceSource.test.mjs` (14), `ui/tests/sequence.test.mjs` (10), `ui/tests/messageItem.test.mjs` |
| `INV-057` A2UI v1.0 UAX #31 Component Identifier and Envelope Invariant | **E2E** (E2E + Unit) | `e2e/test_a2ui_validation.py` (`test_an_invalid_component_identifier_is_normalized`, `test_an_unknown_component_type_is_rejected`, `test_a_dangling_child_reference_is_rejected`, `test_an_empty_component_list_is_rejected`), `tests/test_artifacts.py::test_uax31_identifier_normalization_and_validation` (+ `e2e/test_artifact_routes.py::test_artifact_submit_is_accepted` `xfail`) |
| `INV-058` Model Reasoning Effort Parameter Forwarding Invariant | **Unit** (Unit + Frontend) | `tests/test_reasoning_effort.py` (16 cases: `default` omitted, every non-default tier forwarded verbatim, config reload survival), `ui/tests/configModal.test.mjs` |
| `INV-059` Dynamic Tool Labeling JSON Resource Alignment | **Unit** (Unit + Frontend) | `tests/test_inspector.py::test_tool_labeling_resource_and_labels`, `ui/tests/agentInspector.test.mjs` (badge rendering & category filter) |
| `INV-060` Explicit Thread Skill Retention and Token Leakage Guard | **E2E** (E2E + Unit) | `e2e/test_workspace_and_skills.py::test_a_retained_skill_survives_a_phase_transition`, `tests/test_skills.py::test_skill_stashing_across_thread_creation` |
| `INV-061` Artifacts Implementation Capability Gating and Prompt Sanitization | **E2E** (E2E + Unit) | `e2e/test_capability_gating.py` (`test_disabling_artifacts_removes_the_artifact_tools`, `test_disabling_artifacts_keeps_the_plan_lifecycle_tools`, `test_disabling_artifacts_is_reported_by_the_inspector`), `tests/test_modes_and_plan.py::test_available_harness_tools_resolution_artifacts_none`, `tests/test_bundled_skills.py::test_bundled_skills_excluded_when_artifacts_implementation_none` |
| `INV-062` Steerable Provider Isolation and Credential Freedom | **E2E** (E2E + Unit) | `e2e/test_inspector_and_steerable.py` (5 steerable control tests), `e2e/test_steerable_conversation.py::test_agent_and_daemon_queues_are_independent`, `tests/test_steerable.py` (19) |
| `INV-063` Deterministic End-to-End Test Harness Isolation | **E2E** | `e2e/test_steerable_conversation.py::test_repeated_scripted_scenarios_are_deterministic`, `tests/e2e/conftest.py`, `tests/e2e/stub_sandbox.py` |

## Coverage Summary

| Coverage metric | Requirements (50) | Invariants (61) | Floor ([0058](../decisions/0058-coverage-baseline-and-tiering.md)) |
| --- | --- | --- | --- |
| **Green E2E** | **37 / 50 (74.0%)** | **44 / 61 (72.1%)** | — |
| `xfail`-only E2E (`REQ-045`, `INV-056`) | 1 / 50 (2.0%) | 1 / 61 (1.6%) | — |
| **Combined E2E** | **38 / 50 (76.0%)** | **45 / 61 (73.8%)** | **≥ 60%** (≥ 30 REQs, ≥ 37 INVs) |
| Unit / Frontend / Config only | 12 / 50 (24.0%) | 16 / 61 (26.2%) | — |
| **Uncovered (`None`)** | **0 / 50 (0.0%)** | **0 / 61 (0.0%)** | **0** |

The 12 requirements covered exclusively at Unit / Frontend / Config tiers are `REQ-001`, `REQ-002`,
`REQ-003`, `REQ-008`, `REQ-010`, `REQ-011`, `REQ-016`, `REQ-024`, `REQ-028`, `REQ-038`, `REQ-047`,
and `REQ-048`. The 16 invariants covered exclusively at Unit / Frontend / Config tiers are `INV-001`,
`INV-002`, `INV-003`, `INV-008`, `INV-010`, `INV-011`, `INV-013`, `INV-019`, `INV-020`, `INV-036`,
`INV-042`, `INV-044`, `INV-045`, `INV-048`, `INV-058`, and `INV-059`.

Every requirement and invariant in [`requirements.md`](./requirements.md) and
[`invariants.md`](./invariants.md) appears in exactly one row above — 50 of 50 requirements and
61 of 61 invariants.

## Known Unimplemented / Broken Behaviours Pinned by `xfail`

All 8 non-strict `xfail` tests (`strict=False`) document specified behaviour that is currently
unimplemented or broken in production code and are cross-linked in [`backlog.md`](./backlog.md):

| Test ID | Tier | Gap pinned | Backlog entry |
| --- | --- | --- | --- |
| `tests/e2e/test_artifact_routes.py::test_artifact_submit_is_accepted` | E2E | `/submit` dispatches `"submit"`, whereas generated questionnaires declare `"submit_btn"` | [Artifact Submit Route Dispatches an Undeclared Button ID](./backlog.md#artifact-submit-route-dispatches-an-undeclared-button-id) |
| `tests/e2e/test_error_diagnostics.py::test_a_failing_turn_persists_the_error_type_and_traceback` | E2E | `ag_ui_langgraph` converts provider exceptions into message-only `RunErrorEvent` before outer runner enrichment | [Review and Rethink Error Reporting Architecture and Semantics](./backlog.md#review-and-rethink-error-reporting-architecture-and-semantics) |
| `tests/e2e/test_error_diagnostics.py::test_the_streamed_run_error_exposes_the_error_type` | E2E | Streamed `RUN_ERROR` omits `error_type` for the same reason | [Review and Rethink Error Reporting Architecture and Semantics](./backlog.md#review-and-rethink-error-reporting-architecture-and-semantics) |
| `tests/e2e/test_inspector_and_steerable.py::test_inspect_report_reflects_conversation_history` | E2E | Checkpoint decoder returns no messages (`messages.json` never written), leaving `history.message_count == 0` | [Inspector Conversation History Reconstruction from Checkpoints](./backlog.md#inspector-conversation-history-reconstruction-from-checkpoints) |
| `tests/e2e/test_telemetry_and_timestamps.py::test_events_carry_authoritative_emission_timestamps` | E2E | Backend AG-UI events do not yet stamp an authoritative emission timestamp | [Chat Bubble Timestamps Reflect Client-Side Render Time...](./backlog.md#chat-bubble-timestamps-reflect-client-side-render-time-rather-than-serverllm-event-emission-time) |
| `tests/e2e/test_telemetry_and_timestamps.py::test_streamed_events_expose_timestamps_to_clients` | E2E | Replayed SSE events lack authoritative emission timestamps for the same reason | [Chat Bubble Timestamps Reflect Client-Side Render Time...](./backlog.md#chat-bubble-timestamps-reflect-client-side-render-time-rather-than-serverllm-event-emission-time) |
| `tests/test_personas.py::test_agent_config_exposes_a_configurable_persona` | Unit | `AgentConfig` has no `persona` field yet (`REQ-024`) | [Pluggable Agent Personas](./backlog.md#pluggable-agent-personas-coder-office-worker-designer-etc) |
| `tests/test_personas.py::test_configured_persona_reaches_the_effective_system_prompt` | Unit | System prompt identity is hardcoded to the default Coder archetype (`REQ-024`) | [Pluggable Agent Personas](./backlog.md#pluggable-agent-personas-coder-office-worker-designer-etc) |

## Residual Structural Gaps

1. **Real sandbox container provisioning** — `tests/e2e/` uses `StubSandboxBackend` (`tests/e2e/stub_sandbox.py`); live OpenSandbox container mounts (`/workspace`, `/projects`, read-only skills) are only mocked in `tests/test_sandbox.py`. Tracked in [`backlog.md`](./backlog.md#end-to-end-coverage-of-real-sandbox-container-provisioning).
2. **Gitea-gated Sync PR E2E tests** — the 4 tests in `tests/e2e/test_sync_pr_lifecycle.py` skip under `SEAMUS_TEST_IN_MEMORY=true` and execute only when Gitea persistence is enabled.
3. **React hook pure-reducer seam (`useThreadStream`)** — `useThreadStream` is executed in `ui/tests/chatArea.test.mjs` through `ChatArea` and a scripted SSE `fetch` stub, but edge-case SSE reduction transitions are not yet isolated into a pure reducer test without modifying `ui/src/`. Tracked in [`backlog.md`](./backlog.md#extract-pure-event-reducer-from-usethreadstream-for-direct-unit-testing).
4. **Live model / Ollama / browser automation** — real LLM inference, live Ollama daemon calls (`tests/test_runner.py` uses mocks), and full Playwright browser DOM/CSS layout remain outside this baseline by design.

## Cross-References

- [0058-coverage-baseline-and-tiering.md](../decisions/0058-coverage-baseline-and-tiering.md) — tier definitions, zero-uncovered & ≥60% E2E floors, and `xfail` policy
- [0057-e2e-test-suite.md](../decisions/0057-e2e-test-suite.md) — creation of the deterministic end-to-end suite
- [requirements.md](./requirements.md) — `REQ-052` defines end-to-end coverage requirements
- [invariants.md](./invariants.md) — `INV-063` defines deterministic E2E isolation
- [backlog.md](./backlog.md) — open work items and `xfail`-tracked implementation gaps
