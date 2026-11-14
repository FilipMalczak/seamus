"""Tests for agent personas (REQ-024).

REQ-024 requires the harness to support an extensible architecture for agent
personas, with the ``Coder`` persona as the near-term focus. The architecture
is specified in
[0019-threads-modes-personas-architecture.md](../decisions/0019-threads-modes-personas-architecture.md)
and [threads_modes_personas.md](../knowledge/threads_modes_personas.md), but the
persona *mechanism* is not implemented yet: the identity is hardcoded in
``build_default_identity`` and ``AgentConfig`` has no persona field.

The suite therefore records two things:

* the behaviour that *is* implemented today — the default ``Coder`` identity is
  part of the effective system prompt — asserted green;
* the behaviour that is *specified but not implemented* — a configurable
  persona whose identity reaches the prompt — asserted as a non-strict
  ``xfail`` whose reason names the backlog entry tracking it.

Implementing the persona mechanism flips the ``xfail`` to a pass without a test
edit.
"""

from __future__ import annotations

from typing import Any

import pytest

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


@pytest.mark.xfail(
    strict=False,
    reason=(
        "REQ-024 personas are not implemented: AgentConfig has no persona field and the "
        "system prompt identity is hardcoded. Tracked by the 'Pluggable Agent Personas' "
        "backlog entry in knowledge/backlog.md."
    ),
)
def test_agent_config_exposes_a_configurable_persona() -> None:
    """REQ-024: a persona is a first-class, configurable property of the agent."""
    # ``AgentConfig`` has no ``persona`` field yet, so the payload is validated
    # through the model API: the test documents the specified contract, and the
    # ``xfail`` marker records that the contract is not implemented.
    config = AgentConfig.model_validate({"persona": "coder"})

    assert config.model_dump()["persona"] == "coder"


@pytest.mark.xfail(
    strict=False,
    reason=(
        "REQ-024 personas are not implemented: the effective system prompt always uses the "
        "hardcoded default identity. Tracked by the 'Pluggable Agent Personas' backlog "
        "entry in knowledge/backlog.md."
    ),
)
def test_configured_persona_reaches_the_effective_system_prompt() -> None:
    """REQ-024: the configured persona's identity reaches the assembled system prompt."""
    # ``build_effective_system_prompt`` has no ``persona`` parameter yet, so the
    # call is made through an untyped alias: the test documents the specified
    # contract, and the ``xfail`` marker records that it is not implemented.
    build: Any = build_effective_system_prompt
    prompt = build(
        persona="office-worker",
        include_dynamic_context=False,
    )

    assert "office-worker" in prompt
    assert build_default_identity() not in prompt
