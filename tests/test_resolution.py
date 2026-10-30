"""Unit tests for identifier resolution (UUID and slug)."""

from uuid import uuid4

import pytest

from seamus.config.models import AgentConfig, InferenceConfig
from seamus.domain.entities import Agent
from seamus.domain.resolution import (
    EntityNotFoundError,
    parse_uuid,
    resolve_session,
    resolve_thread,
)


def test_parse_uuid() -> None:
    valid = uuid4()
    assert parse_uuid(str(valid)) == valid
    assert parse_uuid("not-a-uuid") is None
    assert parse_uuid("") is None


def test_resolve_session_and_thread() -> None:
    config = AgentConfig(
        inference=InferenceConfig(api_key="key"),
        model_name="model",
    )
    agent = Agent(config=config, name="agent-one")
    session = agent.create_session(name="session-slug")
    thread = session.create_thread(name="thread-slug")

    # Resolve session by UUID
    assert resolve_session(agent, str(session.id)).id == session.id
    # Resolve session by slug
    assert resolve_session(agent, "session-slug").id == session.id

    # Resolve thread by UUID
    assert resolve_thread(session, str(thread.id)).id == thread.id
    # Resolve thread by slug
    assert resolve_thread(session, "thread-slug").id == thread.id

    # Unknown resolution raises EntityNotFoundError
    with pytest.raises(EntityNotFoundError):
        resolve_session(agent, "unknown-session")

    with pytest.raises(EntityNotFoundError):
        resolve_thread(session, "unknown-thread")

