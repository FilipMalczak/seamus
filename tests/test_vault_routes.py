"""Integration tests for /api/v-alpha/vault endpoints and system info vault metadata."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from seamus.config.models import AgentConfig, InferenceConfig, InferenceFormat
from seamus.config.settings import (
    SystemSettings,
    SystemSettingsStore,
    reset_system_settings_store,
)
from seamus.config.template import ConfigTemplateStore, reset_config_template_store
from seamus.harness.runner import reset_runner_registry
from seamus.harness.store import HarnessStore, reset_harness_store
from seamus.server.app import create_app
from seamus.vault.client import VaultClient
from seamus.vault.models import VaultSettings


@pytest.fixture(autouse=True)
def reset_globals() -> None:
    """Ensure clean isolation between tests."""
    template = AgentConfig(
        inference=InferenceConfig(
            format=InferenceFormat.OPENAI,
            base_url="https://openrouter.ai/api/v1",
            api_key="test-api-key",
        ),
        model_name="openai/gpt-oss-120b",
    )
    reset_config_template_store(ConfigTemplateStore(initial_template=template))
    reset_system_settings_store(SystemSettingsStore(initial_settings=SystemSettings()))
    reset_harness_store(HarnessStore())
    reset_runner_registry()


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    return TestClient(app)


def test_system_info_includes_vault_login_url(client: TestClient) -> None:
    res = client.get("/api/v-alpha/system/info")
    assert res.status_code == 200
    data = res.json()
    assert "vault" in data
    assert data["vault"]["enabled"] is True
    assert data["vault"]["url"] == "http://localhost:8200"
    assert data["vault"]["login_url"] == "http://localhost:8200/ui/vault/auth?with=token"


def test_vault_token_endpoint(client: TestClient) -> None:
    mock_vault = MagicMock(spec=VaultClient)
    mock_vault.settings = VaultSettings(
        base_url="http://openbao:8200",
        external_url="http://localhost:8200",
        token="s.root-token-xyz",
    )

    with patch("seamus.server.routes.vault.get_default_vault_client", return_value=mock_vault):
        res = client.get("/api/v-alpha/vault/token")
        assert res.status_code == 200
        body = res.json()
        assert body["token"] == "s.root-token-xyz"


def test_vault_list_and_create_secrets_endpoints(client: TestClient) -> None:
    mock_vault = MagicMock(spec=VaultClient)
    mock_vault.list_secrets = AsyncMock(return_value=["api-key/inference/openrouter"])
    mock_vault.get_secret_with_version = AsyncMock(
        return_value=({"value": "sk-secret", "org": "seamus"}, 2)
    )
    mock_vault.set_secret = AsyncMock(return_value={"version": 3})
    mock_vault.get_secret_metadata = AsyncMock(
        return_value={"versions": {"1": {}, "2": {}, "3": {}}}
    )

    with patch("seamus.server.routes.vault.get_default_vault_client", return_value=mock_vault):
        list_res = client.get("/api/v-alpha/vault/secrets")
        assert list_res.status_code == 200
        items = list_res.json()["secrets"]
        assert len(items) == 1
        assert items[0]["path"] == "api-key/inference/openrouter"
        assert items[0]["version"] == 2
        assert items[0]["keys"] == ["value", "org"]

        post_res = client.post(
            "/api/v-alpha/vault/secrets",
            json={
                "path": "/api-key/inference/openrouter",
                "data": {"value": "sk-new-secret"},
            },
        )
        assert post_res.status_code == 201
        created = post_res.json()
        assert created["path"] == "api-key/inference/openrouter"
        assert created["current_version"] == 3
        assert created["keys"] == ["value"]


def test_config_template_rejects_version_in_secret_expression(client: TestClient) -> None:
    res = client.post(
        "/api/v-alpha/config-template",
        json={
            "inference": {
                "format": "openai",
                "base_url": "https://openrouter.ai/api/v1",
                "api_key": (
                    "${secret(path='/api-key/inference/openrouter', field='value', version=1)}"
                ),
            },
            "model_name": "openai/gpt-oss-120b",
        },
    )
    assert res.status_code == 422
    assert "disallowed in user configurations" in res.text
