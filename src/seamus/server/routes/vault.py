"""REST API endpoints for the secrets vault under /api/v-alpha/vault."""

import logging

from fastapi import APIRouter, HTTPException, status

from seamus.server.schemas import (
    VaultSecretCreateRequest,
    VaultSecretDetailResponse,
    VaultSecretItem,
    VaultSecretListResponse,
    VaultTokenResponse,
)
from seamus.vault.client import get_default_vault_client
from seamus.vault.models import SecretNotFoundError, VaultConnectionError, VaultError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/vault", tags=["vault"])


@router.get("/token", response_model=VaultTokenResponse)
async def get_vault_token() -> VaultTokenResponse:
    """Return the OpenBao authentication token for UI 'Login via Token' reveal."""
    client = get_default_vault_client()
    return VaultTokenResponse(token=client.settings.resolve_token())


@router.get("/secrets", response_model=VaultSecretListResponse)
async def list_secrets() -> VaultSecretListResponse:
    """List configured secrets paths and their available fields (values redacted)."""
    client = get_default_vault_client()
    try:
        keys = await client.list_secrets()
    except VaultConnectionError as exc:
        logger.warning("Vault connection failed: %s", exc)
        return VaultSecretListResponse(secrets=[])
    except VaultError as exc:
        logger.warning("Vault error listing secrets: %s", exc)
        return VaultSecretListResponse(secrets=[])

    items: list[VaultSecretItem] = []
    for key in keys:
        clean_path = key.strip("/")
        try:
            data, current_v = await client.get_secret_with_version(clean_path)
            items.append(
                VaultSecretItem(
                    path=clean_path,
                    keys=list(data.keys()),
                    version=current_v,
                )
            )
        except Exception as exc:
            logger.debug("Failed to inspect secret %s: %s", clean_path, exc)
            items.append(VaultSecretItem(path=clean_path, keys=[]))

    return VaultSecretListResponse(secrets=items)


@router.post(
    "/secrets",
    response_model=VaultSecretDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_or_update_secret(
    payload: VaultSecretCreateRequest,
) -> VaultSecretDetailResponse:
    """Create or update a secret at the specified path."""
    client = get_default_vault_client()
    clean_path = payload.path.strip().lstrip("/")
    if not clean_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Secret path cannot be empty",
        )
    if not payload.data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Secret data dictionary cannot be empty",
        )

    try:
        resp = await client.set_secret(clean_path, payload.data)
        version = resp.get("version")
        try:
            meta = await client.get_secret_metadata(clean_path)
            all_versions = (
                [int(v) for v in meta.get("versions", {}).keys()]
                if "versions" in meta
                else ([int(version)] if version else [])
            )
        except Exception:
            all_versions = [int(version)] if version else []

        return VaultSecretDetailResponse(
            path=clean_path,
            keys=list(payload.data.keys()),
            current_version=int(version) if version is not None else None,
            versions=sorted(all_versions),
        )
    except VaultConnectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"OpenBao connection failed: {exc}",
        ) from exc
    except VaultError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to write secret: {exc}",
        ) from exc


@router.get("/secrets/{path:path}", response_model=VaultSecretDetailResponse)
async def get_secret_metadata(path: str) -> VaultSecretDetailResponse:
    """Retrieve metadata and available keys for a secret without exposing values."""
    client = get_default_vault_client()
    clean_path = path.strip().lstrip("/")
    try:
        data, version = await client.get_secret_with_version(clean_path)
        try:
            meta = await client.get_secret_metadata(clean_path)
            version = int(meta.get("current_version") or version)
            all_versions = (
                [int(v) for v in meta.get("versions", {}).keys()]
                if "versions" in meta
                else ([version] if version else [])
            )
        except Exception:
            all_versions = [version] if version else []

        return VaultSecretDetailResponse(
            path=clean_path,
            keys=list(data.keys()),
            current_version=version,
            versions=sorted(all_versions),
        )
    except SecretNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except VaultConnectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"OpenBao connection failed: {exc}",
        ) from exc
    except VaultError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
