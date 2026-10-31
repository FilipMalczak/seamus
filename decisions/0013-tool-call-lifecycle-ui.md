# 0013. Tool Call Lifecycle Progression and UI Stream Rendering

Date: 2026-10-31
Status: Accepted

## Context

During multi-turn execution and tool usage, tool calls displayed in the React Web UI remained indefinitely in the `"Running..."` state. In addition, tool names occasionally reverted to `"tool"`, tool arguments remained unpopulated, and tool execution outputs were not rendered.

Investigation of the end-to-end event stream revealed:
1. `ag_ui_langgraph` and LangGraph's tool node reliably emit AG-UI 1.0 streaming events (`TOOL_CALL_START`, `TOOL_CALL_ARGS`, `TOOL_CALL_END`, `TOOL_CALL_RESULT`, and `MESSAGES_SNAPSHOT`).
2. `ToolCallResultEvent` transmits the tool output in `event.content` (and optional error flags), but the client stream hook (`useThreadStream.ts`) looked only for `event.result ?? event.output`, evaluating to `undefined` and preventing completion detection in `ToolCallItem.tsx`.
3. `TOOL_CALL_END` (emitted by AG-UI when argument generation is complete and tool execution begins) was grouped with `TOOL_CALL_RESULT`, resetting or preventing result capture and prematurely altering thread status.
4. `TOOL_CALL_ARGS` transmits JSON fragments in `event.delta`, whereas the client expected structured `event.args`. Furthermore, lack of `toolCallName` on continuation argument chunks caused the fallback `event.toolCallName || "tool"` to overwrite the actual tool name.
5. Tool call matching was restricted strictly to `prev[prev.length - 1]`, failing when intervening text or reasoning events occurred before tool results arrived.
6. `MESSAGES_SNAPSHOT` events were ignored, preventing state reconciliation on step finish, reconnection, or page refresh.

## Decision

1. **Explicit Tool Call Lifecycle States**:
   - Model tool call records with explicit statuses: `"pending"` (arguments streaming / preparing), `"wip"` (tool executing in sandbox / backend), `"done"` (execution complete with result output), and `"error"` (execution failed).
   - Update `ui/src/api/types.ts` with `ToolCallStatus` and update `ToolCallRecord`.

2. **Accurate Stream Reduction & Event Handling (`ui/src/hooks/useThreadStream.ts`)**:
   - **`TOOL_CALL_START`**: Register tool call with `status: "pending"`, record tool name, initialize raw argument buffer.
   - **`TOOL_CALL_ARGS` / `TOOL_CALL_CHUNK`**: Progressively accumulate `event.delta`, attempt incremental JSON parsing into structured `args`, preserve `toolCall.name` without generic `"tool"` overwrite.
   - **`TOOL_CALL_END`**: Transition tool status to `"wip"` and thread status to `EXECUTING_TOOL`, reflecting that arguments are complete and backend tool execution is underway.
   - **`TOOL_CALL_RESULT`**: Extract execution output from `event.content` (falling back to `event.result` / `event.output`), transition tool call status to `"done"` (or `"error"` if error flags are present), and transition thread status to `AWAITING_LLM`.
   - **`MESSAGES_SNAPSHOT`**: Parse authoritative message history and tool message results, reconciling tool call status and results across turns, step completions, and page reloads.
   - Locate matching tool calls across preceding assistant messages via `findLastIndex` rather than checking only the last message.

3. **Backend Status Transition Alignment (`seamus.harness.runner`)**:
   - Keep thread status in `AgentStatus.EXECUTING_TOOL` on `TOOL_CALL_END`, transitioning to `AgentStatus.AWAITING_LLM` only on `TOOL_CALL_RESULT` or assistant text events.

4. **UI Presentation & Badge Indicators (`ui/src/components/ToolCallItem.tsx`, `ui/src/App.css`)**:
   - Render distinct visual badges and indicators:
     - `Pending`: Amber badge with clock icon indicating arguments being prepared.
     - `WIP`: Cyan badge with spinning loader indicating active sandbox execution.
     - `Done`: Emerald badge with check icon indicating successful tool completion.
     - `Failed`: Red badge with error icon indicating tool execution failure.
   - Display formatted input arguments (parsed JSON or raw string) and result output when available.

## Consequences

- Tool calls visibly progress through clear lifecycle phases (**Pending** -> **WIP** -> **Done**).
- Tool names, input arguments, and execution outputs render reliably during live streaming and upon reconnect / replay.
- Thread status remains in `EXECUTING_TOOL` throughout the entire duration of tool execution.

## Cross-References

- [0002-harness-server-mvp.md](./0002-harness-server-mvp.md)
- [0003-react-web-ui.md](./0003-react-web-ui.md)
- [0007-agui-reasoning-and-trace-messages.md](./0007-agui-reasoning-and-trace-messages.md)
- [0010-opensandbox-filesystem-sandboxing.md](./0010-opensandbox-filesystem-sandboxing.md)
- [../knowledge/requirements.md](../knowledge/requirements.md)
- [../knowledge/invariants.md](../knowledge/invariants.md)
- [../knowledge/architecture.md](../knowledge/architecture.md)
- [../knowledge/abstractions.md](../knowledge/abstractions.md)
- [../knowledge/backlog.md](../knowledge/backlog.md)
