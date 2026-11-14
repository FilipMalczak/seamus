"""End-to-end baseline for the agent lifecycle routes.

Agents are the top of the Seamus hierarchy: an agent owns a configuration and
a set of sessions. This file covers the routes that create, list, read, and
update agents, including the rule that a new agent's configuration is derived
from the service-wide configuration template.

The tests drive the real ASGI application against the real harness store. The
only substitution is the inference provider (the ``steerable`` scripted
provider) and the container (the in-process stub sandbox).
"""

from __future__ import annotations

import httpx
import pytest

from seamus.config.models import InferenceFormat


@pytest.mark.asyncio
async def test_agent_creation_derives_its_config_from_the_template(
    client: httpx.AsyncClient,
) -> None:
    """A new agent inherits the service-wide configuration template."""
    res = await client.post("/api/v-alpha/agents", json={"name": "derived-agent"})

    assert res.status_code == 201
    body = res.json()
    assert body["name"] == "derived-agent"
    assert body["config"]["model_name"] == "steerable-model"
    assert body["config"]["inference"]["format"] == InferenceFormat.STEERABLE.value


@pytest.mark.asyncio
async def test_agent_creation_applies_config_overrides(
    client: httpx.AsyncClient,
) -> None:
    """An explicit config overrides the template for that agent only."""
    res = await client.post(
        "/api/v-alpha/agents",
        json={
            "name": "overridden-agent",
            "config": {
                "model_name": "override-model",
                "inference": {
                    "format": InferenceFormat.STEERABLE.value,
                    "base_url": "https://openrouter.ai/api/v1",
                },
            },
        },
    )

    assert res.status_code == 201
    assert res.json()["config"]["model_name"] == "override-model"

    # The template itself is untouched.
    template = (await client.get("/api/v-alpha/config-template")).json()
    assert template["config"]["model_name"] == "steerable-model"


@pytest.mark.asyncio
async def test_agent_creation_rejects_a_duplicate_name(
    client: httpx.AsyncClient,
) -> None:
    """Two agents cannot share a slug."""
    await client.post("/api/v-alpha/agents", json={"name": "duplicate-agent"})

    res = await client.post("/api/v-alpha/agents", json={"name": "duplicate-agent"})

    assert res.status_code == 409


@pytest.mark.asyncio
async def test_agent_listing_includes_created_agents(
    client: httpx.AsyncClient,
) -> None:
    """The listing route reports every registered agent."""
    await client.post("/api/v-alpha/agents", json={"name": "listed-agent"})

    res = await client.get("/api/v-alpha/agents")

    assert res.status_code == 200
    names = [a["name"] for a in res.json()]
    assert "listed-agent" in names


@pytest.mark.asyncio
async def test_agent_listing_has_a_singular_alias(
    client: httpx.AsyncClient,
) -> None:
    """``/agent`` and ``/agents`` are aliases of the same listing."""
    await client.post("/api/v-alpha/agents", json={"name": "aliased-agent"})

    plural = await client.get("/api/v-alpha/agents")
    singular = await client.get("/api/v-alpha/agent")

    assert plural.status_code == 200
    assert singular.status_code == 200
    assert plural.json() == singular.json()


@pytest.mark.asyncio
async def test_agent_detail_includes_its_sessions(
    client: httpx.AsyncClient,
) -> None:
    """The detail route reports the agent's sessions."""
    created = (await client.post("/api/v-alpha/agents", json={"name": "detail-agent"})).json()

    res = await client.get(f"/api/v-alpha/agent/{created['id']}")

    assert res.status_code == 200
    body = res.json()
    assert body["id"] == created["id"]
    assert body["name"] == "detail-agent"
    assert isinstance(body["sessions"], list)


@pytest.mark.asyncio
async def test_agent_detail_rejects_an_unknown_agent(
    client: httpx.AsyncClient,
) -> None:
    """Reading an unknown agent is a 404."""
    res = await client.get("/api/v-alpha/agent/does-not-exist")

    assert res.status_code == 404


@pytest.mark.asyncio
async def test_agent_update_replaces_the_name_and_config(
    client: httpx.AsyncClient,
) -> None:
    """Updating an agent replaces its name and its configuration."""
    created = (await client.post("/api/v-alpha/agents", json={"name": "before-update"})).json()

    res = await client.post(
        f"/api/v-alpha/agent/{created['id']}",
        json={
            "name": "after-update",
            "config": {
                "model_name": "updated-model",
                "inference": {
                    "format": InferenceFormat.STEERABLE.value,
                    "base_url": "https://openrouter.ai/api/v1",
                },
            },
        },
    )

    assert res.status_code == 200
    body = res.json()
    assert body["name"] == "after-update"
    assert body["config"]["model_name"] == "updated-model"

    again = await client.get(f"/api/v-alpha/agent/{created['id']}")
    assert again.json()["name"] == "after-update"
    assert again.json()["config"]["model_name"] == "updated-model"


@pytest.mark.asyncio
async def test_agent_update_rejects_a_duplicate_name(
    client: httpx.AsyncClient,
) -> None:
    """Renaming an agent onto an existing slug is a 409."""
    await client.post("/api/v-alpha/agents", json={"name": "taken-agent"})
    other = (await client.post("/api/v-alpha/agents", json={"name": "other-agent"})).json()

    res = await client.post(
        f"/api/v-alpha/agent/{other['id']}",
        json={
            "name": "taken-agent",
            "config": {
                "model_name": "steerable-model",
                "inference": {
                    "format": InferenceFormat.STEERABLE.value,
                    "base_url": "https://openrouter.ai/api/v1",
                },
            },
        },
    )

    assert res.status_code == 409


@pytest.mark.asyncio
async def test_agent_update_rejects_an_unknown_agent(
    client: httpx.AsyncClient,
) -> None:
    """Updating an unknown agent is a 404."""
    res = await client.post(
        "/api/v-alpha/agent/does-not-exist",
        json={
            "name": "ghost",
            "config": {
                "model_name": "steerable-model",
                "inference": {
                    "format": InferenceFormat.STEERABLE.value,
                    "base_url": "https://openrouter.ai/api/v1",
                },
            },
        },
    )

    assert res.status_code == 404
