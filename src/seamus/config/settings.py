"""System settings models and persistent store."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from seamus.persistence.workspace import GitWorkspaceManager

logger = logging.getLogger(__name__)


class SystemSettings(BaseModel):
    """System-wide configuration settings not scoped to any agent or session."""

    skill_directories: list[str] = Field(default_factory=list)


class SystemSettingsStore:
    """Manages the service-wide singleton SystemSettings persisted to Git."""

    def __init__(
        self,
        initial_settings: SystemSettings | None = None,
        workspace_manager: GitWorkspaceManager | None = None,
    ) -> None:
        self._ws_mgr = workspace_manager
        if initial_settings is not None:
            self._settings = initial_settings.model_copy(deep=True)
        else:
            self._settings = self._load_initial_settings()

    def _get_workspace_manager(self) -> GitWorkspaceManager:
        if self._ws_mgr is not None:
            return self._ws_mgr
        from seamus.persistence.workspace import get_workspace_manager

        return get_workspace_manager()

    def _load_initial_settings(self) -> SystemSettings:
        """Attempt to load settings from persistence; fall back to empty defaults."""
        try:
            ws_mgr = self._get_workspace_manager()
            data = ws_mgr.read_system_settings()
            if data is not None:
                return SystemSettings.model_validate(data)
            defaults = SystemSettings()
            ws_mgr.commit_system_settings(defaults.model_dump())
            return defaults
        except Exception:
            logger.debug("Failed to read system settings from workspace; using in-memory defaults")
            return SystemSettings()

    def get_settings(self) -> SystemSettings:
        """Retrieve a copy of current system settings."""
        return self._settings.model_copy(deep=True)

    def set_settings(self, settings: SystemSettings) -> SystemSettings:
        """Update system settings and persist to system repository."""
        self._settings = settings.model_copy(deep=True)
        try:
            ws_mgr = self._get_workspace_manager()
            ws_mgr.commit_system_settings(self._settings.model_dump())
        except Exception:
            logger.exception("Failed to persist system settings to repository")
        return self.get_settings()


_GLOBAL_SETTINGS_STORE: SystemSettingsStore | None = None


def get_system_settings_store() -> SystemSettingsStore:
    """Return the global singleton instance of SystemSettingsStore."""
    global _GLOBAL_SETTINGS_STORE
    if _GLOBAL_SETTINGS_STORE is None:
        _GLOBAL_SETTINGS_STORE = SystemSettingsStore()
    return _GLOBAL_SETTINGS_STORE


def reset_system_settings_store(
    store: SystemSettingsStore | None = None,
) -> SystemSettingsStore:
    """Reset or override the global SystemSettingsStore singleton instance."""
    global _GLOBAL_SETTINGS_STORE
    _GLOBAL_SETTINGS_STORE = store
    return get_system_settings_store()
