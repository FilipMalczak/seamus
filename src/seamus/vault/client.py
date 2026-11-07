"""OpenBao REST API client for secrets management."""

import logging
from typing import Any, cast
from urllib.parse import quote

import httpx

from seamus.vault.models import (
    ResolvedSecretField,
    SecretNotFoundError,
    VaultConnectionError,
    VaultError,
    VaultSettings,
)

logger = logging.getLogger(__name__)


class VaultClient:
    """Async and sync client for OpenBao / Vault KV v2 secrets engine."""

    def __init__(
        self,
        settings: VaultSettings | None = None,
        client: httpx.AsyncClient | None = None,
        sync_client: httpx.Client | None = None,
    ) -> None:
        self.settings = settings or VaultSettings.from_env()
        self._external_client = client
        self._client: httpx.AsyncClient | None = client
        self._sync_client = sync_client

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            headers = {"Content-Type": "application/json"}
            token = self.settings.resolve_token()
            if token:
                headers["X-Vault-Token"] = token
                headers["X-OpenBao-Token"] = token

            self._client = httpx.AsyncClient(
                base_url=self.settings.base_url.rstrip("/"),
                headers=headers,
                timeout=10.0,
            )
        return self._client

    def _get_sync_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        token = self.settings.resolve_token()
        if token:
            headers["X-Vault-Token"] = token
            headers["X-OpenBao-Token"] = token
        return headers

    async def close(self) -> None:
        """Close the underlying HTTP client if managed internally."""
        if (
            self._external_client is None
            and self._client is not None
            and not self._client.is_closed
        ):
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> "VaultClient":
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    def _format_path(self, path: str) -> str:
        clean = path.strip().lstrip("/")
        return "/".join(quote(seg, safe="") for seg in clean.split("/") if seg)

    async def health(self) -> dict[str, Any]:
        """Check vault health status."""
        client = await self._get_client()
        try:
            resp = await client.get("/v1/sys/health")
            return cast(dict[str, Any], resp.json())
        except httpx.HTTPError as exc:
            msg = f"Failed to connect to OpenBao at {self.settings.base_url}: {exc}"
            raise VaultConnectionError(msg) from exc

    async def get_secret_with_version(
        self,
        path: str,
        version: int | None = None,
    ) -> tuple[dict[str, Any], int]:
        """Fetch secret data document and its version at the given path in KV v2."""
        client = await self._get_client()
        formatted_path = self._format_path(path)
        url = f"/v1/{self.settings.mount}/data/{formatted_path}"
        params: dict[str, Any] = {}
        if version is not None:
            params["version"] = version

        try:
            resp = await client.get(url, params=params)
        except httpx.HTTPError as exc:
            msg = f"Vault connection failed when reading {path!r}: {exc}"
            raise VaultConnectionError(msg) from exc

        if resp.status_code == 404:
            msg = f"Secret not found at path {path!r} (version={version})"
            raise SecretNotFoundError(msg)

        if not resp.is_success:
            msg = f"Vault returned HTTP {resp.status_code} for {path!r}: {resp.text}"
            raise VaultError(msg)

        payload = resp.json()
        outer_data = payload.get("data", {})
        data = outer_data.get("data")
        if data is None:
            msg = f"Secret data missing from vault response for {path!r}"
            raise SecretNotFoundError(msg)

        meta = outer_data.get("metadata", {})
        resolved_version = int(meta.get("version") or version or 1)
        return cast(dict[str, Any], data), resolved_version

    async def get_secret(
        self,
        path: str,
        version: int | None = None,
    ) -> dict[str, Any]:
        """Fetch secret data document at the given path in KV v2."""
        data, _ = await self.get_secret_with_version(path=path, version=version)
        return data

    async def get_secret_field_with_version(
        self,
        path: str,
        field: str = "value",
        version: int | None = None,
    ) -> ResolvedSecretField:
        """Fetch a specific string field and its version from the secret document."""
        data, resolved_version = await self.get_secret_with_version(path=path, version=version)
        if field not in data:
            available = list(data.keys())
            msg = (
                f"Field {field!r} not found in secret at path {path!r} "
                f"(version={version}). Available fields: {available}"
            )
            raise SecretNotFoundError(msg)
        val = data[field]
        if not isinstance(val, str):
            msg = (
                f"Secret field {field!r} at path {path!r} must be a string, "
                f"got {type(val).__name__}"
            )
            raise VaultError(msg)
        return ResolvedSecretField(value=val, version=resolved_version)

    async def get_secret_field(
        self,
        path: str,
        field: str = "value",
        version: int | None = None,
    ) -> str:
        """Fetch a specific field from the secret document at the given path."""
        res = await self.get_secret_field_with_version(path=path, field=field, version=version)
        return res.value

    def get_secret_with_version_sync(
        self,
        path: str,
        version: int | None = None,
    ) -> tuple[dict[str, Any], int]:
        """Synchronously fetch secret data document and its version at the given path in KV v2."""
        formatted_path = self._format_path(path)
        url = f"{self.settings.base_url.rstrip('/')}/v1/{self.settings.mount}/data/{formatted_path}"
        params: dict[str, Any] = {}
        if version is not None:
            params["version"] = version

        try:
            if self._sync_client:
                resp = self._sync_client.get(url, params=params)
            else:
                with httpx.Client(headers=self._get_sync_headers(), timeout=10.0) as client:
                    resp = client.get(url, params=params)
        except httpx.HTTPError as exc:
            msg = f"Vault connection failed when reading {path!r}: {exc}"
            raise VaultConnectionError(msg) from exc

        if resp.status_code == 404:
            msg = f"Secret not found at path {path!r} (version={version})"
            raise SecretNotFoundError(msg)

        if not resp.is_success:
            msg = f"Vault returned HTTP {resp.status_code} for {path!r}: {resp.text}"
            raise VaultError(msg)

        payload = resp.json()
        outer_data = payload.get("data", {})
        data = outer_data.get("data")
        if data is None:
            msg = f"Secret data missing from vault response for {path!r}"
            raise SecretNotFoundError(msg)

        meta = outer_data.get("metadata", {})
        resolved_version = int(meta.get("version") or version or 1)
        return cast(dict[str, Any], data), resolved_version

    def get_secret_sync(
        self,
        path: str,
        version: int | None = None,
    ) -> dict[str, Any]:
        """Synchronously fetch secret data document at the given path in KV v2."""
        data, _ = self.get_secret_with_version_sync(path=path, version=version)
        return data

    def get_secret_field_with_version_sync(
        self,
        path: str,
        field: str = "value",
        version: int | None = None,
    ) -> ResolvedSecretField:
        """Synchronously fetch a specific string field and its version from the secret document."""
        data, resolved_version = self.get_secret_with_version_sync(path=path, version=version)
        if field not in data:
            available = list(data.keys())
            msg = (
                f"Field {field!r} not found in secret at path {path!r} "
                f"(version={version}). Available fields: {available}"
            )
            raise SecretNotFoundError(msg)
        val = data[field]
        if not isinstance(val, str):
            msg = (
                f"Secret field {field!r} at path {path!r} must be a string, "
                f"got {type(val).__name__}"
            )
            raise VaultError(msg)
        return ResolvedSecretField(value=val, version=resolved_version)

    def get_secret_field_sync(
        self,
        path: str,
        field: str = "value",
        version: int | None = None,
    ) -> str:
        """Synchronously fetch a specific field from the secret document."""
        res = self.get_secret_field_with_version_sync(path=path, field=field, version=version)
        return res.value

    async def set_secret(
        self,
        path: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """Store or update a secret document at the given path in KV v2."""
        client = await self._get_client()
        formatted_path = self._format_path(path)
        url = f"/v1/{self.settings.mount}/data/{formatted_path}"

        try:
            resp = await client.post(url, json={"data": data})
        except httpx.HTTPError as exc:
            msg = f"Vault connection failed when writing {path!r}: {exc}"
            raise VaultConnectionError(msg) from exc

        if not resp.is_success:
            msg = f"Vault returned HTTP {resp.status_code} writing {path!r}: {resp.text}"
            raise VaultError(msg)

        payload = resp.json()
        return cast(dict[str, Any], payload.get("data", {}))

    async def list_secrets(self, path: str = "", recursive: bool = True) -> list[str]:
        """List secret paths under a prefix, optionally recursing into subfolders."""
        client = await self._get_client()
        formatted_path = self._format_path(path)
        if formatted_path:
            url = f"/v1/{self.settings.mount}/metadata/{formatted_path}"
        else:
            url = f"/v1/{self.settings.mount}/metadata"

        try:
            resp = await client.get(url, params={"list": "true"})
        except httpx.HTTPError as exc:
            msg = f"Vault connection failed listing {path!r}: {exc}"
            raise VaultConnectionError(msg) from exc

        if resp.status_code == 404:
            return []

        if not resp.is_success:
            msg = f"Vault returned HTTP {resp.status_code} listing {path!r}: {resp.text}"
            raise VaultError(msg)

        payload = resp.json()
        raw_keys = list(payload.get("data", {}).get("keys", []))
        if not recursive:
            return raw_keys

        results: list[str] = []
        for k in raw_keys:
            sub = f"{path.strip('/')}/{k}" if path.strip("/") else k
            if k.endswith("/"):
                sub_results = await self.list_secrets(sub.rstrip("/"), recursive=True)
                results.extend(sub_results)
            else:
                results.append(sub)
        return results

    async def get_secret_metadata(self, path: str) -> dict[str, Any]:
        """Get secret metadata (versions, created times, deletion status)."""
        client = await self._get_client()
        formatted_path = self._format_path(path)
        url = f"/v1/{self.settings.mount}/metadata/{formatted_path}"

        try:
            resp = await client.get(url)
        except httpx.HTTPError as exc:
            msg = f"Vault connection failed fetching metadata for {path!r}: {exc}"
            raise VaultConnectionError(msg) from exc

        if resp.status_code == 404:
            msg = f"Secret metadata not found at path {path!r}"
            raise SecretNotFoundError(msg)

        if not resp.is_success:
            msg = f"Vault returned HTTP {resp.status_code} for {path!r}: {resp.text}"
            raise VaultError(msg)

        payload = resp.json()
        return cast(dict[str, Any], payload.get("data", {}))

    def get_secret_metadata_sync(self, path: str) -> dict[str, Any]:
        """Synchronously get secret metadata."""
        formatted_path = self._format_path(path)
        url = (
            f"{self.settings.base_url.rstrip('/')}/v1/"
            f"{self.settings.mount}/metadata/{formatted_path}"
        )

        try:
            if self._sync_client:
                resp = self._sync_client.get(url)
            else:
                with httpx.Client(headers=self._get_sync_headers(), timeout=10.0) as client:
                    resp = client.get(url)
        except httpx.HTTPError as exc:
            msg = f"Vault connection failed fetching metadata for {path!r}: {exc}"
            raise VaultConnectionError(msg) from exc

        if resp.status_code == 404:
            msg = f"Secret metadata not found at path {path!r}"
            raise SecretNotFoundError(msg)

        if not resp.is_success:
            msg = f"Vault returned HTTP {resp.status_code} for {path!r}: {resp.text}"
            raise VaultError(msg)

        payload = resp.json()
        return cast(dict[str, Any], payload.get("data", {}))


_DEFAULT_VAULT_CLIENT: VaultClient | None = None


def get_default_vault_client() -> VaultClient:
    """Return the global singleton VaultClient initialized from environment settings."""
    global _DEFAULT_VAULT_CLIENT
    if _DEFAULT_VAULT_CLIENT is None:
        _DEFAULT_VAULT_CLIENT = VaultClient(settings=VaultSettings.from_env())
    return _DEFAULT_VAULT_CLIENT


def reset_default_vault_client(client: VaultClient | None = None) -> None:
    """Reset or override the global singleton VaultClient (useful in tests)."""
    global _DEFAULT_VAULT_CLIENT
    _DEFAULT_VAULT_CLIENT = client

