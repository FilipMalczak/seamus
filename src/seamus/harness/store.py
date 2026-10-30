"""In-memory repository store for agents, sessions, and threads."""

from uuid import UUID

import logfire

from seamus.config.models import AgentConfig
from seamus.domain.entities import Agent, Session, Thread
from seamus.domain.resolution import (
    EntityNotFoundError,
    parse_uuid,
    resolve_session,
    resolve_thread,
)


class SlugConflictError(ValueError):
    """Raised when an entity slug conflicts with an existing entity in the same scope."""


class HarnessStore:
    """In-memory storage manager for agents, sessions, and threads."""

    def __init__(self) -> None:
        self._agents: dict[UUID, Agent] = {}

    def list_agents(self) -> list[Agent]:
        """Return a list of all registered agents sorted by creation time."""
        return sorted(self._agents.values(), key=lambda a: a.created_at)

    def resolve_agent(self, identifier: str) -> Agent:
        """Resolve an agent by UUID or slug name."""
        as_uuid = parse_uuid(identifier)
        if as_uuid is not None and as_uuid in self._agents:
            return self._agents[as_uuid]

        for agent in self._agents.values():
            if agent.name == identifier:
                return agent

        msg = f"Agent '{identifier}' not found."
        raise EntityNotFoundError(msg)

    def _ensure_agent_slug_unique(self, name: str | None, current_agent_id: UUID | None) -> None:
        if name is None:
            return
        for agent in self._agents.values():
            if agent.id != current_agent_id and agent.name == name:
                msg = f"Agent slug '{name}' is already in use by agent '{agent.id}'."
                raise SlugConflictError(msg)

    def _ensure_session_slug_unique(
        self, agent: Agent, name: str | None, current_session_id: UUID | None
    ) -> None:
        if name is None:
            return
        for session in agent.sessions.values():
            if session.id != current_session_id and session.name == name:
                msg = f"Session slug '{name}' is already in use in agent '{agent.id}'."
                raise SlugConflictError(msg)

    def _ensure_thread_slug_unique(
        self, session: Session, name: str | None, current_thread_id: UUID | None
    ) -> None:
        if name is None:
            return
        for thread in session.threads.values():
            if thread.id != current_thread_id and thread.name == name:
                msg = f"Thread slug '{name}' is already in use in session '{session.id}'."
                raise SlugConflictError(msg)

    def create_agent(self, config: AgentConfig, name: str | None = None) -> Agent:
        """Create a new agent after validating complete configuration and slug uniqueness."""
        config.validate_complete()
        self._ensure_agent_slug_unique(name, current_agent_id=None)

        agent = Agent(name=name, config=config)
        agent_ident = agent.name or str(agent.id)
        with logfire.span(
            f"agent {agent_ident}",
            agent_id=str(agent.id),
            agent_name=agent.name,
            agent_identifier=agent_ident,
            operation="create",
        ):
            # Automatically create initial no-name session (which creates an open thread)
            agent.create_session(name=None)
            self._agents[agent.id] = agent
            return agent

    def update_agent(
        self,
        identifier: str,
        config: AgentConfig,
        name: str | None,
    ) -> Agent:
        """Update an agent's configuration and optional name with the full updated object."""
        agent = self.resolve_agent(identifier)
        config.validate_complete()
        self._ensure_agent_slug_unique(name, current_agent_id=agent.id)

        agent_ident = name or str(agent.id)
        with logfire.span(
            f"agent {agent_ident}",
            agent_id=str(agent.id),
            agent_name=name,
            agent_identifier=agent_ident,
            operation="update",
        ):
            agent.name = name
            agent.config = config.model_copy(deep=True)
            agent.touch()
            return agent

    def create_session(
        self,
        agent_identifier: str,
        config: AgentConfig | None = None,
        name: str | None = None,
    ) -> Session:
        """Create a new session within the resolved agent."""
        agent = self.resolve_agent(agent_identifier)
        self._ensure_session_slug_unique(agent, name, current_session_id=None)

        agent_ident = agent.name or str(agent.id)
        with logfire.span(
            f"agent {agent_ident}",
            agent_id=str(agent.id),
            agent_name=agent.name,
            agent_identifier=agent_ident,
        ):
            session = agent.create_session(config=config, name=name)
            session_ident = session.name or str(session.id)
            with logfire.span(
                f"session {session_ident}",
                session_id=str(session.id),
                session_name=session.name,
                session_identifier=session_ident,
                agent_id=str(agent.id),
                operation="create",
            ):
                session.config.validate_complete()
                return session

    def update_session(
        self,
        agent_identifier: str,
        session_identifier: str,
        config: AgentConfig,
        name: str | None,
    ) -> Session:
        """Update a session's configuration and optional name with the full updated object."""
        agent = self.resolve_agent(agent_identifier)
        session = resolve_session(agent, session_identifier)
        config.validate_complete()
        self._ensure_session_slug_unique(agent, name, current_session_id=session.id)

        session_ident = name or str(session.id)
        with logfire.span(
            f"session {session_ident}",
            session_id=str(session.id),
            session_name=name,
            session_identifier=session_ident,
            agent_id=str(agent.id),
            operation="update",
        ):
            session.name = name
            session.config = config.model_copy(deep=True)
            session.touch()
            agent.touch()
            return session

    def create_thread(
        self,
        agent_identifier: str,
        session_identifier: str,
        name: str | None = None,
    ) -> Thread:
        """Create a new thread within the resolved session."""
        agent = self.resolve_agent(agent_identifier)
        session = resolve_session(agent, session_identifier)
        self._ensure_thread_slug_unique(session, name, current_thread_id=None)

        agent_ident = agent.name or str(agent.id)
        session_ident = session.name or str(session.id)
        with logfire.span(
            f"agent {agent_ident}",
            agent_id=str(agent.id),
            agent_name=agent.name,
            agent_identifier=agent_ident,
        ):
            with logfire.span(
                f"session {session_ident}",
                session_id=str(session.id),
                session_name=session.name,
                session_identifier=session_ident,
                agent_id=str(agent.id),
            ):
                thread = session.create_thread(name=name)
                thread_ident = thread.name or str(thread.id)
                with logfire.span(
                    f"thread {thread_ident}",
                    thread_id=str(thread.id),
                    thread_name=thread.name,
                    thread_identifier=thread_ident,
                    session_id=str(session.id),
                    agent_id=str(agent.id),
                    operation="create",
                ):
                    agent.touch()
                    return thread

    def update_thread(
        self,
        agent_identifier: str,
        session_identifier: str,
        thread_identifier: str,
        name: str | None,
    ) -> Thread:
        """Update a thread's name with the full updated object."""
        agent = self.resolve_agent(agent_identifier)
        session = resolve_session(agent, session_identifier)
        thread = resolve_thread(session, thread_identifier)
        self._ensure_thread_slug_unique(session, name, current_thread_id=thread.id)

        thread_ident = name or str(thread.id)
        with logfire.span(
            f"thread {thread_ident}",
            thread_id=str(thread.id),
            thread_name=name,
            thread_identifier=thread_ident,
            session_id=str(session.id),
            agent_id=str(agent.id),
            operation="update",
        ):
            thread.name = name
            thread.touch()
            session.touch()
            agent.touch()
            return thread


_GLOBAL_STORE: HarnessStore | None = None


def get_harness_store() -> HarnessStore:
    """Return the singleton instance of HarnessStore."""
    global _GLOBAL_STORE
    if _GLOBAL_STORE is None:
        _GLOBAL_STORE = HarnessStore()
    return _GLOBAL_STORE


def reset_harness_store(store: HarnessStore | None = None) -> HarnessStore:
    """Reset the global singleton store (useful in tests)."""
    global _GLOBAL_STORE
    _GLOBAL_STORE = store
    return get_harness_store()
