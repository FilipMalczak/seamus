"""Unit tests for domain entities, slug validation, and thread invariants."""

import pytest

from seamus.config.models import AgentConfig, InferenceConfig
from seamus.domain.entities import (
    Agent,
    AgentStatus,
    Thread,
    validate_slug,
)


def test_validate_slug_valid() -> None:
    assert validate_slug(None) is None
    assert validate_slug("foo") == "foo"
    assert validate_slug("foo-bar") == "foo-bar"
    assert validate_slug("agent-1-test") == "agent-1-test"


def test_validate_slug_invalid() -> None:
    for invalid in ["Foo", "foo_bar", "-foo", "foo-", "foo--bar", "foo bar", ""]:
        if invalid == "":
            assert validate_slug(invalid) is None
        else:
            with pytest.raises(ValueError, match="Invalid slug name"):
                validate_slug(invalid)


def test_thread_lifecycle() -> None:
    thread = Thread(name="main-thread")
    assert thread.name == "main-thread"
    assert thread.is_open is True
    assert thread.status == AgentStatus.AWAITING_USER
    assert len(thread.events) == 0

    initial_touched = thread.last_touched_at
    thread.append_event({"type": "test_event"})
    assert len(thread.events) == 1
    assert thread.last_touched_at >= initial_touched


def test_session_single_open_thread_invariant() -> None:
    complete_config = AgentConfig(
        inference=InferenceConfig(api_key="test-key"),
        model_name="test-model",
    )
    agent = Agent(config=complete_config, name="test-agent")
    session = agent.create_session(name="session-1")

    # Session begins with exactly one open thread
    assert len(session.threads) == 1
    t1 = session.get_open_thread()
    assert t1.is_open is True

    # Creating a second thread closes the first (INV-005)
    t2 = session.create_thread(name="second-thread")
    assert len(session.threads) == 2
    assert t1.is_open is False
    assert t2.is_open is True
    assert session.get_open_thread().id == t2.id
