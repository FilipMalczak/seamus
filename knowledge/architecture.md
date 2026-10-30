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
|  |    SessionAgentRunner  --->  DeepAgent (MemorySaver)                      |  |
|  |    AG-UI Event Broadcaster (Pub-Sub & History Replay)                     |  |
|  +---------------------------------------------------------------------------+  |
+---------------------------------------------------------------------------------+
```

## Component Boundaries

1. **Web User Interface (`ui`)**:
   - Location: `ui/`
   - Responsibility: React 19 single-page application built with Vite and TypeScript. Houses navigation sidebar tree, conversational message pane, SSE streaming client, and in-browser JSON config editor.
2. **Configuration (`seamus.config`)**:
   - Location: `src/seamus/config/`
   - Responsibility: `InferenceConfig`, `AgentConfig`, and singleton `ConfigTemplate` management with copy-on-derive semantics and completeness validation.
3. **Domain Entities (`seamus.domain`)**:
   - Location: `src/seamus/domain/`
   - Responsibility: Models for `Agent`, `Session`, `Thread`, and `AgentStatus`. Dual-resolution logic mapping UUIDs and slugs to entities.
4. **Harness & Runner (`seamus.harness`)**:
   - Location: `src/seamus/harness/`
   - Responsibility: In-memory store repository, `SessionAgentRunner` wrapping `create_deep_agent` and `ag_ui_langgraph.LangGraphAgent`, and event broadcasting/replay queues.
5. **Server & REST API (`seamus.server`)**:
   - Location: `src/seamus/server/`
   - Responsibility: FastAPI application factory mounted at `/api/v-alpha/`, Pydantic request/response schemas, routes for config template, agents, sessions, input dispatch, thread redirection, and SSE streaming. Optionally serves built `ui/dist` bundle in production.
6. **Decisions (`decisions`)**:
   - Location: `decisions/`
   - Responsibility: Append-only architectural and project direction decision records.
7. **Knowledge (`knowledge`)**:
   - Location: `knowledge/`
   - Responsibility: Durable conceptual, architectural, and requirement specifications.

## Cross-References
- [0001-project-initialization.md](../decisions/0001-project-initialization.md)
- [0002-harness-server-mvp.md](../decisions/0002-harness-server-mvp.md)
- [0003-react-web-ui.md](../decisions/0003-react-web-ui.md)
- [abstractions.md](./abstractions.md)
- [vocabulary.md](./vocabulary.md)
