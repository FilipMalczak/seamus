"""Routes for system-wide settings."""

from fastapi import APIRouter

from seamus.config.settings import SystemSettings, get_system_settings_store
from seamus.server.schemas import SystemSettingsResponse

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=SystemSettingsResponse)
async def get_settings() -> SystemSettingsResponse:
    """Retrieve the current system-wide settings."""
    store = get_system_settings_store()
    return SystemSettingsResponse(settings=store.get_settings())


@router.post("", response_model=SystemSettingsResponse)
async def update_settings(payload: SystemSettings) -> SystemSettingsResponse:
    """Update and persist the system-wide settings."""
    store = get_system_settings_store()
    updated = store.set_settings(payload)
    return SystemSettingsResponse(settings=updated)
