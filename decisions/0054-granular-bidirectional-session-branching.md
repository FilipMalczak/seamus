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

3. **Vertical Layout & Tall/Expanded Pinning**:
   - Arrange "Branch Before" and "Branch After" icon buttons vertically (`flex-direction: column`).
   - Sized at fixed constant dimensions (14px height each) such that together they match the exact height of a collapsed bubble (~32px) without icon scaling.
   - When a bubble expands or is taller than a single line, "Branch Before" sticks to the top of the bubble, and "Branch After" sticks to the bottom border of the bubble via `align-self: stretch` and `justify-content: space-between`.

4. **Tool Call Grouping & Visual Brace**:
   - When a single model inference results in more than one tool call, render a visual brace to the left of the group (`.tool-group-brace`).
   - Sibling tool call bubbles inside a group are sized to fit their content (`width: fit-content`), with "Branch Before" placed directly to the right of the first tool call in the group and "Branch After" placed directly to the right of the last tool call in the group.
   - Slicing semantics for tool groups:
     - `before`: Slices immediately prior to the first `TOOL_CALL_RESULT` in the group, restarting all tool executions in the group.
     - `after`: Slices immediately after the last `TOOL_CALL_RESULT` in the group, keeping all existing tool results and continuing execution.
   - Single tool call inferences omit the visual brace to prevent visual clutter, placing singular branch buttons beside the tool call card as with regular bubbles.

5. **Precise Provenance Indicator Placement & Thread Mode Continuity**:
   - When branching a session, the newly created open thread preserves the parent thread's operational `mode`, `phase`, `active_skills`, `todos`, and `active_plan_id` rather than resetting to `plan/discuss`.
   - `SessionBranchProvenance` records `preceding_message_id` (the last conversational item retained before the slice point, or `None` if branched before the first message) so `before` branches on sliced-out items remain anchored in the child session.
   - For user messages, system events, agent text messages, and reasoning blocks:
     - If branched before: the provenance indicator line is rendered **above** the target or subsequent bubble (or at the viewport boundary while awaiting user input).
     - If branched after: the provenance indicator line is rendered **below** the target bubble.
   - For tool calls (both single tool calls and braced tool groups):
     - If branched before: the horizontal indicator line runs underneath the tool call bubble(s) at the vertical midpoint (running behind the tool card for a single tool or odd number of calls, and between the upper and lower tool cards for an even number of calls), with the `"branched before <session>"` pill positioned to the right of the tool calls.
     - If branched after: the provenance indicator line is rendered **below** the tool call or braced group.

## Consequences

### Positive
- Fine-grained control over conversation forks and error recovery at any step in a turn.
- Immediate retries for failed tool calls or undesirable model responses without losing context or restarting sessions.
- Clean UI ergonomics aligned center-ward relative to message bubbles with vertical top/bottom border pinning.
- Clear visual grouping with braces for multi-tool inferences, avoiding sequential execution assumptions.
- Accurate provenance indicator positioning reflecting whether history was sliced before or after each item.
- Full provenance and Git workspace synchronization preserved across all slice points.

### Negative / Trade-offs
- More branch points and commits may be created in Gitea during active experimentation.

