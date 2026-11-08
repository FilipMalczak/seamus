"""Unit tests for daemons, naming daemons, loose slug parser, and exchange counting."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from seamus.config.models import (
    AgentConfig,
    DaemonNamingConfig,
    DaemonsConfig,
    InferenceConfig,
)
from seamus.domain.artifacts import SYNTHETIC_MESSAGE_INDICATOR
from seamus.domain.entities import Session, Thread
from seamus.harness.daemons.formatter import format_thread_history
from seamus.harness.daemons.naming import (
    execute_session_naming,
    execute_thread_naming,
    is_stepback_trigger,
)
from seamus.harness.daemons.parser import parse_loose_slug


def test_daemon_config_validation() -> None:
    # 1. Default disabled
    d_cfg = DaemonNamingConfig()
    assert d_cfg.enabled is False
    assert d_cfg.provider is None
    assert d_cfg.model is None

    # 2. Enabled without model raises ValueError
    with pytest.raises(ValueError, match="daemons.naming.model must be specified"):
        DaemonNamingConfig(enabled=True)

    # 3. Enabled with model succeeds
    valid_cfg = DaemonNamingConfig(enabled=True, model="openai/gpt-4o-mini")
    assert valid_cfg.enabled is True
    assert valid_cfg.model == "openai/gpt-4o-mini"
    assert valid_cfg.provider is None

    # 4. Disabled with details provided is valid
    disabled_with_details = DaemonNamingConfig(
        enabled=False,
        provider=InferenceConfig(base_url="http://localhost:11434/v1"),
        model="llama3.2:3b",
    )
    assert disabled_with_details.enabled is False
    assert disabled_with_details.model == "llama3.2:3b"
    assert disabled_with_details.provider is not None

    # 5. AgentConfig daemons container and copy_with_overrides
    base_agent = AgentConfig(model_name="openai/gpt-oss-120b")
    assert base_agent.daemons.naming.enabled is False

    overridden_agent = base_agent.copy_with_overrides(
        AgentConfig(
            daemons=DaemonsConfig(
                naming=DaemonNamingConfig(enabled=True, model="openai/gpt-4o-mini")
            )
        )
    )
    assert overridden_agent.daemons.naming.enabled is True
    assert overridden_agent.daemons.naming.model == "openai/gpt-4o-mini"
    assert base_agent.daemons.naming.enabled is False


def test_parse_loose_slug_basic_and_normalization() -> None:
    assert parse_loose_slug(None) is None
    assert parse_loose_slug("") is None
    assert parse_loose_slug("   ") is None

    # Plain clean slug
    assert parse_loose_slug("fix-docker-networking") == "fix-docker-networking"

    # Spaces, uppercase, underscores
    assert parse_loose_slug("Fix Docker_Networking") == "fix-docker-networking"

    # Consecutive hyphens and leading/trailing punctuation
    assert parse_loose_slug("---Fix--Docker---Networking.---") == "fix-docker-networking"


def test_parse_loose_slug_markdown_and_quotes() -> None:
    # Fenced code block
    assert parse_loose_slug("```\nfix-docker-networking\n```") == "fix-docker-networking"
    assert parse_loose_slug("```text\nfix-docker-networking\n```") == "fix-docker-networking"

    # Triple quotes
    assert parse_loose_slug('"""fix-docker-networking"""') == "fix-docker-networking"
    assert parse_loose_slug("'''fix-docker-networking'''") == "fix-docker-networking"

    # Single/double quotes and backticks
    assert parse_loose_slug('"fix-docker-networking"') == "fix-docker-networking"
    assert parse_loose_slug("'fix-docker-networking'") == "fix-docker-networking"
    assert parse_loose_slug("`fix-docker-networking`") == "fix-docker-networking"

    # Markdown blockquote
    assert parse_loose_slug("> fix-docker-networking") == "fix-docker-networking"


def test_parse_loose_slug_prefixes_and_debris() -> None:
    # Prefixes
    assert parse_loose_slug("Output: fix-docker-networking") == "fix-docker-networking"
    assert parse_loose_slug("The slug is: fix-docker-networking") == "fix-docker-networking"
    assert parse_loose_slug("Slug: fix-docker-networking") == "fix-docker-networking"
    assert parse_loose_slug("Here is the slug: fix-docker-networking") == "fix-docker-networking"

    # Multi-line conversational output; takes first non-empty line
    multiline = "\n\nOutput: `oauth-redirect-bug`\n\nHope this helps!"
    assert parse_loose_slug(multiline) == "oauth-redirect-bug"


def test_parse_loose_slug_collision_resolution() -> None:
    occupied = {"fix-docker-networking", "fix-docker-networking-2"}
    result = parse_loose_slug("fix-docker-networking", occupied_slugs=occupied)
    assert result == "fix-docker-networking-3"


def test_is_stepback_trigger() -> None:
    # True for 2^k - 1: 1, 3, 7, 15, 31, 63, 127
    triggers = [1, 3, 7, 15, 31, 63, 127, 255]
    for count in triggers:
        assert is_stepback_trigger(count) is True, f"Expected {count} to trigger"

    # False for others
    non_triggers = [0, -1, 2, 4, 5, 6, 8, 9, 10, 14, 16, 20, 30, 32]
    for count in non_triggers:
        assert is_stepback_trigger(count) is False, f"Expected {count} not to trigger"


def test_parallel_slug_model_thread_and_session() -> None:
    # 1. Thread
    t = Thread()
    assert t.name is None
    assert t.custom_name is None
    assert t.daemon_name is None

    # Daemon names thread
    t.daemon_name = "daemon-thread-slug"
    assert t.name == "daemon-thread-slug"

    # User overrides thread
    t.name = "user-custom-slug"
    assert t.custom_name == "user-custom-slug"
    assert t.daemon_name == "daemon-thread-slug"
    assert t.name == "user-custom-slug"

    # User clears name -> falls back to daemon name
    t.name = None
    assert t.custom_name is None
    assert t.name == "daemon-thread-slug"

    # 2. Session
    agent_id = uuid4()
    s = Session(agent_id=agent_id, config=AgentConfig(model_name="openai/gpt-oss-120b"))
    assert s.name is None

    s.daemon_name = "daemon-session-slug"
    assert s.name == "daemon-session-slug"

    s.name = "user-session-slug"
    assert s.custom_name == "user-session-slug"
    assert s.name == "user-session-slug"

    s.name = None
    assert s.custom_name is None
    assert s.name == "daemon-session-slug"


def test_format_thread_history() -> None:
    events = [
        {"type": "TEXT_MESSAGE_START", "role": "user"},
        {"type": "TEXT_MESSAGE_CONTENT", "delta": "Which database should we choose?"},
        {"type": "TEXT_MESSAGE_END"},
        {"type": "TEXT_MESSAGE_START", "role": "assistant"},
        {"type": "TEXT_MESSAGE_CONTENT", "delta": "I will prepare a questionnaire."},
        {"type": "TEXT_MESSAGE_END"},
        {
            "type": "ARTIFACT_CREATED",
            "artifact_id": "art-123",
            "kind": "questionnaires",
            "title": "Database Selection",
        },
        {
            "type": "TEXT_MESSAGE_START",
            "role": "user",
        },
        {
            "type": "TEXT_MESSAGE_CONTENT",
            "delta": (
                f"{SYNTHETIC_MESSAGE_INDICATOR} User clicked 'submit' on artifact 'art-123' "
                'with payload: {"db": "postgres"}'
            ),
        },
        {"type": "TEXT_MESSAGE_END"},
        {"type": "TEXT_MESSAGE_START", "role": "assistant"},
        {"type": "TEXT_MESSAGE_CONTENT", "delta": "Great! PostgreSQL is selected."},
        {"type": "TEXT_MESSAGE_END"},
    ]

    transcript = format_thread_history(events)
    assert "User: Which database should we choose?" in transcript
    expected_art = (
        'Assistant: I will prepare a questionnaire. [Artifact: questionnaires "Database Selection"]'
    )
    assert expected_art in transcript
    expected_action = (
        "User: [Artifact Action: 'submit' on artifact 'art-123'] Payload: {\"db\": \"postgres\"}"
    )
    assert expected_action in transcript
    assert "Assistant: Great! PostgreSQL is selected." in transcript


@pytest.mark.asyncio
async def test_execute_thread_naming_single_thread_session() -> None:
    agent_id = uuid4()
    cfg = AgentConfig(
        inference=InferenceConfig(api_key="test-key"),
        model_name="openai/gpt-oss-120b",
        daemons=DaemonsConfig(naming=DaemonNamingConfig(enabled=True, model="openai/gpt-4o-mini")),
    )
    session = Session(agent_id=agent_id, config=cfg)
    thread = session.create_thread()
    thread.events = [
        {"type": "TEXT_MESSAGE_START", "role": "user"},
        {"type": "TEXT_MESSAGE_CONTENT", "delta": "Fix the docker networking timeout"},
        {"type": "TEXT_MESSAGE_END"},
        {"type": "TEXT_MESSAGE_START", "role": "assistant"},
        {"type": "TEXT_MESSAGE_CONTENT", "delta": "I am updating the docker compose config."},
        {"type": "TEXT_MESSAGE_END"},
    ]

    mock_runner = AsyncMock()
    mock_runner.session = session
    mock_runner._loaded_secret_versions = {}
    mock_runner._resolve_agent_entity = MagicMock(return_value=None)
    mock_runner.broadcaster = AsyncMock()

    with patch(
        "seamus.harness.daemons.naming.invoke_daemon",
        new=AsyncMock(return_value="fix-docker-timeout"),
    ):
        slug = await execute_thread_naming(mock_runner, thread)

    assert slug == "fix-docker-timeout"
    assert thread.daemon_name == "fix-docker-timeout"
    # Single-thread session mirrors thread slug
    assert session.daemon_name == "fix-docker-timeout"
    mock_runner.broadcaster.broadcast.assert_called_once()


@pytest.mark.asyncio
async def test_execute_session_naming_multi_thread() -> None:
    agent_id = uuid4()
    cfg = AgentConfig(
        inference=InferenceConfig(api_key="test-key"),
        model_name="openai/gpt-oss-120b",
        daemons=DaemonsConfig(naming=DaemonNamingConfig(enabled=True, model="openai/gpt-4o-mini")),
    )
    session = Session(agent_id=agent_id, config=cfg)
    t1 = session.create_thread()
    t1.daemon_name = "docker-networking"
    t1.exchange_count = 6

    t2 = session.create_thread(reuse_empty=False, name="vault-secrets")
    t2.exchange_count = 1

    assert session.total_exchange_count == 7
    assert len(session.threads) == 2

    mock_runner = AsyncMock()
    mock_runner.session = session
    mock_runner._loaded_secret_versions = {}
    mock_runner._resolve_agent_entity = MagicMock(return_value=None)
    mock_runner.broadcaster = AsyncMock()

    with patch(
        "seamus.harness.daemons.naming.invoke_daemon",
        new=AsyncMock(return_value="infrastructure-setup"),
    ):
        slug = await execute_session_naming(mock_runner)

    assert slug == "infrastructure-setup"
    assert session.daemon_name == "infrastructure-setup"
    mock_runner.broadcaster.broadcast.assert_called_once()


@pytest.mark.asyncio
async def test_invoke_daemon_api_key_override_and_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    from langchain_core.messages import AIMessage
    from pydantic import SecretStr

    from seamus.harness.daemons.engine import invoke_daemon

    captured_kwargs: dict[str, Any] = {}

    class DummyChat:
        def __init__(self, **kwargs: Any) -> None:
            captured_kwargs.update(kwargs)

        async def ainvoke(self, messages: Any) -> Any:
            return AIMessage(content="test-slug-output")

    monkeypatch.setattr("seamus.harness.runner.ReasoningChatOpenAI", DummyChat)

    # 1. With active api_key_override
    cfg = InferenceConfig(api_key="${secret('/api-key/openrouter')}")
    slug = await invoke_daemon(
        provider=cfg,
        model="openai/gpt-4o-mini",
        instructions="Instructions",
        input_payload="Input",
        api_key_override="resolved-runner-key",
    )
    assert slug == "test-slug-output"
    assert captured_kwargs["api_key"] == SecretStr("resolved-runner-key")

    # 2. Without override, falls back to env var if symbolic
    monkeypatch.setenv("OPENROUTER_API_KEY", "env-openrouter-key")
    slug = await invoke_daemon(
        provider=cfg,
        model="openai/gpt-4o-mini",
        instructions="Instructions",
        input_payload="Input",
    )
    assert slug == "test-slug-output"
    assert captured_kwargs["api_key"] == SecretStr("env-openrouter-key")
