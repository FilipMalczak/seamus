# Architecture

High-level architecture, components, responsibilities, dependencies, and boundaries.

## System Overview

Seamus is a deep agent harness engineered for full developer ownership, inspection, and customization. It provides the execution harness, tool mediation, memory/context structures, and agent lifecycle management over DeepAgent.

```
+---------------------------------------------------------------------------------+
|                                     Seamus                                      |
|                                                                                 |
|  +---------------------------------------------------------------------------+  |
|  |                             React Web UI                                  |  |
|  |         [Sidebar Navigation Tree]  <--->  [Real-Time Chat & Tool Cards]   |  |
|  |         [In-Browser JSON Config Editor Modal]                             |  |
|  +---------------------------------------------------------------------------+  |
|                                       | (HTTP REST & SSE Stream)                |
|                                       v                                         |
|  +---------------------------------------------------------------------------+  |
|  |                             FastAPI Server                                |  |
|  |                       (Prefix: /api/v-alpha/)                             |  |
|  |   +---------------------+   +---------------------+   +---------------+   |  |
|  |   |   Config Template   |   |   Agents & Sessions |   | Threads & SSE |   |  |
|  |   +---------------------+   +---------------------+   +---------------+   |  |
|  +---------------------------------------------------------------------------+  |
|                                       |                                         |
|                                       v                                         |
|  +---------------------------------------------------------------------------+  |
|  |                             Domain & Store                                |  |
|  |    Agent (UUID/Slug)  --->   Session (UUID/Slug)  --->  Thread (UUID/Slug) |  |
|  |    Complete Config           Copied Config              Single Open Thread|  |
|  +---------------------------------------------------------------------------+  |
|                                       |                                         |
|                                       v                                         |
|  +---------------------------------------------------------------------------+  |
|  |                          Harness & Execution                              |  |
|  |    SessionAgentRunner  --->  DeepAgent (GitCheckpointSaver)               |  |
|  |    SeamusOpenSandboxBackend  --->  OpenSandbox Server (Containerized)     |  |
|  |    AG-UI Event Broadcaster (Pub-Sub & History Replay)                     |  |
|  +---------------------------------------------------------------------------+  |
+---------------------------------------------------------------------------------+
```

## Component Boundaries

1. **Web User Interface (`ui`)**:
   - Location: `ui/`
   - Responsibility: React 19 single-page application built with Vite and TypeScript. Arranged with a draggable split resizer defaulting to a 1:2 proportion (`33.33%` sidebar / `66.67%` main panel) between the navigation sidebar tree (with external system integration footer) and the main panel, with boundary clamping, double-click 1:2 reset, and local storage preference persistence. Synchronizes the active agent, session, thread, and main panel tab with URL query parameters (`?agent=...&session=...&thread=...&tab=...`) supporting deep-linking and browser history navigation. Houses top-level workspace tabs (`[Chat] | [Inspector] | [Changes]` plus dynamic tabbed artifacts such as `[Plan]` and `[Form]`), multiline wrapping breadcrumb top bar with mode switcher (`Chat` | `Plan`) and thread mode badge, sidebar thread items with left-aligned badges (`<icon><label><ID or name>`), conversational message pane with client-side Markdown rendering (GFM, code blocks with copy-to-clipboard, safe external links, and table overflow protection), expandable verbose error diagnostics panel, inline interactive A2UI subset artifact rendering (`A2UIArtifactRenderer`) for questionnaires with blocking conversation cadence and dedicated tabs for non-blocking artifacts (forms and plans with interactive Proceed and inline comment review actions), DeepAgent Inspector (displaying composite/scaffold system prompts, tool schemas, inference runtime parameters, active todos checklist, and message trajectory), Changes diff tab separating workspace deliverables from formatted artifact diffs with diff/rendered toggles and locked closed states, automatic live diff and tree state polling during active runs, SSE streaming client, and a dual-mode (`Form` | `Raw JSON`) configuration editor (`ConfigModal`).
2. **Configuration (`seamus.config`)**:
   - Location: `src/seamus/config/`
   - Responsibility: `InferenceConfig`, `AgentConfig`, `SystemSettings` (system-wide skill directories), and persistent stores (`ConfigTemplateStore`, `SystemSettingsStore`) backed by Gitea repository `system` with first-run defaults.
3. **Domain Entities (`seamus.domain`)**:
   - Location: `src/seamus/domain/`
   - Responsibility: Models for `Agent` (configured with `Persona`), `Session` (workspace branch, `active_plan_id`), `Thread` (executing in specific operational `Mode` and `PlanPhase`), and `AgentStatus`. Dual-resolution logic mapping UUIDs and slugs to entities. Enforces lifecycle boundaries where mode switches trigger thread closures and spawn new threads, with empty-thread reuse to prevent orphaned threads. Declarative mode descriptors in `seamus.domain.modes` (`CHAT_MODE`, `PLAN_MODE` with `discuss`, `make`, `execute` phases) and container mount policies (`MountPolicy`).
4. **Harness & Runner (`seamus.harness`)**:
   - Location: `src/seamus/harness/`
   - Responsibility: In-memory store repository with Gitea hydration, `SessionAgentRunner` wrapping `create_deep_agent` with Anthropic skills integration (`SkillsMiddleware`), task planning integration (`TodoListMiddleware` / `write_todos` conditionally enabled by `todo_implementation`), structured LM-XML system prompt engineering (`seamus.harness.prompt`) adapting to active Persona, Mode, and Plan phase with per-inference `DynamicSystemPromptMiddleware`, dynamic graph reloading (`reload_config`) via `RunnerRegistry`, `SeamusOpenSandboxBackend` integrating `langchain-sandbox-opensandbox` (`OpenSandboxBackend`) with a containerized local `opensandbox-server`, mounting `/workspace` (read-write in `chat`, `plan/discuss`, and `plan/execute`; read-only in `plan/make`) with unconstrained notes and specification organization in `/workspace`, system skill directories (read-only at `/skills/system/{idx}`), `ReasoningChatOpenAI`, `SeamusLangGraphAgent` configured with `DEFAULT_RECURSION_LIMIT` (default 250, overridable via `SEAMUS_RECURSION_LIMIT`), agent inspector service (`seamus.harness.inspector`) for semi-live runtime and branch state extraction (including active `todos` and deduplicated workspace file listings), tabbed non-blocking A2UI plan artifacts (`seamus.harness.artifacts.PlanBuilder`) with proceed transition, and event broadcasting/replay queues. Enforces a multi-tiered skill precedence hierarchy: future immutable bundled platform skills (`/skills/bundled`) > visible session skills (`/workspace/skills`) > background session skills (`/workspace/.skills`) > future auxiliary project skills (`/projects/<repo>/skills` then `.skills`) > system-wide defaults in descending index priority (`system[0]` > `system[1]` ... > `system[last]`). DeepAgents sources are ordered from lowest to highest priority to uphold this hierarchy via "last one wins" collision resolution.
5. **Persistence & Git Workspace (`seamus.persistence`)**:
   - Location: `src/seamus/persistence/`
   - Responsibility: Gitea REST API client (`GiteaClient`), workspace clone/branch management (`GitWorkspaceManager`), and checkpoint-driven Git commits (`GitCheckpointSaver`). Maintains strict separation between `agent/config/`, `agent/state/`, and agent-accessible `data/` (mounted into the OpenSandbox container at `/workspace`). Enforces purposeful workspace synchronization (`sync_session_workspace`) via auto-pull rebase upon session checkout and prior to each inference turn loop, ensuring external authorized modifications (such as admin intervention or manual skill provisioning) immediately reflect in the container. Orchestrates dedicated `system` Git repository (`settings.json`, `config-template.json`) and Gitea Sync PR lifecycle (`open_sync_pr`, `merge_sync_pr`) linking session branches to `main` with merges strictly scoped to `data/` deliverables. Persists thread events (`events.json`), checkpoints/HITL state (`checkpoints.json`), and human-readable messages (`messages.json`), with git commit provenance extraction.
6. **Server & REST API (`seamus.server`)**:
   - Location: `src/seamus/server/`
   - Responsibility: FastAPI application factory mounted at `/api/v-alpha/`, Pydantic request/response schemas, routes for config template, system settings (`/api/v-alpha/settings`), agents, sessions, agent inspection (`/api/v-alpha/agent/{agent}/session/{session}/inspect`), session diff inspection (`/api/v-alpha/agent/{agent}/session/{session}/diff`), thread acceptance (`/api/v-alpha/agent/{agent}/session/{session}/thread/{thread}/accept`), input dispatch, thread redirection, system integration metadata (`/api/v-alpha/system/info`), and SSE streaming (thread-level `/thread/{thread}` and session-level `/session/{session}/stream`). Optionally serves built `ui/dist` bundle in production.
7. **Telemetry & Observability (`seamus.telemetry`)**:
   - Location: `src/seamus/telemetry.py`
   - Responsibility: Logfire initialization, evaluation of `LOGFIRE_SEND_TO_LOGFIRE`, custom domain scrubbing (preserving `session`), FastAPI request instrumentation with `/health` exclusions, and OpenTelemetry environment setup for LangChain/LangGraph tracing.
8. **Decisions (`decisions`)**:
   - Location: `decisions/`
   - Responsibility: Append-only architectural and project direction decision records.
9. **Knowledge (`knowledge`)**:
   - Location: `knowledge/`
   - Responsibility: Durable conceptual, architectural, and requirement specifications.
10. **Test Infrastructure & Isolation (`tests`)**:
   - Location: `tests/`
   - Responsibility: Test suites verifying unit, component, and persistence logic. `tests/conftest.py` orchestrates an ephemeral, SQLite-backed Gitea container fixture with dynamic port allocation and temporary workspace root, isolating the test suite from live development environments and enabling collision-free parallel execution.
11. **Artifact Subsystem & Bundled Skills (`seamus.harness.artifacts`, `seamus.skills.bundled`)**:
   - Location: `src/seamus/harness/artifacts.py`, `src/seamus/domain/artifacts.py`, `src/seamus/skills/bundled/`
   - Responsibility: Persistence, validation, and auto-synthesis of A2UI subset renderable artifacts under `<session_workspace>/artifacts/<family>/<uuid>/` (`manifest.json`, `body.json`, `state.json`, `closed.marker`, `interactions/<button_id>.json`). Houses atomic builders (`make_artifact`, `make_questionnaire`, `make_form`, `make_plan`), pre-render surface validation (`validate_a2ui_surface`), static structure warning checks (`check_a2ui_surface_warnings`), loose component tree normalization and auto-repair with mutation logging (`normalize_a2ui_components`, `auto_declare_manifest_buttons`), and agent tools (`wait_for_click`). Manages `/skills/bundled` mounted read-only into OpenSandbox containers at highest priority, backed by shared workspace volume storage in containerized setups.

## Cross-References
- [0001-project-initialization.md](../decisions/0001-project-initialization.md)
- [0002-harness-server-mvp.md](../decisions/0002-harness-server-mvp.md)
- [0003-react-web-ui.md](../decisions/0003-react-web-ui.md)
- [0004-inline-tree-editing-session-status.md](../decisions/0004-inline-tree-editing-session-status.md)
- [0036-mount-bundled-skills-via-shared-volume.md](../decisions/0036-mount-bundled-skills-via-shared-volume.md)
- [0037-validate-a2ui-surface-render-on-make-artifact.md](../decisions/0037-validate-a2ui-surface-render-on-make-artifact.md)
- [0038-a2ui-root-component-and-incomplete-structure-warning.md](../decisions/0038-a2ui-root-component-and-incomplete-structure-warning.md)
- [0005-logfire-integration.md](../decisions/0005-logfire-integration.md)
- [0006-external-system-links.md](../decisions/0006-external-system-links.md)
- [0007-agui-reasoning-and-trace-messages.md](../decisions/0007-agui-reasoning-and-trace-messages.md)
- [0008-git-persistence.md](../decisions/0008-git-persistence.md)
- [0009-ui-markdown-renderer.md](../decisions/0009-ui-markdown-renderer.md)
- [0010-opensandbox-filesystem-sandboxing.md](../decisions/0010-opensandbox-filesystem-sandboxing.md)
- [0011-agent-inspector.md](../decisions/0011-agent-inspector.md)
- [0012-sync-prs-and-thread-accept.md](../decisions/0012-sync-prs-and-thread-accept.md)
- [0013-tool-call-lifecycle-ui.md](../decisions/0013-tool-call-lifecycle-ui.md)
- [0014-SUPERSEDED-ui-layout-proportions-breadcrumbs.md](../decisions/0014-SUPERSEDED-ui-layout-proportions-breadcrumbs.md)
- [0015-session-changes-diff-tab.md](../decisions/0015-session-changes-diff-tab.md)
- [0016-sync-pr-data-scope.md](../decisions/0016-sync-pr-data-scope.md)
- [0017-dedicated-test-gitea.md](../decisions/0017-dedicated-test-gitea.md)
- [0018-dynamic-system-prompt-architecture.md](../decisions/0018-dynamic-system-prompt-architecture.md)
- [0019-threads-modes-personas-architecture.md](../decisions/0019-threads-modes-personas-architecture.md)
- [0023-github-actions-ci-pipeline.md](../decisions/0023-github-actions-ci-pipeline.md)
- [0024-anthropic-skills-and-system-settings.md](../decisions/0024-anthropic-skills-and-system-settings.md)
- [0025-todo-list-middleware.md](../decisions/0025-todo-list-middleware.md)
- [0026-in-sandbox-skill-mount-paths.md](../decisions/0026-in-sandbox-skill-mount-paths.md)
- [0027-skills-config-project-rules-and-inspector.md](../decisions/0027-skills-config-project-rules-and-inspector.md)
- [0028-ui-ux-ergonomics-and-url-state.md](../decisions/0028-ui-ux-ergonomics-and-url-state.md)
- [0030-operational-modes-and-plan-mode.md](../decisions/0030-operational-modes-and-plan-mode.md)
- [0031-SUPERSEDED-migrate-a2ui-to-adaptive-cards.md](../decisions/0031-SUPERSEDED-migrate-a2ui-to-adaptive-cards.md)
- [0034-mature-a2ui-artifacts-model.md](../decisions/0034-mature-a2ui-artifacts-model.md)
- [0037-validate-a2ui-surface-render-on-make-artifact.md](../decisions/0037-validate-a2ui-surface-render-on-make-artifact.md)
- [0038-a2ui-root-component-and-incomplete-structure-warning.md](../decisions/0038-a2ui-root-component-and-incomplete-structure-warning.md)
- [0039-loose-artifact-normalization-and-mutation-log.md](../decisions/0039-loose-artifact-normalization-and-mutation-log.md)
- [0040-session-level-ui-view-and-unified-thread-feed.md](../decisions/0040-session-level-ui-view-and-unified-thread-feed.md)
- [artifacts.md](./artifacts.md)
- [threads_modes_personas.md](./threads_modes_personas.md)
- [abstractions.md](./abstractions.md)
- [backlog.md](./backlog.md)
- [vocabulary.md](./vocabulary.md)
