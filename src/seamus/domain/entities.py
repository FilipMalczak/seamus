"""Domain entities for agents, sessions, threads, and execution lifecycle."""

import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator

from seamus.config.models import AgentConfig

SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def validate_slug(name: str | None) -> str | None:
    """Validate that an optional name follows the lowercase slug format."""
    if name is None:
        return None
    trimmed = name.strip()
    if not trimmed:
        return None
    if not SLUG_PATTERN.match(trimmed):
        msg = (
            f"Invalid slug name '{name}'. Names must match '^[a-z0-9]+(?:-[a-z0-9]+)*$' "
            "(lowercase alphanumeric characters separated by single hyphens)."
        )
        raise ValueError(msg)
    return trimmed


class AgentStatus(StrEnum):
    """Execution status of an agent within a thread."""

    AWAITING_USER = "AWAITING_USER"
    AWAITING_LLM = "AWAITING_LLM"
    EXECUTING_TOOL = "EXECUTING_TOOL"
    ERROR = "ERROR"


class Thread(BaseModel):
    """A sub-conversation execution thread within a session."""

    id: UUID = Field(default_factory=uuid4)
    name: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_touched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    is_open: bool = True
    status: AgentStatus = AgentStatus.AWAITING_USER
    events: list[Any] = Field(default_factory=list)

    @field_validator("name", mode="before")
    @classmethod
    def _validate_name(cls, v: str | None) -> str | None:
        return validate_slug(v)

    def touch(self) -> None:
        """Update last_touched_at timestamp to current UTC time."""
        self.last_touched_at = datetime.now(UTC)

    def append_event(self, event: Any) -> None:
        """Append an event to the thread's history and touch timestamp."""
        self.events.append(event)
        self.touch()


class Session(BaseModel):
    """A conversation instance with an agent, comprising one or more threads."""

    id: UUID = Field(default_factory=uuid4)
    agent_id: UUID
    name: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_touched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    config: AgentConfig
    threads: dict[UUID, Thread] = Field(default_factory=dict)

    @field_validator("name", mode="before")
    @classmethod
    def _validate_name(cls, v: str | None) -> str | None:
        return validate_slug(v)

    def touch(self) -> None:
        """Update last_touched_at timestamp to current UTC time."""
        self.last_touched_at = datetime.now(UTC)

    def create_thread(self, name: str | None = None) -> Thread:
        """Create a new open thread, closing all previous threads in the session."""
        for thread in self.threads.values():
            thread.is_open = False

        new_thread = Thread(name=name, is_open=True, status=AgentStatus.AWAITING_USER)
        self.threads[new_thread.id] = new_thread
        self.touch()
        return new_thread

    def get_open_thread(self) -> Thread:
        """Return the currently open thread in the session, or create one if none exist."""
        for thread in reversed(list(self.threads.values())):
            if thread.is_open:
                return thread
        # Invariant fallback: if no threads exist or all are closed, open a new thread
        return self.create_thread()


class Agent(BaseModel):
    """An agent entity holding a complete configuration and managing sessions."""

    id: UUID = Field(default_factory=uuid4)
    name: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_touched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    config: AgentConfig
    sessions: dict[UUID, Session] = Field(default_factory=dict)

    @field_validator("name", mode="before")
    @classmethod
    def _validate_name(cls, v: str | None) -> str | None:
        return validate_slug(v)

    def touch(self) -> None:
        """Update last_touched_at timestamp to current UTC time."""
        self.last_touched_at = datetime.now(UTC)

    def create_session(
        self,
        config: AgentConfig | None = None,
        name: str | None = None,
    ) -> Session:
        """Create and register a new session under this agent with an initial open thread."""
        session_config = (
            self.config.copy_with_overrides(config)
            if config is not None
            else self.config.model_copy(deep=True)
        )
        session = Session(
            agent_id=self.id,
            name=name,
            config=session_config,
        )
        # Ensure session starts with an initial open thread
        session.create_thread()
        self.sessions[session.id] = session
        self.touch()
        return session
