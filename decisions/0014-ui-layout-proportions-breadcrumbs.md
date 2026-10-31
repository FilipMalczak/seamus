# 0014. Draggable UI Split Divider (50/50 Default) and Multiline Breadcrumbs

Date: 2026-10-31
Status: Accepted

## Context

The Seamus Web UI previously used a fixed sidebar width (`300px`) and allocated all remaining viewport width to the main chat panel (`flex: 1`). As a deep agent harness with a multi-level hierarchy (Agents -> Sessions -> Threads) and rich tree controls (inline name editing, session configuration modals, branch indicators, status badges, external system links), a fixed 300px sidebar constricted the navigation hierarchy while chat was disproportionately wide.

An initial static 2:1 proportion split proved inflexible for varying display widths and user workflows. Additionally, in narrower layouts, the breadcrumb trail at the top of the chat area (`Agent / Session / Thread [Status]`) occupied a single line with fixed `48px` height, causing horizontal clipping against top-bar action buttons when identifiers or session names grew long.

## Decision

1. **Draggable Divider with 50/50 Default Split**:
   - Provide a draggable split resizer (`.split-resizer`) between the navigation sidebar and the main chat/inspector panel.
   - Default the split to a balanced **50/50 ratio** (`0.50`), allowing equal horizontal prominence for the entity navigation tree and conversational interaction.
   - Support smooth mouse dragging with pointer tracking on `window`, enforcing boundary clamps (minimum 280px for the navigation tree and 300px for the main panel) to prevent accidental collapse.
   - Persist the user's chosen split ratio in `localStorage` (`seamus_sidebar_ratio`) across sessions and page refreshes.
   - Support double-clicking the resizer handle to instantly reset to the balanced 50/50 split.
   - Style `.split-resizer` with hover/active accent glows (`var(--accent-primary)`) and an expanded invisible hit area (`::after`) for effortless grabbing.

2. **Multiline Breadcrumbs and Responsive Header**:
   - Change `.chat-top-bar` from fixed `height: 48px` to `min-height: 48px; height: auto` with `flex-wrap: wrap; gap: 0.5rem; padding: 0.5rem 1rem`.
   - Wrap individual breadcrumb segments (entity name + trailing slash) in `.crumb-item` spans using `inline-flex` and `align-items: center` to ensure delimiters never wrap as orphaned punctuation to a new line.
   - Enable `flex-wrap: wrap; gap: 0.25rem 0.45rem; line-height: 1.4` on `.chat-breadcrumbs`, and add `word-break: break-word` across entity crumb labels.
   - Anchor `.chat-top-actions` (thread status pill and Accept thread button) with `flex-shrink: 0; margin-left: auto` so actions remain cleanly positioned and accessible regardless of column width or breadcrumb wrapping.

3. **Compact Chat Spacing Refinements**:
   - Refine horizontal padding on `.chat-viewport`, `.composer-container`, `.chat-error-banner`, and `.closed-thread-notice` to `1rem` to maximize usable reading and typing area across all customized split widths.

## Consequences

- Users have full flexibility to adjust the balance between tree navigation and chat focus according to their display size and current task.
- The default 50/50 proportion provides immediate visual symmetry and comfortably accommodates both deep tree hierarchies and conversational chat.
- Long agent, session, or thread titles wrap gracefully across multiple lines in the header without visual clipping or obstructing action buttons.
