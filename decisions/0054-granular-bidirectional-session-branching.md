# 0054. Granular Bidirectional Session Branching UX

Date: 2026-11-11

## Status

Accepted

## Context

Decision 0022 introduced session branching and lifecycle error handling, permitting sessions to branch off completed assistant turns into parallel sessions. However, the UX and engine were limited:
- Branching was only exposed at the footer of assistant turns ("Branch" and "Branch after tools (retry inference)").
- Branching off user messages relied on a client-side workaround that searched backwards for a preceding assistant message and resubmitted the user prompt.
- Slicing was coarse: it could only cut either at the very end of an assistant turn (`RUN_FINISHED`) or immediately after the last tool call in an assistant turn.
- Users could not branch before or after individual elements within a conversation: specifically, distinct user messages, synthetic system events (e.g. artifact interactions), individual bot text messages, reasoning blocks, or individual tool calls.

## Decision

1. **Granular Bidirectional Branching (`before` and `after`)**:
   - Model `BranchSessionRequest` with `target_id: str`, `position: Literal["before", "after"]`, and optional `item_type`:
     - Retain backward compatibility for legacy `message_id` and `retry_inference` parameters.
   - Slicing semantics across all five conversation item types:
     - **User Message**:
       - `before`: Slice history immediately prior to the user message events. The new session starts in `AWAITING_USER` state with clean workspace matching that point; no inference is triggered.
       - `after`: Include the user message in history; set status to `AWAITING_LLM` and automatically launch inference in the new session.
     - **System Event** (synthetic messages such as artifact button submissions):
       - `before`: Slice history prior to the synthetic event; session starts in `AWAITING_USER` at the prior conversational state.
       - `after`: Include the synthetic event; launch inference on the synthetic event in `AWAITING_LLM` state.
     - **Bot Message** (assistant text):
       - `before`: Slice history prior to the text message emission; status `AWAITING_LLM`, re-running inference to generate the message again and continue processing.
       - `after`: Include the text message. If the turn finished, status is `AWAITING_USER`; if followed by tools in the same turn, status is `AWAITING_LLM` and continues processing.
     - **Bot Thinking** (reasoning block):
       - `before`: Slice history prior to reasoning emission; status `AWAITING_LLM`, re-running inference to regenerate reasoning and continue processing.
       - `after`: Include reasoning; status `AWAITING_LLM`, continuing turn processing.
     - **Tool Call**:
       - `before`: Slice history prior to tool execution (after `TOOL_CALL_END`, before `TOOL_CALL_RESULT`). Workspace state reverts to the commit prior to this tool's execution. In the new session, re-execute the tool and continue the turn.
       - `after`: Include the tool result (`TOOL_CALL_RESULT`); status `AWAITING_LLM`. Keep the pre-branch tool result in checkpointer state and continue processing (executing next tools or returning to LLM inference).

2. **Center-ward UI Alignment**:
   - Remove legacy footer "Branch" and "Branch after tools" buttons from assistant message containers.
   - Introduce per-item `.bubble-branch-actions` positioned towards the center of the screen:
     - To the **left** of user message bubbles (since user messages align right).
     - To the **right** of assistant text bubbles, reasoning blocks, tool call cards, and system event cards.
   - Pair two distinct icons for "Branch before" and "Branch after" with explicit tooltips detailing the exact outcome.

## Consequences

### Positive
- Fine-grained control over conversation forks and error recovery at any step in a turn.
- Immediate retries for failed tool calls or undesirable model responses without losing context or restarting sessions.
- Clean UI ergonomics aligned center-ward relative to message bubbles.
- Full provenance and Git workspace synchronization preserved across all slice points.

### Negative / Trade-offs
- More branch points and commits may be created in Gitea during active experimentation.

