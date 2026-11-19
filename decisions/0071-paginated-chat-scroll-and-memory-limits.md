# 0071. Paginated Chat Scroll & Memory-Limited Bubble Virtualization

Date: 2026-11-19

## Status

Accepted

## Context

In long-horizon agentic sessions, a conversation thread or session can accumulate hundreds or thousands of inference events (user messages, assistant text outputs, reasoning spans, tool calls, and artifacts). Previously, when loading a session or reconnecting to its event stream, the backend replayed all historical events from the beginning over SSE. This led to:
1. Significant latency and network overhead during initial session loading.
2. The user starting at the oldest message and having to wait or click "Scroll to bottom" to reach the active point.
3. Severe memory pressure and DOM bloat in the browser, rendering thousands of complex React components simultaneously.

## Decision

1. **System Settings (`src/seamus/config/settings.py`)**:
   - Add three configurable parameters with defaults:
     - `api_batch_size: int = 50` (number of message bubbles to fetch per API batch)
     - `ui_batch_size: int = 200` (number of message bubbles rendered before and after viewport anchor)
     - `memory_batch_size: int = 300` (number of message bubbles retained in frontend memory as plain JSON data objects before and after viewport anchor)
   - Enforce invariant `api_batch_size <= ui_batch_size <= memory_batch_size`.
   - Expose and allow updating these settings in UI `SettingsModal`.

2. **Dedicated Paginated Message Endpoints**:
   - `GET /api/v-alpha/agent/{agent_identifier}/session/{session_identifier}/messages`
   - `GET /api/v-alpha/agent/{agent_identifier}/session/{session_identifier}/thread/{thread_identifier}/messages`
   - Parameters: `limit: int = 50`, `before_id: str | None = None`, `after_id: str | None = None`, `tail: bool = False`.
   - Aggregates granular AG-UI events into structured `ChatMessage` turns and bubbles:
     - User message: 1 bubble
     - Assistant text response: 1 bubble
     - Reasoning span: 1 bubble
     - Tool call (with response): 1 bubble
     - Artifact card: 1 bubble
     - Thread transition: 1 boundary bubble
   - Slices messages and bubbles based on cursor or tail parameters. For assistant turns spanning dozens or hundreds of parts/tool calls, the paginator slices inside the turn's `parts` and `toolCalls` arrays rather than delivering the entire multi-bubble turn as an indivisible unit.

3. **SSE Stream Replay Toggle**:
   - In `stream_session_events` and `stream_thread_events`, add `replay: bool = True`.
   - When `replay=false`, skip replaying historical events and immediately yield live broadcaster events.

4. **Frontend Two-Tier Buffering & Windowing**:
   - **In-Memory Buffer**: Stores up to `memory_batch_size` bubbles before and after the active anchor as plain JavaScript/JSON data objects (`ChatMessage[]`), with zero detached DOM nodes. When receiving older or newer slices that belong to an already loaded turn, parts and tool calls are merged (`prependMessages` / `appendMessages`).
   - **Rendered UI Window**: Slices the memory buffer (including inside turn parts) to mount at most `ui_batch_size` bubbles before and after the active anchor in the DOM (~400 bubbles max). Every bubble (parts, tool calls, reasoning, and user messages) carries a `data-bubble-id` attribute enabling precise viewport anchor tracking during scrolling.
   - **Upward Infinite Scroll**: Automatically fetches older 50-bubble batches as the user scrolls near the top, adjusting `scrollTop` to prevent visual jumping.
   - **Scroll to Bottom**: Immediately clears out-of-range historical bubbles, re-fetches or focuses the latest 50 bubbles, and restores bottom auto-scrolling.

## Consequences

- Initial session loading is instantaneous regardless of session length.
- Browser RAM footprint is strictly bounded to at most ~600 JSON message objects and ~400 rendered DOM components.
- Seamless upward infinite scroll allows exploring complete conversation history on demand.

