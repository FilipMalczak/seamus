"""Unit tests for VaultClient, secret interpolation, version watching, and checkpoint explosion."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

import httpx
import pytest
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import empty_checkpoint
from pydantic import SecretStr

from seamus.config.models import AgentConfig, InferenceConfig
from seamus.domain.entities import Agent, Session
from seamus.harness.runner import ReasoningChatOpenAI, SessionAgentRunner
from seamus.persistence.checkpointer import GitCheckpointSaver
from seamus.persistence.config import PersistenceSettings
from seamus.persistence.workspace import GitWorkspaceManager
from seamus.vault.client import VaultClient
from seamus.vault.interpolator import (
    resolve_secrets_with_versions,
    resolve_secrets_with_versions_sync,
)
from seamus.vault.models import (
    SecretNotFoundError,
    VaultError,
    VaultSettings,
)


@pytest.mark.asyncio
async def test_vault_client_get_set_and_list_secrets(tmp_path: Path) -> None:
    token_file = tmp_path / "root_token"
    token_file.write_text("s.test-root-token\n", encoding="utf-8")

    store: dict[str, list[dict[str, Any]]] = {
        "api-key/inference/openrouter": [{"value": "sk-or-v1-initial"}],
        "git/creds": [{"username": "bot", "token": "ghp_123"}],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("X-Vault-Token") == "s.test-root-token"
        path = request.url.path
        method = request.method

        if (method == "LIST" or request.url.params.get("list") == "true") and path.startswith(
            "/v1/secret/metadata"
        ):
            sub = path.removeprefix("/v1/secret/metadata").strip("/")
            prefix = f"{sub}/" if sub else ""
            keys: set[str] = set()
            for k in store:
                if k.startswith(prefix):
                    rem = k[len(prefix) :]
                    if "/" in rem:
                        keys.add(rem.split("/", 1)[0] + "/")
                    elif rem:
                        keys.add(rem)
            if not keys:
                return httpx.Response(404, json={"errors": []})
            return httpx.Response(200, json={"data": {"keys": sorted(keys)}})

        if method == "GET" and path.startswith("/v1/secret/metadata/"):
            sec_path = path.removeprefix("/v1/secret/metadata/").strip("/")
            if sec_path not in store:
                return httpx.Response(404, json={"errors": ["not found"]})
            versions = store[sec_path]
            return httpx.Response(
                200,
                json={
                    "data": {
                        "current_version": len(versions),
                        "versions": {str(i + 1): {} for i in range(len(versions))},
                    }
                },
            )

        if method == "GET" and path.startswith("/v1/secret/data/"):
            sec_path = path.removeprefix("/v1/secret/data/").strip("/")
            if sec_path not in store:
                return httpx.Response(404, json={"errors": ["not found"]})
            versions = store[sec_path]
            ver_param = request.url.params.get("version")
            ver = int(ver_param) if ver_param else len(versions)
            data = versions[ver - 1]
            return httpx.Response(
                200,
                json={
                    "data": {
                        "data": data,
                        "metadata": {"version": ver},
                    }
                },
            )

        if method == "POST" and path.startswith("/v1/secret/data/"):
            sec_path = path.removeprefix("/v1/secret/data/").strip("/")
            body = json.loads(request.content.decode("utf-8"))
            new_data = body["data"]
            store.setdefault(sec_path, []).append(new_data)
            ver = len(store[sec_path])
            return httpx.Response(200, json={"data": {"version": ver}})

        return httpx.Response(500, json={"errors": ["unhandled"]})

    settings = VaultSettings(
        base_url="http://openbao:8200",
        external_url="http://localhost:8200",
        token_file=token_file,
    )
    transport = httpx.MockTransport(handler)
    async_http = httpx.AsyncClient(
        transport=transport,
        base_url="http://openbao:8200",
        headers={"X-Vault-Token": settings.resolve_token() or ""},
    )
    sync_http = httpx.Client(
        transport=transport,
        base_url="http://openbao:8200",
        headers={"X-Vault-Token": settings.resolve_token() or ""},
    )
    client = VaultClient(settings=settings, client=async_http, sync_client=sync_http)

    # List recursively
    paths = await client.list_secrets()
    assert paths == ["api-key/inference/openrouter", "git/creds"]

    # Read field with version
    resolved = await client.get_secret_field_with_version("/api-key/inference/openrouter", "value")
    assert resolved.value == "sk-or-v1-initial"
    assert resolved.version == 1

    # Set a new version
    write_resp = await client.set_secret(
        "/api-key/inference/openrouter", {"value": "sk-or-v2-rotated"}
    )
    assert write_resp["version"] == 2

    resolved_v2 = await client.get_secret_field_with_version(
        "/api-key/inference/openrouter", "value"
    )
    assert resolved_v2.value == "sk-or-v2-rotated"
    assert resolved_v2.version == 2

    # Missing field raises SecretNotFoundError
    with pytest.raises(SecretNotFoundError, match="Field 'missing' not found"):
        await client.get_secret_field_with_version("/git/creds", "missing")

    # Missing secret raises SecretNotFoundError
    with pytest.raises(SecretNotFoundError, match="Secret not found"):
        await client.get_secret_field_with_version("/does/not/exist", "value")

    await async_http.aclose()
    sync_http.close()


@pytest.mark.asyncio
async def test_resolve_secrets_with_versions_leaves_original_config_untouched() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/secret/data/api-key/inference/openrouter":
            return httpx.Response(
                200,
                json={
                    "data": {
                        "data": {"value": "sk-live-secret-123"},
                        "metadata": {"version": 3},
                    }
                },
            )
        return httpx.Response(404, json={"errors": ["not found"]})

    transport = httpx.MockTransport(handler)
    async_http = httpx.AsyncClient(transport=transport, base_url="http://openbao:8200")
    vault_client = VaultClient(client=async_http)

    cfg = AgentConfig(
        inference=InferenceConfig(
            api_key="${secret('/api-key/inference/openrouter')}",
        ),
        model_name="openai/gpt-oss-120b",
    )

    resolved_cfg, version_map = await resolve_secrets_with_versions(cfg, client=vault_client)
    assert resolved_cfg.inference.api_key == "sk-live-secret-123"
    assert version_map == {("/api-key/inference/openrouter", "value"): 3}
    # Original config remains symbolic
    assert cfg.inference.api_key == "${secret('/api-key/inference/openrouter')}"
    await async_http.aclose()


def test_resolve_secrets_rejects_non_string_field_value() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": {
                    "data": {"value": 12345},
                    "metadata": {"version": 1},
                }
            },
        )

    transport = httpx.MockTransport(handler)
    sync_http = httpx.Client(transport=transport, base_url="http://openbao:8200")
    vault_client = VaultClient(sync_client=sync_http)

    cfg = AgentConfig(
        inference=InferenceConfig(api_key="${secret('/num/secret')}"),
        model_name="openai/gpt-oss-120b",
    )
    with pytest.raises(VaultError, match="must be a string"):
        resolve_secrets_with_versions_sync(cfg, client=vault_client)
    sync_http.close()


def test_runner_per_inference_secret_version_watching_auto_reloads() -> None:
    session = Session(
        agent_id=uuid4(),
        name="secret-watch-session",
        config=AgentConfig(
            inference=InferenceConfig(
                api_key="${secret('/api-key/inference/openrouter')}",
                base_url="https://openrouter.ai/api/v1",
            ),
            model_name="openai/gpt-oss-120b",
        ),
    )

    dummy_agent = MagicMock()
    dummy_agent.config = {"recursion_limit": 50}
    runner = SessionAgentRunner(session=session, agent=dummy_agent)
    runner._llm = ReasoningChatOpenAI(
        model="openai/gpt-oss-120b",
        api_key=SecretStr("sk-v1-old"),
        base_url="https://openrouter.ai/api/v1",
    )
    runner._loaded_secret_versions = {("/api-key/inference/openrouter", "value"): 1}

    current_vault_version = 1
    current_vault_value = "sk-v1-old"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/secret/metadata/api-key/inference/openrouter":
            return httpx.Response(
                200,
                json={"data": {"current_version": current_vault_version}},
            )
        if request.url.path == "/v1/secret/data/api-key/inference/openrouter":
            return httpx.Response(
                200,
                json={
                    "data": {
                        "data": {"value": current_vault_value},
                        "metadata": {"version": current_vault_version},
                    }
                },
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    sync_http = httpx.Client(transport=transport, base_url="http://openbao:8200")
    vault_client = VaultClient(sync_client=sync_http)

    with patch("seamus.harness.runner.get_default_vault_client", return_value=vault_client):
        # Case 1: Version in OpenBao is still 1 -> no reload
        reloaded = runner.refresh_secrets_sync()
        assert reloaded is False
        assert runner._loaded_secret_versions == {("/api-key/inference/openrouter", "value"): 1}
        assert isinstance(runner._llm.openai_api_key, SecretStr)
        assert runner._llm.openai_api_key.get_secret_value() == "sk-v1-old"

        # Case 2: Version in OpenBao increases to 2 -> auto-reload
        current_vault_version = 2
        current_vault_value = "sk-v2-new-secret"
        reloaded = runner.refresh_secrets_sync()
        assert reloaded is True
        assert runner._loaded_secret_versions == {("/api-key/inference/openrouter", "value"): 2}
        assert isinstance(runner._llm.openai_api_key, SecretStr)
        assert runner._llm.openai_api_key.get_secret_value() == "sk-v2-new-secret"
        # Session config in memory remains symbolic and unversioned
        assert session.config.inference.api_key == "${secret('/api-key/inference/openrouter')}"

    sync_http.close()


def test_checkpoint_saver_explodes_secret_expressions_on_disk_and_git(tmp_path: Path) -> None:
    agent_cfg = AgentConfig(
        inference=InferenceConfig(
            api_key="${secret('/api-key/inference/openrouter')}",
            base_url="https://openrouter.ai/api/v1",
        ),
        model_name="openai/gpt-oss-120b",
    )
    agent = Agent(name="test-agent", config=agent_cfg)
    session = Session(
        agent_id=agent.id,
        name="test-session",
        config=agent_cfg,
    )
    thread = session.get_open_thread()

    settings = PersistenceSettings(workspace_dir=tmp_path / "ws", enabled=False)
    ws_mgr = GitWorkspaceManager(settings=settings)
    ws_mgr.create_session_workspace(session, agent)

    loaded_versions = {("/api-key/inference/openrouter", "value"): 5}
    saver = GitCheckpointSaver(
        agent_id=agent.id,
        session_id=session.id,
        workspace_manager=ws_mgr,
        session=session,
        secret_versions_provider=lambda: loaded_versions,
    )

    config: RunnableConfig = {"configurable": {"thread_id": thread.id.hex, "checkpoint_ns": ""}}
    cp = empty_checkpoint()
    cp["id"] = "cp-exploded-1"

    saver.put(config, cp, {"source": "loop", "step": 1, "parents": {}}, {})

    # Verify config.json on disk has the exploded expression with path=, field=, version=5
    session_dir = ws_mgr.get_session_workspace_path(agent.id, session.id)
    config_file = session_dir / "agent" / "config" / "config.json"
    disk_data = json.loads(config_file.read_text(encoding="utf-8"))
    assert (
        disk_data["config"]["inference"]["api_key"]
        == "${secret(path='/api-key/inference/openrouter', field='value', version=5)}"
    )

    # Verify session.config in memory was NOT mutated to include version=5
    assert session.config.inference.api_key == "${secret('/api-key/inference/openrouter')}"
