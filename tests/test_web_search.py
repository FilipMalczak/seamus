"""Tests for DuckDuckGo web search and web page extraction toolset."""

from unittest.mock import MagicMock, patch

import pytest

from seamus.harness.web_search import (
    WEB_SEARCH_TOOL_NAMES,
    _async_fetch_web_page,
    _async_web_search,
    _sync_fetch_web_page,
    _sync_web_search,
    create_fetch_web_page_tool,
    create_web_search_tool,
    get_web_search_tools,
)


def test_web_search_tool_names_constant() -> None:
    """Verify tool names constant matches expected identifiers."""
    assert WEB_SEARCH_TOOL_NAMES == {"web_search", "fetch_web_page"}


def test_tool_factories() -> None:
    """Verify tool factory functions create LangChain StructuredTools."""
    search_tool = create_web_search_tool()
    assert search_tool.name == "web_search"
    assert search_tool.coroutine is not None

    fetch_tool = create_fetch_web_page_tool()
    assert fetch_tool.name == "fetch_web_page"
    assert fetch_tool.coroutine is not None

    all_tools = get_web_search_tools()
    assert len(all_tools) == 2
    assert {t.name for t in all_tools} == WEB_SEARCH_TOOL_NAMES


def test_sync_web_search_empty_query() -> None:
    """Verify empty query returns prompt error."""
    assert _sync_web_search("") == "Search query cannot be empty."
    assert _sync_web_search("   ") == "Search query cannot be empty."


@patch("seamus.harness.web_search.DDGS")
def test_sync_web_search_success(mock_ddgs_cls: MagicMock) -> None:
    """Verify formatted output when DDGS returns results."""
    mock_ddgs = MagicMock()
    mock_ddgs_cls.return_value = mock_ddgs
    mock_ddgs.text.return_value = [
        {
            "title": "Python 3.12 Documentation",
            "href": "https://docs.python.org/3.12/",
            "body": "Official Python 3.12 documentation and reference manual.",
        },
        {
            "title": "What's New In Python 3.12",
            "href": "https://docs.python.org/3.12/whatsnew/",
            "body": "Detailed changelog and new features.",
        },
    ]

    output = _sync_web_search("python 3.12", max_results=2)
    assert "Web search results for: 'python 3.12'" in output
    assert "1. [Python 3.12 Documentation](https://docs.python.org/3.12/)" in output
    assert "Official Python 3.12 documentation and reference manual." in output
    assert "2. [What's New In Python 3.12](https://docs.python.org/3.12/whatsnew/)" in output
    mock_ddgs.text.assert_called_once_with("python 3.12", max_results=2)


@patch("seamus.harness.web_search.DDGS")
def test_sync_web_search_no_results(mock_ddgs_cls: MagicMock) -> None:
    """Verify clean message when DDGS returns empty results."""
    mock_ddgs = MagicMock()
    mock_ddgs_cls.return_value = mock_ddgs
    mock_ddgs.text.return_value = []

    output = _sync_web_search("nonexistentquery12345xyz")
    assert output == "No web search results found for: nonexistentquery12345xyz"


@patch("seamus.harness.web_search.DDGS")
def test_sync_web_search_error_handled(mock_ddgs_cls: MagicMock) -> None:
    """Verify exception from DDGS is caught and returns an informative string."""
    mock_ddgs = MagicMock()
    mock_ddgs_cls.return_value = mock_ddgs
    mock_ddgs.text.side_effect = RuntimeError("DDG rate limit reached (202)")

    output = _sync_web_search("failing query")
    assert "Web search error: DDG rate limit reached (202)" in output


def test_sync_fetch_web_page_empty_url() -> None:
    """Verify empty URL returns error."""
    assert _sync_fetch_web_page("") == "URL cannot be empty."
    assert _sync_fetch_web_page("   ") == "URL cannot be empty."


@patch("seamus.harness.web_search.DDGS")
def test_sync_fetch_web_page_success(mock_ddgs_cls: MagicMock) -> None:
    """Verify markdown extraction from web page."""
    mock_ddgs = MagicMock()
    mock_ddgs_cls.return_value = mock_ddgs
    mock_ddgs.extract.return_value = {
        "url": "https://example.com",
        "content": "# Example Domain\n\nThis domain is for use in examples.",
    }

    output = _sync_fetch_web_page("https://example.com")
    assert output == "# Example Domain\n\nThis domain is for use in examples."
    mock_ddgs.extract.assert_called_once_with("https://example.com", fmt="text_markdown")


@patch("seamus.harness.web_search.DDGS")
def test_sync_fetch_web_page_truncation(mock_ddgs_cls: MagicMock) -> None:
    """Verify content is truncated if exceeding max_chars."""
    mock_ddgs = MagicMock()
    mock_ddgs_cls.return_value = mock_ddgs
    mock_ddgs.extract.return_value = {
        "url": "https://example.com/long",
        "content": "A" * 2000,
    }

    output = _sync_fetch_web_page("https://example.com/long", max_chars=1000)
    assert len(output) > 1000
    assert output.startswith("A" * 1000)
    assert "[Content truncated: showing 1000 of 2000 characters]" in output


@patch("seamus.harness.web_search.DDGS")
def test_sync_fetch_web_page_no_content(mock_ddgs_cls: MagicMock) -> None:
    """Verify clean message when extract returns empty content."""
    mock_ddgs = MagicMock()
    mock_ddgs_cls.return_value = mock_ddgs
    mock_ddgs.extract.return_value = {"url": "https://empty.com", "content": ""}

    output = _sync_fetch_web_page("https://empty.com")
    assert output == "No readable content could be extracted from: https://empty.com"


@patch("seamus.harness.web_search.DDGS")
def test_sync_fetch_web_page_error_handled(mock_ddgs_cls: MagicMock) -> None:
    """Verify exceptions from extract are caught and handled gracefully."""
    mock_ddgs = MagicMock()
    mock_ddgs_cls.return_value = mock_ddgs
    mock_ddgs.extract.side_effect = ConnectionError("Could not connect to host")

    output = _sync_fetch_web_page("https://unreachable.local")
    assert "Error extracting web page content: Could not connect to host" in output


@pytest.mark.asyncio
@patch("seamus.harness.web_search.DDGS")
async def test_async_web_search(mock_ddgs_cls: MagicMock) -> None:
    """Verify async web search wraps sync execution."""
    mock_ddgs = MagicMock()
    mock_ddgs_cls.return_value = mock_ddgs
    mock_ddgs.text.return_value = [
        {"title": "Result", "href": "https://test.com", "body": "Snippet"}
    ]

    res = await _async_web_search("async query")
    assert "Result" in res
    assert "https://test.com" in res


@pytest.mark.asyncio
@patch("seamus.harness.web_search.DDGS")
async def test_async_fetch_web_page(mock_ddgs_cls: MagicMock) -> None:
    """Verify async fetch web page wraps sync execution."""
    mock_ddgs = MagicMock()
    mock_ddgs_cls.return_value = mock_ddgs
    mock_ddgs.extract.return_value = {
        "url": "https://async.com",
        "content": "Async Content",
    }

    res = await _async_fetch_web_page("https://async.com")
    assert res == "Async Content"
