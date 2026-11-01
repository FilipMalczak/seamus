# 0021. UI Chat Auto-Scroll User Precedence and Visual Diff File Path Filtering

Date: 2026-11-01

## Status

Accepted

## Context

Two high-friction frontend usability issues were identified in the SPA:
1. **Chat Auto-Scroll Fighting User Scrolling**: In `ui/src/components/ChatArea.tsx`, a `useEffect` triggered on every incoming message token called `scrollIntoView({ behavior: "smooth" })` unconditionally. When an agent was actively streaming tokens or executing tools on long conversation threads, any attempt by the user to scroll up to inspect previous turns was immediately overridden and yanked back down to the active bubble.
2. **Missing File Filtering in Diff Viewer**: In `ui/src/components/ChangesViewer.tsx`, reviewing a Sync PR with many modified files required manually scrolling through a long list or tree. Users needed an instant text/path filter to find files in large change sets.

## Decision

1. **User Precedence in Chat Auto-Scroll**:
   - Track scroll position in `.chat-viewport`. If the viewport is within 60px of the bottom edge, the user is considered "pinned" to the bottom, and incoming stream tokens auto-scroll smoothly as before.
   - If the user scrolls up, auto-scrolling is suppressed so the user can freely read historical messages without disruption.
   - When the user scrolls away from the bottom, display a floating "Scroll to bottom" button above the composer that smoothly scrolls to the latest message and re-pins auto-scrolling.
   - Sending a message or switching threads automatically re-pins to the bottom.

2. **Visual Diff File Path Filtering**:
   - Add a search input with clear action to the changed files sidebar in `ChangesViewer.tsx`.
   - Compute `filteredIndexedDiffs` preserving original file diff indices.
   - Filter both the sidebar navigation (tree view and list view) and the diff cards in the main viewport in real time.
   - Display a count badge indicating matching files (e.g. `X / Y`) and render friendly empty states when no files match the active filter.

## Consequences

### Positive
- Users can review past messages and tool calls during active agent streaming without being interrupted.
- Large Sync PRs with dozens of files can be filtered instantly by path substring.
- Preserves seamless jump-to-file and collapsible diff toggling.

### Negative / Trade-offs
- Slight additional React state management for scroll detection and filter queries.

