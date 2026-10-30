"""Routes for system status and external system integration metadata."""

from fastapi import APIRouter

from seamus.server.schemas import SystemInfoResponse, SystemLogfireInfo
from seamus.telemetry import get_logfire_service_name, is_logfire_enabled

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/info", response_model=SystemInfoResponse)
async def get_system_info() -> SystemInfoResponse:
    """Return system information including external integrations and telemetry status."""
    enabled = is_logfire_enabled()
    service_name = get_logfire_service_name()
    url = f"https://logfire-eu.pydantic.dev/filip-malczak/{service_name}" if enabled else None

    return SystemInfoResponse(
        logfire=SystemLogfireInfo(
            enabled=enabled,
            service_name=service_name,
            url=url,
        )
    )
