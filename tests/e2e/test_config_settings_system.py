"""End-to-end baseline for the configuration, settings, and system-info surfaces.

These routes are the service-wide control plane: the singleton configuration
template that seeds every agent, the system-wide settings, and the integration
metadata the UI reads to decide which external systems to offer.

The tests drive the real ASGI application. The only substitution is the
inference provider (the ``steerable`` scripted provider), which the
configuration template is seeded with.
"""

from __future__ import annotations

import httpx
import pytest

from seamus.config.models import InferenceFormat
from seamus.config.settings import get_system_settings_store
from seamus.config.template import get_config_template_store


@pytest.mark.asyncio
async def test_config_template_exposes_the_seeded_template(
    client: httpx.AsyncClient,
) -> None:
    """The config-template route returns the singleton template and its completeness."""
    res = await client.get("/api/v-alpha/config-template")

    assert res.status_code == 200
    body = res.json()
    assert body["config"]["model_name"] == "steerable-model"
    assert body["config"]["inference"]["format"] == InferenceFormat.STEERABLE.value
    assert body["is_complete"] is True


@pytest.mark.asyncio
async def test_config_template_update_replaces_the_singleton(
    client: httpx.AsyncClient,
) -> None:
    """POSTing a config template replaces the singleton and is observable on the next GET."""
    payload = {
        "model_name": "replacement-model",
        "mode": "chat",
        "inference": {
            "format": InferenceFormat.STEERABLE.value,
            "base_url": "https://openrouter.ai/api/v1",
        },
    }

    res = await client.post("/api/v-alpha/config-template", json=payload)
    assert res.status_code == 200
    assert res.json()["config"]["model_name"] == "replacement-model"

    # The replacement is the new singleton, not a copy.
    again = await client.get("/api/v-alpha/config-template")
    assert again.json()["config"]["model_name"] == "replacement-model"
    assert get_config_template_store().get_template().model_name == "replacement-model"


@pytest.mark.asyncio
async def test_config_template_update_rejects_an_invalid_payload(
    client: httpx.AsyncClient,
) -> None:
    """An invalid config template is rejected with a 422 and leaves the singleton intact."""
    before = (await client.get("/api/v-alpha/config-template")).json()["config"]["model_name"]

    res = await client.post(
        "/api/v-alpha/config-template",
        json={"inference": {"format": "not-a-format", "base_url": "https://example.test"}},
    )

    assert res.status_code == 422
    after = (await client.get("/api/v-alpha/config-template")).json()["config"]["model_name"]
    assert after == before


@pytest.mark.asyncio
async def test_settings_expose_the_default_skill_directories(
    client: httpx.AsyncClient,
) -> None:
    """The settings route returns the system-wide settings."""
    res = await client.get("/api/v-alpha/settings")

    assert res.status_code == 200
    settings = res.json()["settings"]
    assert isinstance(settings["skill_directories"], list)
    assert settings["skill_directories"], "expected at least one default skill directory"


@pytest.mark.asyncio
async def test_settings_update_is_persisted_in_the_store(
    client: httpx.AsyncClient,
) -> None:
    """POSTing settings replaces the singleton and is observable on the next GET."""
    payload = {"skill_directories": ["/opt/skills", "/srv/skills"]}

    res = await client.post("/api/v-alpha/settings", json=payload)
    assert res.status_code == 200
    assert res.json()["settings"]["skill_directories"] == ["/opt/skills", "/srv/skills"]

    again = await client.get("/api/v-alpha/settings")
    assert again.json()["settings"]["skill_directories"] == ["/opt/skills", "/srv/skills"]
    assert get_system_settings_store().get_settings().skill_directories == [
        "/opt/skills",
        "/srv/skills",
    ]


@pytest.mark.asyncio
async def test_system_info_reports_every_integration(client: httpx.AsyncClient) -> None:
    """The system-info route reports the state of all three external integrations."""
    res = await client.get("/api/v-alpha/system/info")

    assert res.status_code == 200
    body = res.json()
    assert set(body) == {"logfire", "gitea", "vault"}
    assert isinstance(body["logfire"]["enabled"], bool)
    assert isinstance(body["gitea"]["enabled"], bool)
    assert body["vault"]["enabled"] is True


@pytest.mark.asyncio
async def test_health_probe_reports_ok(client: httpx.AsyncClient) -> None:
    """The health probe is reachable outside the versioned API prefix."""
    res = await client.get("/health")

    assert res.status_code == 200
    assert res.json() == {"status": "ok", "service": "seamus"}
