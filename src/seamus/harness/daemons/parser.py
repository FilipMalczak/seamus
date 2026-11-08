"""Defensive loose slug parsing and normalization for daemon LLM outputs."""

from __future__ import annotations

import re

SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
CODE_BLOCK_PATTERN = re.compile(r"```(?:[a-zA-Z0-9_-]+)?\s*([\s\S]*?)\s*```")
PREFIX_PATTERN = re.compile(
    r"^(?:output|slug|the slug is|here is the slug|result|suggested slug)\s*:\s*",
    re.IGNORECASE,
)


def parse_loose_slug(
    raw_output: str | None,
    occupied_slugs: set[str] | None = None,
    max_length: int = 50,
) -> str | None:
    """Preemptively and loosely parse an LLM output into a valid lowercase slug.

    Handles fenced markdown code blocks, quotes, prefix labels (e.g. 'Output:'),
    conversational debris, and punctuation. Collides against occupied_slugs by
    appending an incremental numeric suffix.
    """
    if raw_output is None:
        return None

    text = raw_output.strip()
    if not text:
        return None

    # 1. Extract from fenced markdown code block if present
    code_match = CODE_BLOCK_PATTERN.search(text)
    if code_match:
        text = code_match.group(1).strip()

    # 2. Extract from triple quotes if present
    for quote in ('"""', "'''"):
        if text.startswith(quote) and text.endswith(quote) and len(text) >= len(quote) * 2:
            text = text[len(quote) : -len(quote)].strip()

    # 3. Process line by line; find the first non-empty line
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return None
    candidate = lines[0]

    # 4. Strip markdown blockquotes (> ...) or bullet points (- ..., * ...)
    while candidate.startswith(("> ", "- ", "* ")):
        if candidate.startswith("> "):
            candidate = candidate[2:].strip()
        elif candidate.startswith(("- ", "* ")):
            candidate = candidate[2:].strip()

    # 5. Strip common label prefixes like 'Output: ', 'Slug: '
    candidate = PREFIX_PATTERN.sub("", candidate).strip()

    # 6. Strip enclosing quotes or backticks
    candidate = candidate.strip("\"'`")

    # 7. Normalize characters
    candidate = candidate.lower()
    # Replace spaces, underscores, slashes, colons, dots with hyphens
    candidate = re.sub(r"[\s_/:.]+", "-", candidate)
    # Remove any character not lowercase alphanumeric or hyphen
    candidate = re.sub(r"[^a-z0-9-]", "", candidate)
    # Collapse consecutive hyphens
    candidate = re.sub(r"-+", "-", candidate)
    # Strip leading and trailing hyphens
    candidate = candidate.strip("-")

    if not candidate:
        return None

    # 8. Truncate to max_length avoiding ending hyphen
    if len(candidate) > max_length:
        candidate = candidate[:max_length].rstrip("-")

    # 9. Validate final slug pattern
    if not SLUG_PATTERN.match(candidate):
        return None

    # 10. Avoid collision with occupied slugs
    if occupied_slugs and candidate in occupied_slugs:
        base = candidate
        counter = 2
        while f"{base}-{counter}" in occupied_slugs:
            counter += 1
        candidate = f"{base}-{counter}"

    return candidate
