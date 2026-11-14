"""Tests for agent personas (REQ-024).

REQ-024 requires the harness to support an extensible architecture for agent
personas, with the ``Coder`` persona as the near-term focus.
"""

from __future__ import annotations

from seamus.config.models import AgentConfig
from seamus.harness.prompt import build_default_identity, build_effective_system_prompt


def test_default_identity_is_the_coder_persona() -> None:
    """The default identity describes the Coder archetype."""
    identity = build_default_identity()

    assert "Seamus" in identity
    assert "software engineering agent" in identity


def test_default_identity_reaches_the_effective_system_prompt() -> None:
    """REQ-024: the persona identity is part of the assembled system prompt."""
    prompt = build_effective_system_prompt(include_dynamic_context=False)

    assert build_default_identity() in prompt


def test_custom_instructions_are_appended_to_the_system_prompt() -> None:
    """REQ-024: per-agent custom instructions reach the prompt alongside the identity."""
    prompt = build_effective_system_prompt(
        custom_prompt="Always answer in metric units.",
        include_dynamic_context=False,
    )

    assert build_default_identity() in prompt
    assert "Always answer in metric units." in prompt


def test_agent_config_exposes_a_configurable_persona() -> None:
    """REQ-024: a persona is a first-class, configurable property of the agent."""
    config = AgentConfig.model_validate({"persona": "coder"})

    assert config.model_dump()["persona"] == "coder"


def test_configured_persona_reaches_the_effective_system_prompt() -> None:
    """REQ-024: the configured persona's identity reaches the assembled system prompt."""
    prompt = build_effective_system_prompt(
        persona="office-worker",
        include_dynamic_context=False,
    )

    assert "office-worker" in prompt
    assert build_default_identity() not in prompt
