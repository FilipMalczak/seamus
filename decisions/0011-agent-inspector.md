# 0011. DeepAgent Inspector for Configuration, Runtime & Branch State

Date: 2026-10-31
Status: Accepted

## Context

Developers and operators configuring DeepAgents need deep visibility into how an agent is configured and executing on a given Git branch. While live streaming surfaces conversational tokens and tool executions in chat, there was no centralized mechanism to inspect the composite system prompt (base sandbox instructions combined with custom instructions), the available tools and their JSON argument schemas, the model and inference parameters, the Git branch and commit provenance, or the message trajectory as of the latest inference run.

Third-party agent evaluation and observability frameworks (e.g. LangSmith, Arize Phoenix, UK AISI Inspect) are either closed SaaS platforms, heavyweight standalone servers, or focused on test evaluation suites rather than providing an embeddable React inspector for a custom Git-backed DeepAgent harness.

## Decision

1. **Semi-Live Inspection Backend (`seamus.harness.inspector`)**:
   - Introduce an inspector service that produces a unified `AgentInspectReport` reflecting the agent as of its latest inference run.
   - Dual-mode resolution:
     - **Active In-Memory Runner**: When a `SessionAgentRunner` exists in the harness store, inspect the runner's live `CompiledStateGraph` tools, system prompt, active thread status, and memory state.
     - **Persisted Git Branch**: When a session is restored or idle, load `agent/config/config.json`, `agent/state/threads/{thread_id}/messages.json`, and `checkpoints.json` from the session workspace branch (`session/{session_id}`), and query `GitWorkspaceManager` for the latest commit SHA and Gitea URL.
   - **Security**: The report surfaces inference format, model name, and base URL, but confirms key configuration status via a boolean (`api_key_configured`) without exposing raw API keys.

2. **System Prompt Decomposition**:
   - Surface both the **Composite System Prompt** (what the LLM actually receives) and its decomposed layers:
     - `scaffold`: Operational directory guidance, tool instructions, and sandbox boundaries (`build_sandbox_system_prompt`).
     - `custom`: User-configured system prompt or prompt templates from the agent/session configuration.

3. **Tool & Capability Inventory**:
   - Extract all registered tools (`ls`, `read_file`, `write_file`, `edit_file`, `glob`, `grep`, `execute`, `task`).
   - For each tool, extract name, description, JSON schema for input arguments (`args_schema`), and execution backend (`opensandbox`).
   - Extract any declared subagent specifications.

4. **REST API Endpoint (`seamus.server.routes.agents`)**:
   - Mount `GET /api/v-alpha/agents/{agent_id}/sessions/{session_id}/inspect` returning `AgentInspectReport`.
   - Accept optional query parameter `thread_id` to inspect a specific thread (defaulting to the session's open thread).

5. **Tabbed Workspace UI (`[Chat] | [Inspector]`)**:
   - Add top-level tabs in the main workspace view (`ui/src/components/MainArea.tsx` / `ui/src/App.tsx`).
   - Preserve conversational state in memory when toggling between Chat and Inspector tabs.
   - Structure the Inspector view with:
     - Hero header: Model pill, status badge, branch chip linking to Gitea, commit SHA, and refresh button.
     - Section cards: Overview & Model, System Prompt (with one-click clipboard copy and layer toggle), Tools & Parameters (accordion with formatted JSON schemas), and Message Trajectory.

6. **Deferred Historical Time-Travel**:
   - Record a Deferred entry in `knowledge/backlog.md` for historical time-travel inspection (inspecting agent state at arbitrary past commits or checkpoint timestamps).

## Consequences

- Operators and developers can inspect the exact prompt, tool schemas, and model parameters powering any session without digging through raw Git JSON files or terminal logs.
- The inspector works uniformly for active in-memory sessions and dormant sessions loaded from Gitea branches.
- Sensitive credentials remain safeguarded.

## Cross-References

- [0002-harness-server-mvp.md](./0002-harness-server-mvp.md)
- [0003-react-web-ui.md](./0003-react-web-ui.md)
- [0008-git-persistence.md](./0008-git-persistence.md)
- [0010-opensandbox-filesystem-sandboxing.md](./0010-opensandbox-filesystem-sandboxing.md)
- [../knowledge/requirements.md](../knowledge/requirements.md)
- [../knowledge/invariants.md](../knowledge/invariants.md)
- [../knowledge/architecture.md](../knowledge/architecture.md)
- [../knowledge/abstractions.md](../knowledge/abstractions.md)
- [../knowledge/backlog.md](../knowledge/backlog.md)

