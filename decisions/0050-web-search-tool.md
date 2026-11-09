# 0050. Web Search Toolset and Enum Configuration Guard

Date: 2026-11-10

## Status

Accepted

## Context

Agents frequently require external information to research libraries, investigate unfamiliar errors, look up current API documentation, and fact-check assumptions. Previously, Seamus agents were confined to local sandbox execution and local project context.

When adding web search capabilities:
1. The search engine must be free and ideally require no API key or external credentials to avoid setup friction.
2. The agent needs both query search (titles, URLs, and snippets) and full page reading/extraction (markdown content) to inspect detailed documentation.
3. The capability must be configurable and guarded across template, agent, and session hierarchies. Following Seamus conventions established for `todo_implementation` ([0049-native-lmxml-todo-planning.md](./0049-native-lmxml-todo-planning.md)) and `skills_implementation` ([0048-native-lmxml-skills-system.md](./0048-native-lmxml-skills-system.md)), this should be modeled as an extensible enum rather than a raw boolean flag, defaulting to `"duckduckgo"`.
4. When disabled (`web_search = "none"`), the web search tools must not be exposed to the model or displayed in the Inspector.

## Decision

1. **DuckDuckGo Provider (`ddgs`)**:
   - Adopt the `ddgs` library (DuckDuckGo search) as the underlying zero-credential, free web provider.
   - Run network-bound search and extraction operations non-blockingly via `asyncio.to_thread` within the async FastAPI / LangGraph loop.

2. **Discrete Web Toolset (`src/seamus/harness/web_search.py`)**:
   Implement two LangChain `StructuredTool` instances:
   - `web_search(query: str, max_results: int = 5) -> str`: Queries DuckDuckGo for top web results, returning formatted markdown entries with titles, clickable links, and text snippets.
   - `fetch_web_page(url: str, max_chars: int = 10000) -> str`: Fetches page content and converts it to clean Markdown via `DDGS().extract(url, fmt="text_markdown")`. Truncates output to `max_chars` to protect the context window.
   - Graceful error handling: All network errors, rate-limits, or invalid URLs are caught and returned as clean error strings, preventing unhandled exceptions in the agent loop.

3. **Enum Configuration (`WebSearchImplementation`)**:
   - Define `WebSearchImplementation(StrEnum)` with `NONE = "none"` and `DUCKDUCKGO = "duckduckgo"`.
   - Add `web_search: WebSearchImplementation = WebSearchImplementation.DUCKDUCKGO` to `AgentConfig`.
   - Propagate `web_search` through `AgentConfig.copy_with_overrides()` across the `Template -> Agent -> Session` inheritance hierarchy.

4. **Dynamic Tool Filtering & Graph Compilation**:
   - In `SessionAgentRunner.create_agent()`: conditionally bind `web_search` and `fetch_web_page` tools when `config.web_search == WebSearchImplementation.DUCKDUCKGO`.
   - In `SessionAgentRunner.get_active_tools_for_request()`: if `config.web_search == WebSearchImplementation.NONE`, dynamically filter out `web_search` and `fetch_web_page` from request tools to ensure immediate effect on dynamic config updates.

5. **Observability and Inspector**:
   - Add `web_search: WebSearchImplementation` to `AgentInspectReport`.
   - Tag web tools with backend label `"web"` in `ToolInspectInfo`.
   - In `get_agent_inspect_report()`: exclude web tools from the report when `web_search == WebSearchImplementation.NONE`.

6. **User Interface Integration**:
   - `ConfigModal.tsx`: Provide a "Web Search" dropdown in the Form editor (`duckduckgo` vs `none`) with validation in JSON mode.
   - `AgentInspector.tsx`: Display `web_search` status in hero metadata and the Tools panel header. Render a custom `"Web"` badge (`backend-web`) for web tools.
   - `ToolCallItem.tsx`: Render a distinct `Globe` icon for `web_search` and `fetch_web_page` tool calls.

## Consequences

### Positive
- Zero setup friction: fully functional out-of-the-box with no API key or paid subscription needed.
- Clean architectural alignment with `todo_implementation` and `skills_implementation` enum patterns.
- Fast, non-blocking asynchronous execution via `asyncio.to_thread`.
- Complete user control to enable or disable web search per template, agent, or session.

