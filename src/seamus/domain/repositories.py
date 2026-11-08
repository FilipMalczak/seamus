"""Domain models for external Git repository persistence and checkpoints."""

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class MountedRepositoryCheckpointRecord(BaseModel):
    """Metadata recorded for an external repository dual-index snapshot."""

    project_id: str
    attachment_id: str
    mount_name: str
    url: str
    branch: str
    checkpoint_sha: str
    snapshot_tree: str
    semantic_head: str
    semantic_branch: str
    staged_tree: str
    gitea_repo_name: str | None = None
    gitea_repo_url: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class MultiRepoCheckpointManifest(BaseModel):
    """Collection of external repository checkpoints captured for a LangGraph checkpoint."""

    checkpoint_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    repositories: dict[str, MountedRepositoryCheckpointRecord] = Field(default_factory=dict)
