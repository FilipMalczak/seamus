"""End-to-end tests for the LM-XML system prompt composition.

The prompt the model actually sees is assembled at runtime from the session
configuration, the discovered workspace context and the discovered skills.
These tests observe it through the *public* inspection endpoint, so they
assert on the same artefact the Web UI shows:

* REQ-023 / INV-027 — the effective prompt is LM-XML: the identity, the
  operating environment, the dynamic context and the custom instructions each
  live in their own section;
* REQ-042 / INV-052 — a context file discovered in the workspace is injected
  into the prompt;
* INV-053 — the discovered skills are serialized as pure tags, without
  attributes;
* REQ-041 / INV-051 — the prompt reflects the agent's configuration rather
  than a hardcoded constant.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from seamus.harness.runner import get_runner_registry


async def _inspect(client: httpx.AsyncClient, ctx: dict[str, Any]) -> dict[str, Any]:
    """Fetch the inspection report of a session."""
    response = await client.get(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/inspect"
    )
    assert response.status_code == 200
    return response.json()


@pytest.mark.asyncio
async def test_composite_prompt_is_lm_xml(
    client: httpx.AsyncClient,
    make_session: Any,
) -> None:
    """REQ-023 / INV-027: the effective prompt is an LM-XML document."""
    ctx = make_session("prompt-lmxml", mode="chat")

    # Instantiating the runner registers the session; the inspector then
    # composes the prompt through the production code path.
    get_runner_registry().get_runner(ctx["session"])

    body = await _inspect(client, ctx)
    composite = body["prompts"]["composite"]

    assert "<identity>" in composite
    assert "</identity>" in composite
    assert "<operating_environment>" in composite
    assert "</operating_environment>" in composite

    # The sections are properly nested, not merely present.
    assert composite.index("<identity>") < composite.index("</identity>")
    assert composite.index("</identity>") < composite.index("<operating_environment>")


@pytest.mark.asyncio
async def test_composite_prompt_carries_the_dynamic_context(
    client: httpx.AsyncClient,
    make_session: Any,
) -> None:
    """REQ-023: the dynamic context names the session, the agent and the mode."""
    ctx = make_session("prompt-dynamic", mode="chat")
    get_runner_registry().get_runner(ctx["session"])

    body = await _inspect(client, ctx)
    composite = body["prompts"]["composite"]

    assert "<dynamic_context>" in composite
    assert ctx["session_id"] in composite
    assert ctx["agent_id"] in composite
    assert "chat" in composite


@pytest.mark.asyncio
async def test_custom_instructions_reach_the_composite_prompt(
    client: httpx.AsyncClient,
    make_session: Any,
) -> None:
    """REQ-041: the agent's custom instructions are part of the effective prompt."""
    # The session inherits the agent's configuration, so the custom
    # instructions are in place before the runner is instantiated.
    ctx = make_session("prompt-custom", mode="chat", system_prompt="Always answer in metric units.")
    get_runner_registry().get_runner(ctx["session"])

    body = await _inspect(client, ctx)
    composite = body["prompts"]["composite"]

    assert "Always answer in metric units." in composite


@pytest.mark.asyncio
async def test_discovered_context_file_is_injected_into_the_prompt(
    client: httpx.AsyncClient,
    make_session: Any,
    session_dir: Any,
) -> None:
    """REQ-042 / INV-052: a workspace context file reaches the effective prompt."""
    ctx = make_session("prompt-context", mode="chat")

    dirs = session_dir(ctx["session"])
    data_dir = dirs["data"]
    data_dir.mkdir(parents=True, exist_ok=True)
    # `AGENTS.md` is one of the default discovery patterns.
    (data_dir / "AGENTS.md").write_text(
        "The system uses a single-writer event log.",
        encoding="utf-8",
    )

    get_runner_registry().get_runner(ctx["session"])

    body = await _inspect(client, ctx)
    composite = body["prompts"]["composite"]

    assert "single-writer event log" in composite


@pytest.mark.asyncio
async def test_discovered_skills_are_serialized_as_pure_tags(
    client: httpx.AsyncClient,
    make_session: Any,
) -> None:
    """INV-053: the skill entries are child tags, not attributed elements."""
    ctx = make_session("prompt-skills", mode="chat")
    get_runner_registry().get_runner(ctx["session"])

    body = await _inspect(client, ctx)
    composite = body["prompts"]["composite"]

    if "<available_skills>" not in composite:
        pytest.skip("no skills were discovered for this session")

    skills_block = composite[
        composite.index("<available_skills>") : composite.index("</available_skills>")
    ]

    # The name and the description are rendered as child elements; the skill
    # entry itself carries no `name="..."` attribute.
    assert '<skill name="' not in skills_block
    assert "<name>" in skills_block
    assert "<description>" in skills_block


@pytest.mark.asyncio
async def test_prompt_reflects_the_operational_mode(
    client: httpx.AsyncClient,
    make_session: Any,
) -> None:
    """REQ-025: the prompt states the session's operational mode."""
    ctx = make_session("prompt-mode", mode="plan", phase="discuss")
    get_runner_registry().get_runner(ctx["session"])

    body = await _inspect(client, ctx)
    composite = body["prompts"]["composite"]

    assert "<operational_mode>" in composite
    assert "plan" in composite


@pytest.mark.asyncio
async def test_scaffold_and_composite_prompts_differ(
    client: httpx.AsyncClient,
    make_session: Any,
) -> None:
    """REQ-018: the inspector reports the scaffold and the composite separately."""
    ctx = make_session("prompt-layers", mode="chat")
    get_runner_registry().get_runner(ctx["session"])

    body = await _inspect(client, ctx)
    prompts = body["prompts"]

    assert prompts["composite"]
    assert prompts["scaffold"]
    assert prompts["composite"] != prompts["scaffold"]
