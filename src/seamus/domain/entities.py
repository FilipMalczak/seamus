"""Domain entities for agents, sessions, threads, and execution lifecycle."""

import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator

from seamus.config.models import AgentConfig
from seamus.domain.modes import ModeName, PlanPhase, normalize_mode_and_phase

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


class SessionStatus(StrEnum):
    """Operational lifecycle status of a session."""

    ACTIVE = "ACTIVE"
    KILLED = "KILLED"
    FAILED = "FAILED"


class SessionBranchProvenance(BaseModel):
    """Lineage provenance recording where a session branched from."""

    parent_session_id: UUID
    parent_message_id: str
    parent_session_name: str | None = None
    branched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Thread(BaseModel):
    """A sub-conversation execution thread within a session."""

    id: UUID = Field(default_factory=uuid4)
    name: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_touched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    is_open: bool = True
    status: AgentStatus = AgentStatus.AWAITING_USER
    mode: str = ModeName.PLAN.value
    phase: str | None = PlanPhase.DISCUSS.value
    events: list[Any] = Field(default_factory=list)

    @property
    def mode_label(self) -> str:
        """Return display label '<mode>' or '<mode>/<phase>'."""
        if self.phase:
            return f"{self.mode}/{self.phase}"
        return self.mode

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

    @property
    def is_empty(self) -> bool:
        """Check if the thread has no recorded events or user exchanges."""
        return len(self.events) == 0


class Session(BaseModel):
    """A conversation instance with an agent, comprising one or more threads."""

    id: UUID = Field(default_factory=uuid4)
    agent_id: UUID
    name: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_touched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    config: AgentConfig
    status: SessionStatus = Field(default=SessionStatus.ACTIVE)
    active_plan_id: str | None = None
    secret_versions: dict[str, int] = Field(default_factory=dict)
    provenance: SessionBranchProvenance | None = None
    lineage: list[SessionBranchProvenance] = Field(default_factory=list)
    threads: dict[UUID, Thread] = Field(default_factory=dict)

    @field_validator("name", mode="before")
    @classmethod
    def _validate_name(cls, v: str | None) -> str | None:
        return validate_slug(v)

    @property
    def is_active(self) -> bool:
        """Check if the session is active (not KILLED or FAILED)."""
        return self.status == SessionStatus.ACTIVE

    def touch(self) -> None:
        """Update last_touched_at timestamp to current UTC time."""
        self.last_touched_at = datetime.now(UTC)

    def kill(self) -> None:
        """Permanently terminate the session by manual user action."""
        self.status = SessionStatus.KILLED
        for thread in self.threads.values():
            thread.is_open = False
        self.touch()

    def fail(self) -> None:
        """Permanently terminate the session due to an unrecoverable failure."""
        self.status = SessionStatus.FAILED
        for thread in self.threads.values():
            if thread.is_open:
                thread.status = AgentStatus.ERROR
            thread.is_open = False
        self.touch()

    def create_thread(
        self,
        name: str | None = None,
        mode: str | None = None,
        phase: str | None = None,
        reuse_empty: bool = True,
    ) -> Thread:
        """Create a new open thread, closing all previous threads in the session.

        If reuse_empty is True (default) and the currently open thread in the session
        is empty (has no events), the open thread is kept and updated in place with the
        new mode, phase, and name rather than creating an unnecessary empty thread.
        """
        if not self.is_active:
            msg = f"Cannot create thread in session '{self.id}' with status '{self.status.value}'."
            raise ValueError(msg)

        inherited_mode = mode
        if inherited_mode is None and self.threads:
            last_thread = list(self.threads.values())[-1]
            inherited_mode = last_thread.mode
        elif inherited_mode is None:
            inherited_mode = getattr(self.config, "mode", None)

        resolved_mode, resolved_phase = normalize_mode_and_phase(inherited_mode, phase)

        if reuse_empty:
            for thread in reversed(list(self.threads.values())):
                if thread.is_open:
                    if thread.is_empty:
                        if name is not None:
                            thread.name = name
                        thread.mode = resolved_mode
                        thread.phase = resolved_phase
                        thread.touch()
                        self.touch()
                        return thread
                    break

        for thread in self.threads.values():
            thread.is_open = False

        new_thread = Thread(
            name=name,
            is_open=True,
            status=AgentStatus.AWAITING_USER,
            mode=resolved_mode,
            phase=resolved_phase,
        )
        self.threads[new_thread.id] = new_thread
        self.touch()
        return new_thread

    def get_open_thread(self) -> Thread:
        """Return the currently open thread in the session, or the latest thread if closed."""
        for thread in reversed(list(self.threads.values())):
            if thread.is_open:
                return thread
        if not self.is_active and self.threads:
            return list(self.threads.values())[-1]
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
        provenance: SessionBranchProvenance | None = None,
        lineage: list[SessionBranchProvenance] | None = None,
    ) -> Session:
        """Create and register a new session under this agent with an initial open thread."""
        session_config = (
            self.config.copy_with_overrides(config)
            if config is not None
            else self.config.model_copy(deep=True)
        )
        resolved_lineage = lineage if lineage is not None else ([provenance] if provenance else [])
        session = Session(
            agent_id=self.id,
            name=name,
            config=session_config,
            provenance=provenance,
            lineage=resolved_lineage,
        )
        # Ensure session starts with an initial open thread
        session.create_thread()
        self.sessions[session.id] = session
        self.touch()
        return session
