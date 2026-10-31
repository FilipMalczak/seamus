"""In-memory repository store for agents, sessions, and threads with Gitea Git persistence."""

import json
import logging
from datetime import UTC, datetime
from uuid import UUID

import logfire

from seamus.config.models import AgentConfig
from seamus.domain.entities import Agent, AgentStatus, Session, Thread
from seamus.domain.resolution import (
    EntityNotFoundError,
    parse_uuid,
    resolve_session,
    resolve_thread,
)
from seamus.persistence import get_workspace_manager, parse_stored_event

logger = logging.getLogger(__name__)


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
            initial_session = agent.create_session(name=None)
            self._agents[agent.id] = agent

            # Synchronize with Gitea Git repository
            try:
                ws_mgr = get_workspace_manager()
                ws_mgr.initialize_agent_repo(agent)
                ws_mgr.create_session_workspace(initial_session, agent)
                ws_mgr.open_sync_pr(initial_session, agent)
            except Exception:
                logger.exception("Failed to initialize git repository for agent %s", agent.id)

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

            try:
                get_workspace_manager().commit_agent_config(agent)
            except Exception:
                logger.exception("Failed to commit updated agent config for %s", agent.id)

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

                try:
                    ws_mgr = get_workspace_manager()
                    ws_mgr.create_session_workspace(session, agent)
                    ws_mgr.open_sync_pr(session, agent)
                except Exception:
                    logger.exception("Failed to initialize session workspace for %s", session.id)

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

            try:
                get_workspace_manager().commit_session_config(session)
            except Exception:
                logger.exception("Failed to commit updated session config for %s", session.id)

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
                    try:
                        get_workspace_manager().commit_session_config(session)
                    except Exception:
                        logger.exception(
                            "Failed to commit session thread creation for %s", session.id
                        )

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

            try:
                get_workspace_manager().commit_session_config(session)
            except Exception:
                logger.exception("Failed to commit session thread update for %s", session.id)

            return thread

    def accept_thread(
        self,
        agent_identifier: str,
        session_identifier: str,
        thread_identifier: str,
    ) -> Thread:
        """Accept the active thread, merge its Sync PR, and spawn a new thread with a new PR."""
        agent = self.resolve_agent(agent_identifier)
        session = resolve_session(agent, session_identifier)
        thread = resolve_thread(session, thread_identifier)

        if not thread.is_open:
            raise ValueError(f"Thread '{thread_identifier}' is already closed.")

        agent_ident = agent.name or str(agent.id)
        session_ident = session.name or str(session.id)
        thread_ident = thread.name or str(thread.id)

        with logfire.span(
            f"thread {thread_ident}",
            thread_id=str(thread.id),
            thread_name=thread.name,
            thread_identifier=thread_ident,
            session_id=str(session.id),
            session_identifier=session_ident,
            agent_id=str(agent.id),
            agent_identifier=agent_ident,
            operation="accept",
        ):
            # 1. Close current thread
            thread.is_open = False
            thread.touch()
            session.touch()
            agent.touch()

            ws_mgr = get_workspace_manager()

            # 2. Commit closed thread state to session branch
            try:
                ws_mgr.commit_session_config(session)
            except Exception:
                logger.exception(
                    "Failed to commit session config upon thread close for %s", session.id
                )

            # 3. Approve and merge active Sync PR into main
            try:
                ws_mgr.merge_sync_pr(session, agent)
            except Exception:
                logger.exception("Failed to merge Sync PR for session %s", session.id)

            # 4. Open a new thread on the same session branch
            new_thread = session.create_thread()
            session.touch()
            agent.touch()

            # 5. Commit session config with the new thread and open a renewed Sync PR
            try:
                ws_mgr.commit_session_config(session)
            except Exception:
                logger.exception("Failed to commit session config for new thread in %s", session.id)

            try:
                ws_mgr.open_sync_pr(session, agent)
            except Exception:
                logger.exception("Failed to open renewed Sync PR for session %s", session.id)

            return new_thread

    def hydrate_from_gitea(self) -> None:
        """Discover existing agent repositories from Gitea and reconstruct domain entities."""
        ws_mgr = get_workspace_manager()
        client = ws_mgr.client
        if not ws_mgr.settings.enabled or not client.is_healthy():
            return

        try:
            repos = client.list_user_repos()
            for repo in repos:
                repo_name = repo.get("name", "")
                if not repo_name.startswith("agent-"):
                    continue
                agent_id_str = repo_name[len("agent-") :]
                agent_id = parse_uuid(agent_id_str)
                if agent_id is None or agent_id in self._agents:
                    continue

                main_raw = client.get_file_content(
                    repo_name, "main", "agent/config/config.json"
                ) or client.get_file_content(repo_name, "main", "config/config.json")
                if not main_raw:
                    continue
                try:
                    agent_payload = json.loads(main_raw)
                    agent_config = AgentConfig.model_validate(agent_payload.get("config", {}))
                    created_at_str = agent_payload.get("created_at")
                    agent_created_at = (
                        datetime.fromisoformat(created_at_str)
                        if created_at_str
                        else datetime.now(UTC)
                    )
                    agent = Agent(
                        id=agent_id,
                        name=agent_payload.get("name"),
                        config=agent_config,
                        created_at=agent_created_at,
                    )
                except Exception:
                    logger.exception("Failed to reconstruct agent from repo %s", repo_name)
                    continue

                branches = client.list_branches(repo_name)
                for branch in branches:
                    if not branch.startswith("session/"):
                        continue
                    session_id_str = branch[len("session/") :]
                    session_id = parse_uuid(session_id_str)
                    if session_id is None:
                        continue

                    session_raw = client.get_file_content(
                        repo_name, branch, "agent/config/config.json"
                    ) or client.get_file_content(repo_name, branch, "config/config.json")
                    if not session_raw:
                        continue
                    try:
                        session_payload = json.loads(session_raw)
                        session_config = AgentConfig.model_validate(
                            session_payload.get("config", {})
                        )
                        session_created_at_str = session_payload.get("created_at")
                        session_created_at = (
                            datetime.fromisoformat(session_created_at_str)
                            if session_created_at_str
                            else datetime.now(UTC)
                        )
                        session = Session(
                            id=session_id,
                            agent_id=agent.id,
                            name=session_payload.get("name"),
                            config=session_config,
                            created_at=session_created_at,
                        )

                        threads_data = session_payload.get("threads", [])
                        for t_data in threads_data:
                            t_id = parse_uuid(t_data.get("id"))
                            if t_id is not None:
                                t_created_at_str = t_data.get("created_at")
                                t_created_at = (
                                    datetime.fromisoformat(t_created_at_str)
                                    if t_created_at_str
                                    else datetime.now(UTC)
                                )
                                status_str = t_data.get("status", "AWAITING_USER")
                                status_enum = (
                                    AgentStatus(status_str)
                                    if status_str in AgentStatus.__members__
                                    else AgentStatus.AWAITING_USER
                                )
                                thread = Thread(
                                    id=t_id,
                                    name=t_data.get("name"),
                                    is_open=bool(t_data.get("is_open", False)),
                                    status=status_enum,
                                    created_at=t_created_at,
                                )

                                # Hydrate thread events from Gitea or local workspace
                                events_raw = client.get_file_content(
                                    repo_name,
                                    branch,
                                    f"agent/state/threads/{thread.id}/events.json",
                                )
                                if events_raw:
                                    try:
                                        events_data = json.loads(events_raw)
                                        if isinstance(events_data, list):
                                            thread.events = [
                                                parse_stored_event(ev) for ev in events_data
                                            ]
                                    except Exception:
                                        logger.exception(
                                            "Failed to parse events for thread %s in branch %s",
                                            thread.id,
                                            branch,
                                        )
                                else:
                                    try:
                                        ws_mgr = get_workspace_manager()
                                        local_events = ws_mgr.load_thread_events(
                                            agent.id, session.id, thread.id
                                        )
                                        if local_events:
                                            thread.events = local_events
                                    except Exception:
                                        pass

                                session.threads[thread.id] = thread

                        session.get_open_thread()
                        agent.sessions[session.id] = session
                    except Exception:
                        logger.exception("Failed to reconstruct session from branch %s", branch)
                        continue

                if not agent.sessions:
                    agent.create_session(name=None)

                self._agents[agent.id] = agent
                logger.info(
                    "Hydrated agent %s with %d sessions from Gitea",
                    agent.id,
                    len(agent.sessions),
                )
        except Exception:
            logger.exception("Failed during Gitea store hydration")


_GLOBAL_STORE: HarnessStore | None = None


def get_harness_store() -> HarnessStore:
    """Return the singleton instance of HarnessStore."""
    global _GLOBAL_STORE
    if _GLOBAL_STORE is None:
        _GLOBAL_STORE = HarnessStore()
        _GLOBAL_STORE.hydrate_from_gitea()
    return _GLOBAL_STORE


def reset_harness_store(store: HarnessStore | None = None) -> HarnessStore:
    """Reset the global singleton store (useful in tests)."""
    global _GLOBAL_STORE
    _GLOBAL_STORE = store
    return get_harness_store()
