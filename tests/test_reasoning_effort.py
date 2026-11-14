"""Tests for the model reasoning-effort forwarding rule.

`REQ-047` and `INV-058` specify that `reasoning_effort` is omitted from the
provider payload when the configured tier is `default`, and forwarded verbatim
for every other tier. The rule sits on the provider boundary, where a mistake
silently degrades every reasoning-capable turn, so it is asserted at two
levels:

* the *decision* — which value the runner hands to the model constructor;
* the *payload* — what actually reaches the provider request.
"""

from typing import Any

import pytest
from pydantic import SecretStr

from seamus.config.models import (
    AgentConfig,
    InferenceConfig,
    ReasoningEffort,
)
from seamus.domain.entities import Agent
from seamus.harness.runner import ReasoningChatOpenAI, SessionAgentRunner

NON_DEFAULT_TIERS = [
    (ReasoningEffort.NONE, "none"),
    (ReasoningEffort.MINIMAL, "minimal"),
    (ReasoningEffort.LOW, "low"),
    (ReasoningEffort.MEDIUM, "medium"),
    (ReasoningEffort.HIGH, "high"),
    (ReasoningEffort.XHIGH, "xhigh"),
]


def _config(reasoning_effort: ReasoningEffort) -> AgentConfig:
    return AgentConfig(
        inference=InferenceConfig(
            api_key="mock-key",
            base_url="https://openrouter.ai/api/v1",
            reasoning_effort=reasoning_effort,
        ),
        model_name="mock-model",
    )


def _runner(reasoning_effort: ReasoningEffort) -> SessionAgentRunner:
    agent = Agent(config=_config(reasoning_effort), name="effort-agent")
    session = agent.create_session(name="effort-session")
    return SessionAgentRunner(session=session, agent_entity=agent)


def test_reasoning_effort_default_is_omitted_from_the_provider_payload() -> None:
    """INV-058: the `default` tier must not be sent to the provider at all."""
    llm = ReasoningChatOpenAI(
        model="mock-model",
        api_key=SecretStr("mock-key"),
        base_url="https://openrouter.ai/api/v1",
        reasoning_effort=None,
    )

    assert "reasoning_effort" not in llm._default_params


@pytest.mark.parametrize(("tier", "expected"), NON_DEFAULT_TIERS)
def test_reasoning_effort_non_default_tiers_are_forwarded_verbatim(
    tier: ReasoningEffort, expected: str
) -> None:
    """INV-058: every non-default tier reaches the provider unchanged."""
    llm = ReasoningChatOpenAI(
        model="mock-model",
        api_key=SecretStr("mock-key"),
        base_url="https://openrouter.ai/api/v1",
        reasoning_effort=expected,
    )

    assert llm._default_params["reasoning_effort"] == expected


def test_runner_omits_reasoning_effort_for_the_default_tier() -> None:
    """REQ-047: the runner maps the `default` tier to `None`."""
    runner = _runner(ReasoningEffort.DEFAULT)

    llm = runner._llm
    assert isinstance(llm, ReasoningChatOpenAI)
    assert llm.reasoning_effort is None
    assert "reasoning_effort" not in llm._default_params


@pytest.mark.parametrize(("tier", "expected"), NON_DEFAULT_TIERS)
def test_runner_forwards_non_default_reasoning_effort_tiers(
    tier: ReasoningEffort, expected: str
) -> None:
    """REQ-047: the runner forwards every non-default tier verbatim."""
    runner = _runner(tier)

    llm = runner._llm
    assert isinstance(llm, ReasoningChatOpenAI)
    assert llm.reasoning_effort == expected
    assert llm._default_params["reasoning_effort"] == expected


def test_reasoning_effort_is_not_forwarded_to_the_steerable_provider() -> None:
    """The steerable provider has no reasoning-effort knob; it must not receive one."""
    from seamus.config.models import InferenceFormat

    config = AgentConfig(
        inference=InferenceConfig(
            format=InferenceFormat.STEERABLE,
            base_url="http://localhost:1/v1",
            reasoning_effort=ReasoningEffort.HIGH,
        ),
        model_name="mock-model",
    )
    agent = Agent(config=config, name="steerable-effort-agent")
    session = agent.create_session(name="steerable-effort-session")

    runner = SessionAgentRunner(session=session, agent_entity=agent)

    llm = runner._llm
    assert llm is not None
    assert not isinstance(llm, ReasoningChatOpenAI)
    assert not hasattr(llm, "reasoning_effort")


def test_reasoning_effort_survives_a_config_reload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A reload must not silently drop a configured non-default tier."""
    from unittest.mock import MagicMock

    def mock_create_deep_agent(**kwargs: Any) -> Any:
        mock_graph = MagicMock()
        mock_graph.nodes = {}
        return mock_graph

    monkeypatch.setattr("seamus.harness.runner.create_deep_agent", mock_create_deep_agent)

    runner = _runner(ReasoningEffort.HIGH)
    llm = runner._llm
    assert isinstance(llm, ReasoningChatOpenAI)
    assert llm.reasoning_effort == "high"

    runner.reload_config()

    reloaded = runner._llm
    assert isinstance(reloaded, ReasoningChatOpenAI)
    assert reloaded.reasoning_effort == "high"
