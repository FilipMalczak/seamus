"""Smoke tests for seamus package."""

import seamus


def test_version() -> None:
    """Verify package version is defined and non-empty."""
    assert seamus.__version__ == "0.1.0"
