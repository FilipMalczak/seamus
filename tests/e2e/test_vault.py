"""End-to-end baseline for the OpenBao secrets vault routes.

The vault routes are the only Seamus surface that talks to a third-party
service on every request. This file drives them through the real ASGI
application with a *fake OpenBao* behind ``httpx.MockTransport``: the route
handlers, the real ``VaultClient``, the real KV v2 request/response shapes and
the real error mapping are all exercised, but no network call is made.

The fake OpenBao is a small in-memory KV v2 store, so the tests can assert
that a secret written through the API is readable through the API, that values
are never echoed back, and that the documented status codes are produced.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import httpx
import pytest

from seamus.vault.client import VaultClient, reset_default_vault_client
from seamus.vault.models import VaultSettings


class FakeOpenBao:
    """A minimal in-memory OpenBao KV v2 server."""

    def __init__(self) -> None:
        self.secrets: dict[str, dict[str, Any]] = {}
        self.versions: dict[str, list[int]] = {}
        self.next_version = 1

    def handler(self, request: httpx.Request) -> httpx.Response:
        """Route an OpenBao API request to the in-memory store."""
        path = request.url.path
        parts = [p for p in path.split("/") if p]
        # /v1/<mount>/<data|metadata>[/<path...>]
        if len(parts) < 3 or parts[0] != "v1":
            return httpx.Response(404, json={"errors": ["unsupported path"]})
        engine = parts[2]
        rest = parts[3:]

        if engine == "metadata":
            return self._handle_metadata(request, rest)
        if engine == "data":
            return self._handle_data(request, rest)
        return httpx.Response(404, json={"errors": ["unsupported engine"]})

    def _handle_metadata(self, request: httpx.Request, rest: list[str]) -> httpx.Response:
        if request.method == "GET" and not rest:
            keys = list(self.secrets)
            return httpx.Response(200, json={"data": {"keys": keys}})
        if request.method == "GET" and rest:
            key = "/".join(rest)
            if key not in self.secrets:
                return httpx.Response(404, json={"errors": ["not found"]})
            return httpx.Response(
                200,
                json={
                    "data": {
                        "current_version": self.versions[key][-1],
                        "versions": {str(v): {} for v in self.versions[key]},
                    }
                },
            )
        return httpx.Response(405, json={"errors": ["method not allowed"]})

    def _handle_data(self, request: httpx.Request, rest: list[str]) -> httpx.Response:
        key = "/".join(rest)
        if request.method == "GET":
            if key not in self.secrets:
                return httpx.Response(404, json={"errors": ["not found"]})
            return httpx.Response(
                200,
                json={
                    "data": {
                        "data": self.secrets[key],
                        "metadata": {"version": self.versions[key][-1]},
                    }
                },
            )
        if request.method == "POST":
            payload = json.loads(request.content)
            version = self.next_version
            self.next_version += 1
            self.secrets[key] = payload.get("data", {})
            self.versions.setdefault(key, []).append(version)
            return httpx.Response(200, json={"data": {"version": version}})
        return httpx.Response(405, json={"errors": ["method not allowed"]})


@pytest.fixture
def fake_openbao() -> Iterator[FakeOpenBao]:
    """Install a fake OpenBao as the process-wide default vault client."""
    fake = FakeOpenBao()
    transport = httpx.MockTransport(fake.handler)
    http_client = httpx.AsyncClient(
        transport=transport,
        base_url="http://openbao.test",
        headers={"X-Vault-Token": "test-token"},
    )
    client = VaultClient(
        settings=VaultSettings(base_url="http://openbao.test", token="test-token"),
        client=http_client,
    )
    reset_default_vault_client(client)
    try:
        yield fake
    finally:
        reset_default_vault_client(None)


@pytest.mark.asyncio
async def test_vault_token_is_returned_for_the_ui(
    client: httpx.AsyncClient,
    fake_openbao: FakeOpenBao,
) -> None:
    """The token route returns the configured OpenBao token."""
    res = await client.get("/api/v-alpha/vault/token")

    assert res.status_code == 200
    assert res.json()["token"] == "test-token"


@pytest.mark.asyncio
async def test_vault_secret_is_written_and_read_back(
    client: httpx.AsyncClient,
    fake_openbao: FakeOpenBao,
) -> None:
    """A secret written through the API is readable through the API."""
    res = await client.post(
        "/api/v-alpha/vault/secrets",
        json={"path": "apps/demo", "data": {"api_key": "s3cret", "region": "eu"}},
    )

    assert res.status_code == 201
    body = res.json()
    assert body["path"] == "apps/demo"
    assert sorted(body["keys"]) == ["api_key", "region"]
    assert body["current_version"] == 1
    assert body["versions"] == [1]

    read = await client.get("/api/v-alpha/vault/secrets/apps/demo")
    assert read.status_code == 200
    assert sorted(read.json()["keys"]) == ["api_key", "region"]


@pytest.mark.asyncio
async def test_vault_secret_values_are_never_echoed(
    client: httpx.AsyncClient,
    fake_openbao: FakeOpenBao,
) -> None:
    """The API exposes key names and versions, never secret values."""
    await client.post(
        "/api/v-alpha/vault/secrets",
        json={"path": "apps/demo", "data": {"api_key": "s3cret"}},
    )

    read = await client.get("/api/v-alpha/vault/secrets/apps/demo")
    listed = await client.get("/api/v-alpha/vault/secrets")

    assert "s3cret" not in read.text
    assert "s3cret" not in listed.text
    assert read.json()["keys"] == ["api_key"]
    assert listed.json()["secrets"][0]["path"] == "apps/demo"


@pytest.mark.asyncio
async def test_vault_secret_update_bumps_the_version(
    client: httpx.AsyncClient,
    fake_openbao: FakeOpenBao,
) -> None:
    """Writing the same path again creates a new version."""
    await client.post(
        "/api/v-alpha/vault/secrets",
        json={"path": "apps/demo", "data": {"api_key": "one"}},
    )

    res = await client.post(
        "/api/v-alpha/vault/secrets",
        json={"path": "apps/demo", "data": {"api_key": "two"}},
    )

    assert res.status_code == 201
    assert res.json()["current_version"] == 2
    assert res.json()["versions"] == [1, 2]


@pytest.mark.asyncio
async def test_vault_secret_list_reports_paths_and_keys(
    client: httpx.AsyncClient,
    fake_openbao: FakeOpenBao,
) -> None:
    """The list route reports every stored path with its key names."""
    await client.post(
        "/api/v-alpha/vault/secrets",
        json={"path": "apps/one", "data": {"a": "1"}},
    )
    await client.post(
        "/api/v-alpha/vault/secrets",
        json={"path": "apps/two", "data": {"b": "2", "c": "3"}},
    )

    res = await client.get("/api/v-alpha/vault/secrets")

    assert res.status_code == 200
    secrets = {s["path"]: s for s in res.json()["secrets"]}
    assert set(secrets) == {"apps/one", "apps/two"}
    assert secrets["apps/two"]["keys"] == ["b", "c"]


@pytest.mark.asyncio
async def test_vault_unknown_secret_is_a_404(
    client: httpx.AsyncClient,
    fake_openbao: FakeOpenBao,
) -> None:
    """Reading an unknown secret path is a 404."""
    res = await client.get("/api/v-alpha/vault/secrets/does/not/exist")

    assert res.status_code == 404


@pytest.mark.asyncio
async def test_vault_rejects_an_empty_path(
    client: httpx.AsyncClient,
    fake_openbao: FakeOpenBao,
) -> None:
    """An empty secret path is rejected with a 400."""
    res = await client.post(
        "/api/v-alpha/vault/secrets",
        json={"path": "   ", "data": {"a": "1"}},
    )

    assert res.status_code == 400


@pytest.mark.asyncio
async def test_vault_rejects_empty_secret_data(
    client: httpx.AsyncClient,
    fake_openbao: FakeOpenBao,
) -> None:
    """An empty secret data dictionary is rejected with a 400."""
    res = await client.post(
        "/api/v-alpha/vault/secrets",
        json={"path": "apps/demo", "data": {}},
    )

    assert res.status_code == 400
