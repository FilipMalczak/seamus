"""Web search and web page extraction toolset powered by DuckDuckGo."""

import asyncio
import logging
from typing import Any

from ddgs import DDGS
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

WEB_SEARCH_TOOL_NAMES = frozenset({"web_search", "fetch_web_page"})
DEFAULT_MAX_RESULTS = 5
DEFAULT_MAX_PAGE_CHARS = 10000


class WebSearchInput(BaseModel):
    """Input parameters for web_search tool."""

    query: str = Field(description="Search terms or keywords to query the web for.")
    max_results: int = Field(
        default=DEFAULT_MAX_RESULTS,
        description="Maximum number of search results to return (1-10).",
        ge=1,
        le=10,
    )


class FetchWebPageInput(BaseModel):
    """Input parameters for fetch_web_page tool."""

    url: str = Field(description="URL of the web page to fetch and extract content from.")
    max_chars: int = Field(
        default=DEFAULT_MAX_PAGE_CHARS,
        description="Maximum number of characters to return (500-50000).",
        ge=500,
        le=50000,
    )


def _sync_web_search(query: str, max_results: int = DEFAULT_MAX_RESULTS) -> str:
    """Execute a synchronous DuckDuckGo web search."""
    clean_query = query.strip()
    if not clean_query:
        return "Search query cannot be empty."

    try:
        ddgs = DDGS()
        results: list[dict[str, Any]] = list(
            ddgs.text(clean_query, max_results=max(1, min(max_results, 10)))
        )
        if not results:
            return f"No web search results found for: {clean_query}"

        formatted: list[str] = [f"Web search results for: '{clean_query}'\n"]
        for idx, item in enumerate(results, start=1):
            title = str(item.get("title") or "No Title").strip()
            url = str(item.get("href") or "").strip()
            body = str(item.get("body") or "").strip()
            formatted.append(f"{idx}. [{title}]({url})\n   {body}\n")
        return "\n".join(formatted).strip()
    except Exception as exc:
        logger.warning("DuckDuckGo search error for query '%s': %s", clean_query, exc)
        return f"Web search error: {exc}"


async def _async_web_search(query: str, max_results: int = DEFAULT_MAX_RESULTS) -> str:
    """Execute an asynchronous DuckDuckGo web search in a worker thread."""
    return await asyncio.to_thread(_sync_web_search, query, max_results)


def _sync_fetch_web_page(url: str, max_chars: int = DEFAULT_MAX_PAGE_CHARS) -> str:
    """Execute synchronous web page fetching and markdown extraction."""
    clean_url = url.strip()
    if not clean_url:
        return "URL cannot be empty."

    try:
        ddgs = DDGS()
        res = ddgs.extract(clean_url, fmt="text_markdown")
        content = str(res.get("content") or "").strip()
        if not content:
            return f"No readable content could be extracted from: {clean_url}"

        if len(content) > max_chars:
            content = (
                content[:max_chars]
                + f"\n\n[Content truncated: showing {max_chars} of {len(content)} characters]"
            )
        return content
    except Exception as exc:
        logger.warning("DuckDuckGo extraction error for url '%s': %s", clean_url, exc)
        return f"Error extracting web page content: {exc}"


async def _async_fetch_web_page(url: str, max_chars: int = DEFAULT_MAX_PAGE_CHARS) -> str:
    """Execute asynchronous web page fetching and extraction in a worker thread."""
    return await asyncio.to_thread(_sync_fetch_web_page, url, max_chars)


def create_web_search_tool() -> StructuredTool:
    """Create a LangChain StructuredTool for DuckDuckGo web search."""
    return StructuredTool.from_function(
        name="web_search",
        description=(
            "Search the web for up-to-date documentation, articles, and answers using DuckDuckGo. "
            "Returns titles, URLs, and text snippets."
        ),
        func=_sync_web_search,
        coroutine=_async_web_search,
        args_schema=WebSearchInput,
    )


def create_fetch_web_page_tool() -> StructuredTool:
    """Create a LangChain StructuredTool for fetching and reading web page content."""
    return StructuredTool.from_function(
        name="fetch_web_page",
        description=(
            "Fetch and extract readable Markdown content from a given web URL. "
            "Use this to inspect details from search results or documentation links."
        ),
        func=_sync_fetch_web_page,
        coroutine=_async_fetch_web_page,
        args_schema=FetchWebPageInput,
    )


def get_web_search_tools() -> list[StructuredTool]:
    """Return all web search and extraction tools."""
    return [
        create_web_search_tool(),
        create_fetch_web_page_tool(),
    ]

