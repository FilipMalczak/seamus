# 0051: Chat Bubble Timestamps and Sequence Indexing

## Context

In multi-turn autonomous agent sessions, agents frequently execute continuous streaks of tool calls and assistant turns. In the web chat interface:
1. Message timestamps were only shown in the message header above the bubble, formatted to the minute (`HH:MM`) without seconds. When multiple bubbles or turns occurred within the same minute, they all shared identical timestamps, making it difficult to assess how long individual steps took.
2. The chat bubbles themselves lacked per-bubble timestamps.
3. During long streaks of agent turns, users lacked a quick visual indicator of the number of steps executed or how long the agent had been running continuously.

## Decision

1. **Per-Bubble Timestamps with Seconds Precision**:
   - Add `.bubble-timestamp` directly inside each chat bubble (`.message-bubble`), formatted as `HH:MM:SS` via localized time formatting.
   - Enhance timestamp tooltips (`title`) with the full localized date, time, and ISO string (`YYYY-MM-DDTHH:mm:ss.sssZ`).
   - Retain `.message-time` in the message header with identical seconds precision for non-text/tool-call turns.

2. **Streak Detection & Configurable Threshold**:
   - Define a constant `BUBBLE_SEQUENCE_THRESHOLD = 5` in `ui/src/api/types.ts`.
   - In `ChatArea.tsx`, analyze contiguous streaks of messages by sender role (`assistant` or `user`). Thread transitions (`threadTransition`) and synthetic system event messages act as sequence boundaries.
   - If a streak exceeds `BUBBLE_SEQUENCE_THRESHOLD` (more than 5 consecutive messages/bubbles), assign a 1-based sequence index (`#1`, `#2`, ..., `#N`) to each message in that streak.
   - Support configuring or overriding the threshold via `sequenceThreshold` in `ChatAreaProps`.

3. **Top-Left Corner Index Badge & Part-Level Granularity**:
   - For messages with text bubbles, position a compact `.bubble-sequence-badge` (`#1`, `#2`, ...) at the top-left corner of the bubble (`.bubble-top-bar`).
   - For multi-part turns where an assistant executes a sequence of reasoning thoughts and tool calls within a single message turn, extract each sub-bubble (`reasoning`, `tool_call`, `text`, `artifact`) so streaks spanning across parts within a message are indexed sequentially (`#1`, `#2`, ...).
   - Thought processes (`ReasoningBlock`) and tool cards (`ToolCallItem`) display both their sequence index badge and their timestamp representing the latest stream part that constitutes them.
   - For messages without text or parts, surface the sequence badge in `.message-header` adjacent to the sender title so sequence continuity is never lost.
   - Provide role-specific styling with high contrast: sky-blue for assistant (`rgba(56, 189, 248, 0.15)` with `#38bdf8` text) and crisp white/blue for user bubbles (`rgba(255, 255, 255, 0.2)` with `#ffffff` text).

4. **Testing**:
   - Automated unit tests in `ui/tests/sequence.test.mjs` verifying streak calculations, threshold boundaries, thread transition resets, synthetic message resets, and timestamp formatting.

## Consequences

- Users can immediately observe how many turns an agent has executed in a continuous sequence and determine exact elapsed times across turns down to the second.
- Streaks of 5 or fewer messages remain clean and free of index badges, preserving minimal UI noise for standard conversational exchanges.

