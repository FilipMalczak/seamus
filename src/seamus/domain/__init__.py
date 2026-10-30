"""Domain package for Seamus entities and identifier resolution."""

from seamus.domain.entities import (
    Agent,
    AgentStatus,
    Session,
    Thread,
    validate_slug,
)
from seamus.domain.resolution import (
    EntityNotFoundError,
    parse_uuid,
    resolve_session,
    resolve_thread,
)

__all__ = [
    "Agent",
    "AgentStatus",
    "EntityNotFoundError",
    "Session",
    "Thread",
    "parse_uuid",
    "resolve_session",
    "resolve_thread",
    "validate_slug",
]
