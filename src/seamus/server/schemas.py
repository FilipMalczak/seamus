"""Pydantic schemas for the Seamus REST API under /api/v-alpha/."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from seamus.config.models import AgentConfig
from seamus.domain.entities import AgentStatus


class ConfigTemplateResponse(BaseModel):
    """Response representing the current singleton config template."""

    config: AgentConfig
    is_complete: bool


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


class SessionDetailResponse(BaseModel):
    """Detailed response model for a session including thread listing."""

    id: UUID
    agent_id: UUID
    name: str | None
    created_at: datetime
    last_touched_at: datetime
    config: AgentConfig
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


class SystemInfoResponse(BaseModel):
    """Information about system integrations and external systems."""

    logfire: SystemLogfireInfo
