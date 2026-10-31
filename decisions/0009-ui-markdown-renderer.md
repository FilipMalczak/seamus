# 0009. UI Markdown Renderer

* Status: Accepted
* Date: 2026-10-31

## Context

The Seamus Web UI displays conversation messages between human users and autonomous agents across threads. Previously:
- Assistant messages were rendered with basic `ReactMarkdown` with minimal typography (only simple paragraph margins and unformatted code blocks).
- User messages were rendered as raw plain text inside a `<p className="whitespace-pre-wrap">` tag, without any Markdown support.
- Neither user nor assistant messages supported GitHub Flavored Markdown (GFM) features such as tables, strikethrough, autolinks, and task lists.
- Fenced code blocks lacked language labeling, structured formatting, and copy-to-clipboard functionality.
- Wide tables or lengthy code blocks risked overflowing message bubble boundaries and degrading the chat experience.

Both users and LLM agents routinely communicate using Markdown structures: code snippets with language specifiers, tabular summaries, checklist items, blockquotes, and links. The UI needed a unified, robust Markdown rendering pipeline where all messages are assumed to be Markdown and rendered cleanly in the browser.

## Decision

1. **Unified `MarkdownRenderer` Component**:
   - Introduce a dedicated, reusable component in `ui/src/components/MarkdownRenderer.tsx` that wraps `ReactMarkdown` with `remark-gfm`.
   - Both user and assistant message bubbles in `MessageItem.tsx` route through `MarkdownRenderer` with a `variant` prop (`"user" | "assistant"`).
2. **GitHub Flavored Markdown (GFM)**:
   - Use `remark-gfm` to parse and render Markdown tables, strikethrough text (`~~text~~`), task lists (`- [x]`, `- [ ]`), and autolinks.
3. **Safe Link Handling**:
   - Intercept anchor tags (`<a>`) in Markdown to automatically attach `target="_blank"` and `rel="noopener noreferrer"` for external URLs, preventing state loss and tab hijacking.
4. **Enhanced Code Blocks with Clipboard Copy**:
   - Intercept code block containers (`<pre>`) to render a language label bar (e.g. `python`, `typescript`, `bash`, `json`) and an interactive copy button with feedback (`Copied!` state for 2 seconds).
   - Ensure horizontal scrolling (`overflow-x: auto`) for long lines without overflowing the chat bubble.
5. **Horizontal Table Overflow Protection**:
   - Wrap `<table>` elements in a `.markdown-table-wrapper` container with `overflow-x: auto` so wide tables scroll smoothly within message bubbles.
6. **Bubble Contrast & Theme Typography**:
   - Adapt inline code, link colors, blockquotes, and code block headers depending on the bubble variant:
     - `.markdown-assistant`: styled for dark slate background (`var(--bg-secondary)`), sky blue links (`#38bdf8`), and subtle code containers.
     - `.markdown-user`: styled for deep blue background (`#1e3a8a`), light blue links (`#93c5fd`), light inline code backgrounds, and white/cyan contrast.

## Consequences

### Positive
- Both user prompts and agent responses render rich, formatted Markdown identically and predictably.
- Developers can copy code blocks with a single click without selecting text manually.
- Tables and checklists format cleanly inside chat bubbles without layout breaking or page overflow.
- External links open safely in new tabs without navigating away from the active thread session.

### Neutral / Trade-offs
- Adds `remark-gfm` as a frontend dependency in `ui/package.json`.
- Markdown syntax in raw text (like `*` or `#`) will be interpreted as formatting unless escaped with backslashes.

## References
- [Requirements](../knowledge/requirements.md)
- [Architecture](../knowledge/architecture.md)
- [Abstractions](../knowledge/abstractions.md)
- [Invariants](../knowledge/invariants.md)

