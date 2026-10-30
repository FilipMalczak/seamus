# 0007. AG-UI Reasoning Exposure and Multi-Turn LangGraph Span Message Alignment

Date: 2026-10-30
Status: Accepted

## Context

Live multi-turn testing with OpenRouter and Pydantic Logfire surfaced two issues:
1. **Duplicate leading user message on `LangGraph` chain spans in Logfire**:
   - On turn 2+, `ag_ui_langgraph.LangGraphAgent.langgraph_default_merge_state` strips existing checkpoint messages and passes only the new turn delta in the graph input (`gen_ai.prompt`), whereas LangGraph's final output (`gen_ai.completion`) contains the full checkpoint history (`[turn_1_user, turn_1_ai, turn_2_user, turn_2_ai]`).
   - Logfire's `MainSpanProcessorWrapper._transform_langsmith_span_attributes` deduplicates `gen_ai.prompt.messages` against `gen_ai.completion.messages` only when the prompt messages form a prefix of the completion messages. When only the turn delta is passed as input, the prefix check fails on turn 2+ and Logfire prepends the delta message in front of the full conversation in `all_messages_events`.
2. **Missing model thinking/reasoning in AG-UI streams and Web UI**:
   - `langchain_openai.ChatOpenAI` ignores non-Responses-API reasoning fields (`reasoning`, `reasoning_content`, `reasoning_details`) returned by OpenRouter and OpenAI-compatible Chat Completions endpoints.
   - Because `AIMessageChunk` never receives the reasoning deltas in `additional_kwargs`, `ag_ui_langgraph` does not emit AG-UI 1.0 `REASONING_*` events (`REASONING_START`, `REASONING_MESSAGE_START`, `REASONING_MESSAGE_CONTENT`, `REASONING_MESSAGE_END`, `REASONING_END`), and the React Web UI had no handler or presentation component for reasoning streams.

## Decision

1. **`ReasoningChatOpenAI` Wrapper (`seamus.harness.runner`)**:
   - Subclass `langchain_openai.ChatOpenAI` as `ReasoningChatOpenAI` and override `_convert_chunk_to_generation_chunk` and `_create_chat_result`.
   - Extract reasoning text from `reasoning`, `reasoning_content`, or `reasoning_details` on both streaming deltas and non-streaming message payloads, storing it in `additional_kwargs["reasoning_content"]`.
   - This activates `ag_ui_langgraph.utils.resolve_reasoning_content` to emit standard AG-UI 1.0 `REASONING_*` events over SSE and records reasoning content on LangChain/Logfire spans.

2. **`SeamusLangGraphAgent` State Merge (`seamus.harness.runner`)**:
   - Subclass `ag_ui_langgraph.LangGraphAgent` as `SeamusLangGraphAgent` and override `langgraph_default_merge_state` to preserve `[*existing_messages, *new_messages]` in the merged graph input state.
   - Because checkpoint messages carry stable message IDs, LangGraph's `add_messages` reducer updates them in-place without duplicating state, while `gen_ai.prompt.messages` remains a prefix of `gen_ai.completion.messages` so Logfire's `all_messages_events` displays the exact chronological conversation across all turns.

3. **Frontend AG-UI `REASONING_*` Handling & Collapsible Thought Card (`ui`)**:
   - Update `SessionAgentRunner._update_status_from_event` and `useThreadStream.ts` to handle `REASONING_START`, `REASONING_MESSAGE_START`, `REASONING_MESSAGE_CONTENT`, `REASONING_MESSAGE_CHUNK`, `REASONING_MESSAGE_END`, and `REASONING_END`.
   - Accumulate reasoning deltas onto the active assistant `ChatMessage` (`reasoning` and `isReasoning` fields) and unify the assistant message ID when `TEXT_MESSAGE_START` arrives after reasoning.
   - Render a collapsible thought process card in `MessageItem.tsx` displaying a live `"Thinking..."` indicator while reasoning is streaming and a collapsible `"Thought process"` drawer once completed.

## Consequences

- `LangGraph` chain spans in Logfire display the exact conversation sequence without duplicate leading user messages on multi-turn sessions.
- Model thinking/reasoning from OpenRouter and OpenAI-compatible providers streams live over AG-UI SSE events, persists in thread event history for replay, appears in Logfire spans, and renders in the React Web UI.

## Cross-References

- [0002-harness-server-mvp.md](./0002-harness-server-mvp.md)
- [0003-react-web-ui.md](./0003-react-web-ui.md)
- [0005-logfire-integration.md](./0005-logfire-integration.md)
- [../knowledge/requirements.md](../knowledge/requirements.md)
- [../knowledge/invariants.md](../knowledge/invariants.md)
- [../knowledge/architecture.md](../knowledge/architecture.md)
- [../knowledge/abstractions.md](../knowledge/abstractions.md)
- [../knowledge/conventions.md](../knowledge/conventions.md)
- [../knowledge/vocabulary.md](../knowledge/vocabulary.md)

