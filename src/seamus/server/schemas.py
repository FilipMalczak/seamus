"""Pydantic schemas for the Seamus REST API under /api/v-alpha/."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from seamus.config.models import AgentConfig
from seamus.config.settings import SystemSettings
from seamus.domain.entities import (
    AgentStatus,
    SessionBranchProvenance,
    SessionStatus,
)
from seamus.harness.inspector import (
    AgentInspectReport,
    GitInspectInfo,
    HistoryInspectInfo,
    InferenceInspectInfo,
    MessageHistoryItem,
    PromptInspectInfo,
    SkillInspectInfo,
    SubAgentInspectInfo,
    ToolInspectInfo,
    WorkspaceInspectInfo,
)

__all__ = [
    "AgentCreateRequest",
    "AgentDetailResponse",
    "AgentInspectReport",
    "AgentSummaryResponse",
    "AgentUpdateRequest",
    "BranchSessionRequest",
    "ConfigTemplateResponse",
    "GitInspectInfo",
    "HistoryInspectInfo",
    "InferenceInspectInfo",
    "MessageHistoryItem",
    "PromptInspectInfo",
    "SessionCreateRequest",
    "SessionDetailResponse",
    "SessionModeSwitchRequest",
    "SessionSummaryResponse",
    "SessionUpdateRequest",
    "SkillInspectInfo",
    "SubAgentInspectInfo",
    "SystemGiteaInfo",
    "SystemInfoResponse",
    "SystemLogfireInfo",
    "SystemSettingsResponse",
    "SystemVaultInfo",
    "ThreadCreateRequest",
    "ThreadResponse",
    "ThreadUpdateRequest",
    "ToolInspectInfo",
    "UserInputRequest",
    "VaultSecretCreateRequest",
    "VaultSecretDetailResponse",
    "VaultSecretItem",
    "VaultSecretListResponse",
    "VaultTokenResponse",
    "WorkspaceInspectInfo",
]


class ConfigTemplateResponse(BaseModel):
    """Response representing the current singleton config template."""

    config: AgentConfig
    is_complete: bool


class SystemSettingsResponse(BaseModel):
    """Response representing the current system-wide settings."""

    settings: SystemSettings


class AgentCreateRequest(BaseModel):
    """Request payload for creating a new agent."""

    name: str | None = None
    config: AgentConfig | None = None


class AgentUpdateRequest(BaseModel):
    """Request payload for updating an agent with the full updated object."""

    name: str | None = None
    config: AgentConfig


class SessionCreateRequest(BaseModel):
    """Request payload for creating a new session under an agent."""

    name: str | None = None
    config: AgentConfig | None = None


class SessionUpdateRequest(BaseModel):
    """Request payload for updating a session with the full updated object."""

    name: str | None = None
    config: AgentConfig


class SessionModeSwitchRequest(BaseModel):
    """Request payload for switching the operational mode of a session."""

    mode: Literal["chat", "plan"]


class BranchSessionRequest(BaseModel):
    """Request payload for branching a session from a completed assistant message."""

    message_id: str
    name: str | None = None
    retry_inference: bool = False


class ThreadCreateRequest(BaseModel):
    """Request payload for creating a new thread in a session."""

    name: str | None = None


class ThreadUpdateRequest(BaseModel):
    """Request payload for updating a thread's metadata."""

    name: str | None = None


class UserInputRequest(BaseModel):
    """Request payload for posting user input to a session."""

    message: str | None = None
    text: str | None = None
    message_id: str | None = None

    def get_text(self) -> str:
        """Return the user message text from either 'message' or 'text'."""
        val = self.message if self.message is not None else self.text
        if not val or not val.strip():
            msg = "User message text cannot be empty."
            raise ValueError(msg)
        return val.strip()


class ThreadResponse(BaseModel):
    """Response model for a thread."""

    id: UUID
    name: str | None
    created_at: datetime
    last_touched_at: datetime
    is_open: bool
    status: AgentStatus
    mode: str = "chat"
    phase: str | None = None
    mode_label: str = "chat"


class ThreadStatusResponse(BaseModel):
    """Response model for thread status check."""

    status: AgentStatus


class SessionSummaryResponse(BaseModel):
    """Summary response model for a session."""

    id: UUID
    agent_id: UUID
    name: str | None
    created_at: datetime
    last_touched_at: datetime
    config: AgentConfig
    status: SessionStatus = SessionStatus.ACTIVE
    active_plan_id: str | None = None
    provenance: SessionBranchProvenance | None = None
    lineage: list[SessionBranchProvenance] = Field(default_factory=list)


class SessionDetailResponse(BaseModel):
    """Detailed response model for a session including thread listing."""

    id: UUID
    agent_id: UUID
    name: str | None
    created_at: datetime
    last_touched_at: datetime
    config: AgentConfig
    status: SessionStatus = SessionStatus.ACTIVE
    active_plan_id: str | None = None
    provenance: SessionBranchProvenance | None = None
    lineage: list[SessionBranchProvenance] = Field(default_factory=list)
    threads: list[ThreadResponse]


class AgentSummaryResponse(BaseModel):
    """Summary response model for an agent."""

    id: UUID
    name: str | None
    created_at: datetime
    last_touched_at: datetime
    config: AgentConfig


class AgentDetailResponse(BaseModel):
    """Detailed response model for an agent including its session list."""

    id: UUID
    name: str | None
    created_at: datetime
    last_touched_at: datetime
    config: AgentConfig
    sessions: list[SessionSummaryResponse]


class SystemLogfireInfo(BaseModel):
    """Information about Logfire telemetry integration."""

    enabled: bool
    service_name: str
    url: str | None = None


class SystemGiteaInfo(BaseModel):
    """Information about Gitea persistence integration."""

    enabled: bool
    url: str | None = None
    owner: str | None = None


class SystemVaultInfo(BaseModel):
    """Information about OpenBao secrets vault integration."""

    enabled: bool = True
    url: str | None = None
    login_url: str | None = None


class SystemInfoResponse(BaseModel):
    """Information about system integrations and external systems."""

    logfire: SystemLogfireInfo
    gitea: SystemGiteaInfo
    vault: SystemVaultInfo = Field(default_factory=SystemVaultInfo)


class VaultSecretItem(BaseModel):
    """Summary of a secret stored in OpenBao."""

    path: str
    keys: list[str] = Field(default_factory=list)
    version: int | None = None


class VaultSecretListResponse(BaseModel):
    """Response listing all secret paths and their field keys in OpenBao."""

    secrets: list[VaultSecretItem] = Field(default_factory=list)


class VaultSecretCreateRequest(BaseModel):
    """Request payload for creating or updating a secret in OpenBao."""

    path: str
    data: dict[str, str]


class VaultSecretDetailResponse(BaseModel):
    """Detailed metadata response for a secret in OpenBao (without plaintext values)."""

    path: str
    keys: list[str] = Field(default_factory=list)
    current_version: int | None = None
    versions: list[int] = Field(default_factory=list)


class VaultTokenResponse(BaseModel):
    """Response containing the OpenBao login token."""

    token: str | None = None


class SessionDiffResponse(BaseModel):
    """Response model containing active Sync PR diff for a session."""

    agent_id: UUID
    session_id: UUID
    pr_number: int | None = None
    pr_url: str | None = None
    diff: str = ""
