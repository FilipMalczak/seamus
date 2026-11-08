"""Persistence subsystem managing Gitea-backed Git repositories and workspaces."""

from seamus.persistence.checkpointer import (
    GitCheckpointSaver,
    extract_readable_messages,
)
from seamus.persistence.client import GiteaClient
from seamus.persistence.config import PersistenceSettings, get_persistence_settings
from seamus.persistence.external_repo import (
    ExternalRepositoryManager,
    calculate_mount_paths,
    canonicalize_git_url,
    derive_project_id,
    derive_repository_mount_name,
    get_external_repo_manager,
    reset_external_repo_manager,
)
from seamus.persistence.workspace import (
    GitWorkspaceManager,
    get_workspace_manager,
    parse_stored_event,
    reset_workspace_manager,
)

__all__ = [
    "ExternalRepositoryManager",
    "GiteaClient",
    "GitCheckpointSaver",
    "GitWorkspaceManager",
    "PersistenceSettings",
    "calculate_mount_paths",
    "canonicalize_git_url",
    "derive_project_id",
    "derive_repository_mount_name",
    "extract_readable_messages",
    "get_external_repo_manager",
    "get_persistence_settings",
    "get_workspace_manager",
    "parse_stored_event",
    "reset_external_repo_manager",
    "reset_workspace_manager",
]
