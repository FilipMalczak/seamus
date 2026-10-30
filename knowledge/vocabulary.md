# Vocabulary

Canonical terms, definitions, and conceptual distinctions used throughout Seamus.

## Core Concepts

### Agent
An autonomous or semi-autonomous software entity that perceives its environment, reasons, takes actions, and uses tools to accomplish user objectives. In the Seamus harness, an Agent holds a complete configuration and manages one or more Sessions.

### Harness
The execution environment, runtime boundaries, lifecycle control, state persistence, and tool dispatch infrastructure that surrounds and manages agents. Seamus is specifically a deep agent harness designed for full ownership and customization.

### Task
A discrete unit of work requested by a user or assigned to an agent, governed by a lifecycle, branch, and acceptance criteria.

### Run
An execution instance of an agent or harness session executing a task, consisting of prompts, tool calls, results, and state transitions.

### Config Template
A singleton, service-wide configuration baseline specifying inference details (provider format, base URL, API key) and default model. A template may be partially complete (e.g. missing an API key).

### Session (Conversation)
A distinct conversational interaction context with an agent. Each session maintains an isolated copy of configuration derived from its parent agent, holds a dedicated DeepAgent instance, and consists of one or more sequential threads.

### Thread
A sub-conversation segment within a session. Only the most recently created thread in a session is open; earlier threads are closed. A thread records AG-UI streaming events and tracks execution status.

### Slug (Name)
A human-readable, URL-safe identifier formatted as lowercase words separated by hyphens (e.g. `foo-bar-baz`, regex: `^[a-z0-9]+(?:-[a-z0-9]+)*$`). Slugs can be assigned to agents, sessions, and threads as alternative identifiers to UUIDs.

### Agent Status
The operational state of a thread's agent:
- `AWAITING_USER`: Idle, awaiting user input.
- `AWAITING_LLM`: Waiting for model inference or streaming tokens.
- `EXECUTING_TOOL`: Executing an external tool or sub-routine.
- `ERROR`: Terminated due to an unhandled failure.

## Cross-References
- [0001-project-initialization.md](../decisions/0001-project-initialization.md)
- [0002-harness-server-mvp.md](../decisions/0002-harness-server-mvp.md)
- [architecture.md](./architecture.md)
- [abstractions.md](./abstractions.md)
