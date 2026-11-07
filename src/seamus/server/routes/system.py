"""Routes for system status and external system integration metadata."""

from fastapi import APIRouter

from seamus.persistence import get_persistence_settings
from seamus.server.schemas import (
    SystemGiteaInfo,
    SystemInfoResponse,
    SystemLogfireInfo,
    SystemVaultInfo,
)
from seamus.telemetry import (
    get_logfire_dashboard_url,
    get_logfire_service_name,
    is_logfire_enabled,
)
from seamus.vault.models import VaultSettings

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/info", response_model=SystemInfoResponse)
async def get_system_info() -> SystemInfoResponse:
    """Return system information including external integrations and telemetry status."""
    logfire_on = is_logfire_enabled()
    service_name = get_logfire_service_name()
    logfire_url = get_logfire_dashboard_url()

    persist_settings = get_persistence_settings()
    gitea_on = persist_settings.enabled
    gitea_url = persist_settings.gitea_external_url if gitea_on else None
    gitea_owner = persist_settings.gitea_admin_user if gitea_on else None

    vault_settings = VaultSettings.from_env()

    return SystemInfoResponse(
        logfire=SystemLogfireInfo(
            enabled=logfire_on,
            service_name=service_name,
            url=logfire_url,
        ),
        gitea=SystemGiteaInfo(
            enabled=gitea_on,
            url=gitea_url,
            owner=gitea_owner,
        ),
        vault=SystemVaultInfo(
            enabled=True,
            url=vault_settings.external_url,
            login_url=vault_settings.login_url,
        ),
    )
