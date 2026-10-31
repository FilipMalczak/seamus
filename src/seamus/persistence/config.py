"""Configuration settings for Gitea-backed persistence."""

import os
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field


class PersistenceSettings(BaseModel):
    """Runtime configuration for Gitea and Git workspaces."""

    gitea_url: str = Field(
        default_factory=lambda: os.getenv("GITEA_URL", "http://localhost:3001").rstrip("/")
    )
    gitea_external_url: str = Field(
        default_factory=lambda: os.getenv("GITEA_EXTERNAL_URL", "http://localhost:3001").rstrip("/")
    )
    gitea_admin_user: str = Field(default_factory=lambda: os.getenv("GITEA_ADMIN_USER", "seamus"))
    gitea_admin_password: str = Field(
        default_factory=lambda: os.getenv("GITEA_ADMIN_PASSWORD", "seamus-password-123")
    )
    gitea_admin_email: str = Field(
        default_factory=lambda: os.getenv("GITEA_ADMIN_EMAIL", "seamus@seamus.local")
    )
    workspace_dir: Path = Field(
        default_factory=lambda: Path(
            os.getenv("SEAMUS_WORKSPACE_DIR", ".seamus/workspaces")
        ).resolve()
    )
    enabled: bool = Field(
        default_factory=lambda: (
            os.getenv("SEAMUS_PERSISTENCE_ENABLED", "true").lower() in ("true", "1", "yes")
        )
    )


@lru_cache(maxsize=1)
def get_persistence_settings() -> PersistenceSettings:
    """Return the cached singleton persistence configuration settings."""
    return PersistenceSettings()
