# 0002. MVP Harness Server Architecture and REST API

Date: 2026-10-30
Status: Accepted

## Context

The Seamus harness requires a backend service exposing structured lifecycle and conversational features over agents powered by DeepAgent and served via the AG-UI protocol. The initial MVP must establish:
- A service-wide singleton configuration template that can be partially configured (e.g. inference API details and default model).
- A domain hierarchy of Agents, Sessions (conversations), and Threads, each addressable by UUID or URL-safe slug names.
- Complete copy-on-derivation configuration semantics from template to agent, and from agent to session.
- Real-time AG-UI event streaming (replaying past thread events and subscribing live) and execution status tracking.
- An explicit decision on HTTP verb semantics, path structures under `/api/v-alpha/`, and no-deletion safety.

## Decision

1. **API Base Path**: Root all service endpoints under `/api/v-alpha/`.
2. **Resource Deletion Policy**: Prohibit deletion endpoints across all resources (`Agent`, `Session`, `Thread`). Deletion operations are not supported in the API surface; archiving may be evaluated in future iterations.
3. **Update Semantics**: Use `POST` with full updated objects for entity updates (`/api/v-alpha/config-template`, `/api/v-alpha/agent/<A>`, `/api/v-alpha/agent/<A>/session/<S>`, `/api/v-alpha/agent/<A>/session/<S>/thread/<T>`). This allows explicitly clearing optional values (e.g., setting `name: null` or removing an `api_key`).
4. **Input Dispatch**: Dedicate `POST /api/v-alpha/agent/<A>/session/<S>/input` strictly to posting user chat messages. Requests are rejected with HTTP 409 Conflict if the session agent is not in the `AWAITING_USER` state.
5. **Config Inheritance and Completeness**:
   - The singleton `ConfigTemplate` may be incomplete (e.g. missing API key).
   - Agent config is copied from template and customized; sessions copy agent config.
   - Completeness (presence of provider format, base URL, model name, and API key) is enforced when creating an agent or initializing a session.
6. **Thread Modeling and Redirection**:
   - `GET /api/v-alpha/agent/<A>/session/<S>/thread` returns an HTTP 307 Temporary Redirect to the open thread of the session.
   - Sessions maintain an invariant where only the latest thread is open; prior threads are closed.
   - `GET .../thread/<T>` streams past AG-UI events from history, then live events via an in-memory pub-sub event broadcaster.
7. **Thread Status Lifecycle**:
   - Thread status is tracked via `AgentStatus` enum: `AWAITING_USER`, `AWAITING_LLM`, `EXECUTING_TOOL`, and `ERROR`.

## Consequences

- API consumers have a clean, predictable REST hierarchy where identifiers can be UUIDs or slugs.
- Accidental resource deletion is impossible through the API.
- DeepAgent execution runs with in-memory checkpointers (`MemorySaver`) per session, with complete configuration isolation between sessions.
- In-memory event replay and live SSE streaming ensure seamless UI reconnection and turn transitions.

## Cross-References
- [0001-project-initialization.md](./0001-project-initialization.md)
- [../knowledge/architecture.md](../knowledge/architecture.md)
- [../knowledge/abstractions.md](../knowledge/abstractions.md)
- [../knowledge/invariants.md](../knowledge/invariants.md)
- [../knowledge/requirements.md](../knowledge/requirements.md)
- [../knowledge/vocabulary.md](../knowledge/vocabulary.md)

