"""Identifier resolution utilities for mapping UUIDs and slugs to entities."""

from uuid import UUID

from seamus.domain.entities import Agent, Session, Thread


class EntityNotFoundError(KeyError):
    """Raised when an agent, session, or thread identifier cannot be resolved."""


def parse_uuid(identifier: str) -> UUID | None:
    """Attempt to parse a string as a UUID. Return None if invalid."""
    try:
        return UUID(identifier)
    except (ValueError, TypeError, AttributeError):
        return None


def resolve_session(agent: Agent, identifier: str) -> Session:
    """Resolve a session within an agent by UUID or slug name."""
    as_uuid = parse_uuid(identifier)
    if as_uuid is not None and as_uuid in agent.sessions:
        return agent.sessions[as_uuid]

    for session in agent.sessions.values():
        if session.name == identifier:
            return session

    msg = f"Session '{identifier}' not found in agent '{agent.id}'."
    raise EntityNotFoundError(msg)


def resolve_thread(session: Session, identifier: str) -> Thread:
    """Resolve a thread within a session by UUID or slug name."""
    as_uuid = parse_uuid(identifier)
    if as_uuid is not None and as_uuid in session.threads:
        return session.threads[as_uuid]

    for thread in session.threads.values():
        if thread.name == identifier:
            return thread

    msg = f"Thread '{identifier}' not found in session '{session.id}'."
    raise EntityNotFoundError(msg)
