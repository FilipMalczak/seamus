"""Unit tests for HarnessStore repository operations and slug uniqueness."""

import pytest

from seamus.config.models import AgentConfig, InferenceConfig
from seamus.harness.store import HarnessStore, SlugConflictError


def make_complete_config() -> AgentConfig:
    return AgentConfig(
        inference=InferenceConfig(api_key="valid-key"),
        model_name="test-model",
    )


def test_harness_store_agent_crud_and_slug_conflict() -> None:
    store = HarnessStore()
    config = make_complete_config()

    # Create agent
    a1 = store.create_agent(config=config, name="alpha-agent")
    assert a1.name == "alpha-agent"
    assert store.resolve_agent(str(a1.id)).id == a1.id
    assert store.resolve_agent("alpha-agent").id == a1.id

    # Duplicate agent slug raises SlugConflictError
    with pytest.raises(SlugConflictError):
        store.create_agent(config=config, name="alpha-agent")

    # Incomplete config raises ValueError
    incomplete = AgentConfig()
    with pytest.raises(ValueError, match="incomplete"):
        store.create_agent(config=incomplete, name="incomplete-agent")

    # Update agent with new config and name
    updated = store.update_agent(
        identifier="alpha-agent",
        config=config,
        name="beta-agent",
    )
    assert updated.name == "beta-agent"
    assert store.resolve_agent("beta-agent").id == a1.id


def test_harness_store_session_and_thread_slug_scopes() -> None:
    store = HarnessStore()
    config = make_complete_config()

    store.create_agent(config=config, name="agent-1")
    store.create_agent(config=config, name="agent-2")

    # Same session slug in two different agents is allowed
    s1 = store.create_session(agent_identifier="agent-1", name="shared-slug")
    s2 = store.create_session(agent_identifier="agent-2", name="shared-slug")
    assert s1.name == "shared-slug"
    assert s2.name == "shared-slug"

    # Conflicting session slug within same agent is rejected
    with pytest.raises(SlugConflictError):
        store.create_session(agent_identifier="agent-1", name="shared-slug")

    # Thread creation and update
    t1 = store.create_thread(
        agent_identifier="agent-1",
        session_identifier="shared-slug",
        name="thread-1",
    )
    assert t1.name == "thread-1"

    with pytest.raises(SlugConflictError):
        store.create_thread(
            agent_identifier="agent-1",
            session_identifier="shared-slug",
            name="thread-1",
        )

    t1_updated = store.update_thread(
        agent_identifier="agent-1",
        session_identifier="shared-slug",
        thread_identifier="thread-1",
        name="thread-1-renamed",
    )
    assert t1_updated.name == "thread-1-renamed"
