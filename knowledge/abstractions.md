# Abstractions

Interfaces, protocols, abstract base classes, implementations, package boundaries, and extension points.

## Package Boundaries

### `seamus` (`src/seamus`)
- The main package entry point.
- Exports public version `__version__`.
- All modules must be typed and covered by PEP 561 marker `py.typed`.

### `seamus.config` (`src/seamus/config`)
- Configuration abstractions and stores.
- `InferenceFormat`: Supported inference protocol shapes (e.g. `openai`).
- `InferenceConfig`: Provider settings (format, base URL, optional API key).
- `AgentConfig`: Agent-level settings (inference configuration and model name). Provides `is_complete()` and copy/derive utilities.
- `ConfigTemplateStore`: In-memory container for the service-wide singleton template, initialized from environment variables with fallback defaults.

### `seamus.domain` (`src/seamus/domain`)
- Core business entities independent of web or storage frameworks.
- `AgentStatus`: Enumeration of thread states (`AWAITING_USER`, `AWAITING_LLM`, `EXECUTING_TOOL`, `ERROR`).
- `Thread`: Models conversation thread state, open/closed flag, creation and touched timestamps, and past AG-UI event records.
- `Session`: Models an ongoing conversation with an agent, holding an isolated `AgentConfig`, a dedicated runner, and child threads.
- `Agent`: Models an agent entity holding a complete `AgentConfig` and child sessions.
- `Resolution`: Identifier resolution functions mapping UUID or slug strings to entities within their scope.

### `seamus.harness` (`src/seamus/harness`)
- Execution engine and state storage.
- `SessionAgentRunner`: Encapsulates DeepAgent graph instantiation, checkpointer management (`MemorySaver`), input handling, and event lifecycle mapping.
- `EventBroadcaster`: Fan-out pub-sub queue mechanism for multiplexing real-time AG-UI SSE events to multiple active thread consumers.
- `HarnessStore`: In-memory repository managing agents, sessions, and threads with scope-bound slug uniqueness.

### `seamus.server` (`src/seamus/server`)
- Web framework and protocol mapping.
- `create_app`: Factory assembling FastAPI app, CORS middleware, and APIRouters under `/api/v-alpha/`.
- Schemas: Pydantic request and response models enforcing API contracts and masking secrets where appropriate.

## Design Principles
- **Explicit over Implicit**: Prefer concrete, simple classes and protocols rather than speculative abstraction layers.
- **Separation of Concerns**: Keep framework/harness mechanics separate from application and agent domain code.
- **Type Annotations**: Public functions, methods, and classes must carry explicit type annotations.

## Cross-References
- [0001-project-initialization.md](../decisions/0001-project-initialization.md)
- [0002-harness-server-mvp.md](../decisions/0002-harness-server-mvp.md)
- [architecture.md](./architecture.md)
- [conventions.md](./conventions.md)
