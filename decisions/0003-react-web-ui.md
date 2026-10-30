# 0003. React Web UI with Navigation Tree and In-Browser JSON Config Editor

Date: 2026-10-30
Status: Accepted

## Context

With the Seamus MVP backend service exposing `/api/v-alpha/` endpoints for agents, sessions, threads, config templates, and real-time AG-UI SSE streaming, a user-facing web interface is required. The UI must provide:
- A navigation tree visualizing the Agent $\to$ Session $\to$ Thread hierarchy.
- Direct conversational interaction with the active thread over real-time SSE.
- An in-browser raw JSON configuration editor for the service-wide `ConfigTemplate` and entity configurations.
- Fast, high-UX feedback using standard third-party libraries while maintaining lightweight frontend complexity.

## Decision

1. **Frontend Stack**: Use React 19, TypeScript, and Vite under `ui/`.
2. **Third-Party Libraries**:
   - `lucide-react` for UI icons.
   - `react-markdown` for streaming assistant message formatting.
3. **Navigation Tree Architecture**:
   - The left sidebar displays an expandable hierarchy: Agents $\to$ Sessions $\to$ Threads.
   - Visual badges indicate thread open/closed state (`is_open`) and agent execution status (`AWAITING_USER`, `AWAITING_LLM`, `EXECUTING_TOOL`, `ERROR`).
   - Quick action buttons allow creating new agents, sessions, and threads directly from the tree.
4. **Chat & Real-Time Streaming**:
   - The main screen connects to `GET /api/v-alpha/agent/<A>/session/<S>/thread/<T>` over Server-Sent Events (SSE).
   - Past AG-UI events are replayed from thread history, followed by live broadcasts.
   - Message inputs are dispatched via `POST /api/v-alpha/agent/<A>/session/<S>/input`. Dispatched user messages are converted into AG-UI text message events (`TextMessageStartEvent` with `role = 'user'`, `TextMessageContentEvent`, `TextMessageEndEvent`) and appended to `thread.events`, ensuring full conversation history replays when switching between threads.
   - The UI guards against posting when the agent is not in the `AWAITING_USER` state, disabling the send button and showing informative status feedback.
5. **In-Browser JSON Config Editor**:
   - Provide a modal editor supporting raw JSON inspection and modification for `ConfigTemplate` and entity configs.
   - Include client-side JSON syntax validation and auto-formatting before submission via `POST /api/v-alpha/config-template`.
6. **Backend Static Serving**:
   - In production, FastAPI optionally mounts `ui/dist` at root `/` and `/assets`.
   - In development, Vite dev server proxies `/api` and `/health` to `http://localhost:8000`.
7. **Zero-Prompt Creation, Default Entity Initialization & Input Auto-Focus**:
   - Creating an entity (Agent, Session, Thread) never prompts for a name during creation.
   - Creating an agent automatically instantiates a default session (`name = None`), which creates an initial open thread (`name = None`), immediately selected and followed in the UI.
   - Creating or selecting an entity immediately focuses the message composer input field to minimize "time-to-typing-message".
   - Entities can be renamed later via explicit pencil action buttons.
   - If `name` is non-empty, it is displayed in the navigation tree and breadcrumbs; otherwise, the full UUID is displayed.
8. **Multi-Service Container Orchestration & Launch Automation**:
   - Provide `docker-compose.yml` coordinating `backend` and `frontend` with hot reverse proxying.
   - Provide `./run.sh` launch script that ensures services are healthy before opening the browser.
   - `./run.sh --restart` (`-r`) rebuilds images and recreates running containers to apply updates. Restarting preserves persistent data volumes and does not wipe state (a separate `--reseed` flag will be used for resetting data when persistent storage is added).

## Consequences

- Full end-to-end user experience for managing agents and running interactive conversations.
- Developers can edit any configuration field directly in the browser via JSON without waiting for individual form field controls.
- The single backend server can optionally serve the static compiled UI bundle or run alongside Vite during development.

## Cross-References
- [0001-project-initialization.md](./0001-project-initialization.md)
- [0002-harness-server-mvp.md](./0002-harness-server-mvp.md)
- [../knowledge/architecture.md](../knowledge/architecture.md)
- [../knowledge/abstractions.md](../knowledge/abstractions.md)
- [../knowledge/invariants.md](../knowledge/invariants.md)
- [../knowledge/requirements.md](../knowledge/requirements.md)
- [../knowledge/vocabulary.md](../knowledge/vocabulary.md)

