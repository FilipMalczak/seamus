"""In-memory repository store for agents, sessions, and threads with Gitea Git persistence."""

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import logfire

from seamus.config.models import AgentConfig
from seamus.domain.entities import (
    Agent,
    AgentStatus,
    Session,
    SessionBranchProvenance,
    SessionStatus,
    Thread,
)
from seamus.domain.modes import normalize_mode_and_phase
from seamus.domain.repositories import MountedRepositoryCheckpointRecord
from seamus.domain.resolution import (
    EntityNotFoundError,
    parse_uuid,
    resolve_session,
    resolve_thread,
)
from seamus.harness.artifacts import ArtifactResolver, PlanBuilder
from seamus.persistence import (
    calculate_mount_paths,
    get_external_repo_manager,
    get_workspace_manager,
    parse_stored_event,
)

logger = logging.getLogger(__name__)


@dataclass
class _AssistantTurn:
    turn_index: int
    slice_index: int
    associated_ids: set[str]
    rep_id: str
    event_indices: list[int]
    timestamp_ms: float | None = None
    tool_result_slice_index: int | None = None
    tool_ids: set[str] = field(default_factory=set)


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
        import coolname

        config.validate_complete()
        self._ensure_agent_slug_unique(name, current_agent_id=None)

        agent = Agent(name=name, config=config)
        occupied = {a.name for a in self._agents.values() if a.name}
        while agent.generated_name in occupied:
            agent.generated_name = coolname.generate_slug()

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
        if name is not None:
            self._ensure_agent_slug_unique(name, current_agent_id=agent.id)
        else:
            import coolname

            occupied = {a.name for a in self._agents.values() if a.id != agent.id and a.name}
            while agent.generated_name in occupied:
                agent.generated_name = coolname.generate_slug()

        agent_ident = name or agent.generated_name or str(agent.id)
        with logfire.span(
            f"agent {agent_ident}",
            agent_id=str(agent.id),
            agent_name=name or agent.generated_name,
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

    def kill_session(
        self,
        agent_identifier: str,
        session_identifier: str,
    ) -> Session:
        """Manually terminate a session, preventing future turns and closing Sync PR."""
        agent = self.resolve_agent(agent_identifier)
        session = resolve_session(agent, session_identifier)

        from seamus.harness.runner import get_runner_registry

        registry = get_runner_registry()
        runner = registry._runners.get(str(session.id))
        if runner is not None:
            runner.kill()
        else:
            session.kill()

        try:
            ws_mgr = get_workspace_manager()
            ws_mgr.commit_session_config(session)
            ws_mgr.close_sync_pr(session, agent)
        except Exception:
            logger.exception("Failed to update workspace on killing session %s", session.id)

        return session

    @staticmethod
    def _find_assistant_turn(
        thread: Thread, message_id: str, retry_inference: bool = False
    ) -> tuple[int, str] | None:
        """Locate the target assistant turn and its slice index in a thread's events.

        Matches by exact event/tool/message ID, turn index (e.g. 'asst-0'), or client-generated
        timestamp identifier (e.g. 'asst-1793565453328').
        Returns (slice_index, representative_id) or None if not found.
        """
        turns: list[_AssistantTurn] = []
        current_turn_events: list[tuple[int, Any]] = []
        user_ids: set[str] = set()
        in_assistant_turn = False

        def finish_current_turn() -> None:
            nonlocal in_assistant_turn, current_turn_events
            if not current_turn_events:
                in_assistant_turn = False
                return

            last_idx = current_turn_events[-1][0]
            slice_idx = last_idx + 1

            turn_ids: set[str] = set()
            turn_tool_ids: set[str] = set()
            turn_indices: list[int] = []
            rep_id: str | None = None
            turn_ts: float | None = None
            last_tool_res_idx: int | None = None

            for ev_idx, ev in current_turn_events:
                turn_indices.append(ev_idx)
                ev_type = getattr(ev, "type", None) or (
                    ev.get("type") if isinstance(ev, dict) else None
                )
                if ev_type in ("TOOL_CALL_RESULT", "tool_call_result"):
                    last_tool_res_idx = ev_idx

                mid = getattr(ev, "message_id", None) or (
                    ev.get("message_id") if isinstance(ev, dict) else None
                )
                if mid:
                    turn_ids.add(str(mid))
                    if rep_id is None:
                        rep_id = str(mid)

                tcid = getattr(ev, "tool_call_id", None) or (
                    ev.get("tool_call_id") if isinstance(ev, dict) else None
                )
                if tcid:
                    turn_ids.add(str(tcid))
                    turn_tool_ids.add(str(tcid))
                    if rep_id is None:
                        rep_id = str(tcid)

                pmid = getattr(ev, "parent_message_id", None) or (
                    ev.get("parent_message_id") if isinstance(ev, dict) else None
                )
                if pmid:
                    turn_ids.add(str(pmid))

                eid = getattr(ev, "id", None) or (ev.get("id") if isinstance(ev, dict) else None)
                if eid:
                    turn_ids.add(str(eid))

                ts = getattr(ev, "timestamp", None) or (
                    ev.get("timestamp") if isinstance(ev, dict) else None
                )
                if ts and turn_ts is None:
                    try:
                        if isinstance(ts, (int, float)):
                            turn_ts = float(ts) * (1000 if ts < 1e11 else 1)
                        elif isinstance(ts, str):
                            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                            turn_ts = dt.timestamp() * 1000
                    except Exception:
                        pass

            if rep_id is None:
                rep_id = f"asst-turn-{len(turns)}"

            tool_slice = (last_tool_res_idx + 1) if last_tool_res_idx is not None else None

            turns.append(
                _AssistantTurn(
                    turn_index=len(turns),
                    slice_index=slice_idx,
                    associated_ids=turn_ids,
                    rep_id=rep_id,
                    event_indices=turn_indices,
                    timestamp_ms=turn_ts,
                    tool_result_slice_index=tool_slice,
                    tool_ids=turn_tool_ids,
                )
            )
            current_turn_events = []
            in_assistant_turn = False

        current_role: str | None = None
        for idx, ev in enumerate(thread.events):
            role = getattr(ev, "role", None) or (ev.get("role") if isinstance(ev, dict) else None)
            ev_type = getattr(ev, "type", None) or (
                ev.get("type") if isinstance(ev, dict) else None
            )

            if ev_type in ("RUN_STARTED", "run_started"):
                if in_assistant_turn:
                    finish_current_turn()
                current_role = "assistant"
                in_assistant_turn = True
                current_turn_events.append((idx, ev))
                continue

            if ev_type in ("RUN_FINISHED", "run_finished"):
                if in_assistant_turn:
                    current_turn_events.append((idx, ev))
                    finish_current_turn()
                current_role = None
                continue

            if role:
                current_role = role

            if ev_type in ("USER_INPUT", "user_input"):
                current_role = "user"

            if current_role == "user":
                u_mid = getattr(ev, "message_id", None) or (
                    ev.get("message_id") if isinstance(ev, dict) else None
                )
                if u_mid:
                    user_ids.add(str(u_mid))
                u_id = getattr(ev, "id", None) or (ev.get("id") if isinstance(ev, dict) else None)
                if u_id:
                    user_ids.add(str(u_id))
                if in_assistant_turn:
                    finish_current_turn()
                continue

            in_assistant_turn = True
            current_turn_events.append((idx, ev))

        if in_assistant_turn:
            finish_current_turn()

        # Reject if message belongs to a user event
        if message_id in user_ids:
            return None

        if not turns:
            return None

        def get_turn_result(turn: _AssistantTurn) -> tuple[int, str]:
            if retry_inference:
                if turn.tool_result_slice_index is not None:
                    return turn.tool_result_slice_index, turn.rep_id
                msg = (
                    f"Assistant turn '{message_id}' does not contain completed "
                    "tool calls to branch after."
                )
                raise ValueError(msg)
            return turn.slice_index, turn.rep_id

        # 1. Exact match in associated_ids
        for turn in turns:
            if message_id in turn.associated_ids:
                return get_turn_result(turn)

        # 2. Check asst-<turn_index> e.g. "asst-0", "asst-1"
        if message_id.startswith("asst-"):
            suffix = message_id[5:]
            if suffix.isdigit():
                idx = int(suffix)
                if 0 <= idx < len(turns):
                    return get_turn_result(turns[idx])

        # 3. Handle asst-<timestamp_ms> (e.g. from frontend Date.now())
        if message_id.startswith("asst-"):
            suffix = message_id[5:]
            try:
                ts_val = float(suffix)
                if len(turns) == 1:
                    return get_turn_result(turns[0])

                closest_turn = None
                min_diff = float("inf")
                for turn in turns:
                    if turn.timestamp_ms is not None:
                        diff = abs(turn.timestamp_ms - ts_val)
                        if diff < min_diff:
                            min_diff = diff
                            closest_turn = turn
                if closest_turn is not None:
                    return get_turn_result(closest_turn)

                return get_turn_result(turns[-1])
            except ValueError:
                pass

        # 4. Fallback: check if message_id is a substring in events of that assistant turn
        for turn in turns:
            for idx in turn.event_indices:
                ev = thread.events[idx]
                if message_id in str(ev):
                    return get_turn_result(turn)

        return None

    def branch_session(
        self,
        agent_identifier: str,
        session_identifier: str,
        message_id: str,
        name: str | None = None,
        retry_inference: bool = False,
    ) -> Session:
        """Branch off an assistant message in a session to create a new session."""
        agent = self.resolve_agent(agent_identifier)
        parent_session = resolve_session(agent, session_identifier)
        self._ensure_session_slug_unique(agent, name, current_session_id=None)

        # Locate target message and thread
        target_thread: Thread | None = None
        target_event_index: int = -1
        target_rep_id: str | None = None

        for thread in parent_session.threads.values():
            match_res = self._find_assistant_turn(
                thread, message_id, retry_inference=retry_inference
            )
            if match_res is not None:
                target_thread = thread
                target_event_index, target_rep_id = match_res
                break

        if target_thread is None or target_rep_id is None:
            msg = f"Assistant message '{message_id}' not found in session '{parent_session.id}'."
            raise ValueError(msg)

        provenance_id = (
            target_rep_id
            if (message_id.startswith("asst-") and message_id not in target_rep_id)
            else message_id
        )

        provenance = SessionBranchProvenance(
            parent_session_id=parent_session.id,
            parent_message_id=provenance_id,
            parent_session_name=parent_session.name,
        )

        # Sliced events for new session
        sliced_events = list(target_thread.events[:target_event_index])
        sliced_event_ids: set[str] = set()
        for ev in sliced_events:
            for attr in ("message_id", "tool_call_id", "parent_message_id", "id"):
                val = getattr(ev, attr, None) or (ev.get(attr) if isinstance(ev, dict) else None)
                if val:
                    sliced_event_ids.add(str(val))

        inherited_lineage: list[SessionBranchProvenance] = []
        candidates = (
            parent_session.lineage
            if parent_session.lineage
            else ([parent_session.provenance] if parent_session.provenance else [])
        )
        for entry in candidates:
            if entry.parent_message_id in sliced_event_ids:
                inherited_lineage.append(entry)

        inherited_lineage.append(provenance)

        agent_ident = agent.name or str(agent.id)
        with logfire.span(
            f"agent {agent_ident}",
            agent_id=str(agent.id),
            agent_name=agent.name,
            agent_identifier=agent_ident,
        ):
            new_session = Session(
                agent_id=agent.id,
                custom_name=name,
                config=parent_session.config.model_copy(deep=True),
                status=SessionStatus.ACTIVE,
                provenance=provenance,
                lineage=inherited_lineage,
            )
            new_thread = Thread(
                custom_name=None,
                is_open=True,
                status=AgentStatus.AWAITING_LLM if retry_inference else AgentStatus.AWAITING_USER,
                events=sliced_events,
            )
            new_session.threads[new_thread.id] = new_thread
            agent.sessions[new_session.id] = new_session
            agent.touch()

            session_ident = new_session.name or str(new_session.id)
            with logfire.span(
                f"session {session_ident}",
                session_id=str(new_session.id),
                session_name=new_session.name,
                session_identifier=session_ident,
                parent_session_id=str(parent_session.id),
                operation="branch",
            ):
                try:
                    ws_mgr = get_workspace_manager()
                    branch_commit = ws_mgr.find_commit_for_event(
                        agent.id, parent_session.id, provenance_id
                    )
                    if not branch_commit and target_rep_id != provenance_id:
                        branch_commit = ws_mgr.find_commit_for_event(
                            agent.id, parent_session.id, target_rep_id
                        )
                    branch_from = branch_commit or f"origin/session/{parent_session.id}"
                    ws_mgr.create_session_workspace(new_session, agent, branch_from=branch_from)
                    ws_mgr.save_thread_events(
                        agent.id, new_session.id, new_thread.id, new_thread.events
                    )
                    ws_mgr.open_sync_pr(new_session, agent)

                    # Restore or provision mounted external repositories for the branched session
                    if new_session.config.repositories:
                        ext_mgr = get_external_repo_manager()
                        ext_cp = ws_mgr.load_thread_external_checkpoints(
                            agent.id, new_session.id, target_thread.id
                        )
                        mount_paths = calculate_mount_paths(new_session.config.repositories)
                        for repo_cfg in new_session.config.repositories:
                            mount_name = mount_paths.get(repo_cfg.id, "repo")
                            rec_data = (
                                ext_cp.get("repositories", {}).get(repo_cfg.id) if ext_cp else None
                            )
                            if rec_data:
                                record = MountedRepositoryCheckpointRecord.model_validate(rec_data)
                                ext_mgr.restore_working_copy_checkpoint(
                                    agent.id, new_session.id, record
                                )
                            else:
                                ext_mgr.provision_session_working_copy(
                                    agent.id, new_session.id, repo_cfg, mount_name
                                )
                except Exception:
                    logger.exception(
                        "Failed to initialize git workspace for branched session %s",
                        new_session.id,
                    )

                if retry_inference:
                    import asyncio

                    from seamus.harness.runner import get_runner_registry

                    registry = get_runner_registry()
                    parent_runner = registry._runners.get(str(parent_session.id))
                    runner = registry.get_runner(new_session, agent=agent)

                    if runner.checkpointer is not None:
                        if parent_runner and parent_runner.checkpointer is not None:
                            for k_s, v_s in parent_runner.checkpointer.storage.items():
                                if k_s not in runner.checkpointer.storage:
                                    runner.checkpointer.storage[k_s] = v_s
                            for k_w, v_w in parent_runner.checkpointer.writes.items():
                                if k_w not in runner.checkpointer.writes:
                                    runner.checkpointer.writes[k_w] = v_w
                            for k_b, v_b in parent_runner.checkpointer.blobs.items():
                                if k_b not in runner.checkpointer.blobs:
                                    runner.checkpointer.blobs[k_b] = v_b

                        runner.checkpointer.copy_thread(str(target_thread.id), str(new_thread.id))

                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(runner.resume_turn(new_thread))
                    except RuntimeError:
                        pass

                return new_session

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
            ws_mgr = get_workspace_manager()

            # 1. Close active plan if present (e.g. when accepting Sync PR in Plan/Execute)
            if session.active_plan_id:
                try:
                    artifacts_dir = ws_mgr.get_session_artifacts_dir(agent.id, session.id)
                    PlanBuilder.close_plan(artifacts_dir, session.active_plan_id)
                    closed_plan_id = session.active_plan_id
                    session.active_plan_id = None
                    from seamus.harness.runner import get_runner_registry

                    runner = get_runner_registry()._runners.get(str(session.id))
                    if runner is not None:
                        runner.broadcaster.broadcast_sync(
                            {
                                "type": "ARTIFACT_CLOSED",
                                "artifact_id": closed_plan_id,
                                "kind": "plans",
                            }
                        )
                    ws_mgr.commit_checkpoint_changes(agent.id, session.id, thread.id)
                except Exception:
                    logger.exception(
                        "Failed to close active plan upon Sync PR accept for session %s",
                        session.id,
                    )

            # 2. Close current thread
            thread.is_open = False
            thread.touch()
            session.touch()
            agent.touch()

            # 3. Commit closed thread state to session branch
            try:
                ws_mgr.commit_session_config(session)
            except Exception:
                logger.exception(
                    "Failed to commit session config upon thread close for %s", session.id
                )

            # 4. Approve and merge active Sync PR into main
            try:
                ws_mgr.merge_sync_pr(session, agent)
            except Exception:
                logger.exception("Failed to merge Sync PR for session %s", session.id)

            # 5. Open a new thread on the same session branch (Plan mode resets to Discuss)
            new_thread = session.create_thread(mode=thread.mode, phase=None)
            session.touch()
            agent.touch()

            try:
                from seamus.harness.runner import get_runner_registry

                runner = get_runner_registry()._runners.get(str(session.id))
                if runner is not None:
                    runner.sync_sandbox_mounts(new_thread)
                    runner.broadcaster.broadcast_sync(
                        {
                            "type": "THREAD_TRANSITION",
                            "thread_id": str(new_thread.id),
                            "mode": new_thread.mode,
                            "phase": new_thread.phase,
                            "mode_label": new_thread.mode_label,
                            "active_plan_id": session.active_plan_id,
                            "auto_wake": False,
                        }
                    )
            except Exception:
                logger.exception("Failed to sync runner mounts after accept_thread")

            # 6. Commit session config with the new thread and open a renewed Sync PR
            try:
                ws_mgr.commit_session_config(session)
            except Exception:
                logger.exception("Failed to commit session config for new thread in %s", session.id)

            try:
                ws_mgr.open_sync_pr(session, agent)
            except Exception:
                logger.exception("Failed to open renewed Sync PR for session %s", session.id)

            return new_thread

    def switch_session_mode(
        self,
        agent_identifier: str,
        session_identifier: str,
        mode: str,
    ) -> Session:
        """Switch the operational mode of a session by spawning a new thread in the target mode."""
        agent = self.resolve_agent(agent_identifier)
        session = resolve_session(agent, session_identifier)
        if not session.is_active:
            raise ValueError(
                f"Cannot switch mode on inactive session '{session.id}' "
                f"(status: {session.status.value})."
            )

        target_mode, target_phase = normalize_mode_and_phase(mode, None)
        ws_mgr = get_workspace_manager()
        artifacts_dir = ws_mgr.get_session_artifacts_dir(agent.id, session.id)

        from seamus.harness.runner import get_runner_registry

        runner = get_runner_registry()._runners.get(str(session.id))
        old_thread = session.get_open_thread()

        # Close active plan if one is open when switching modes
        if session.active_plan_id:
            closed_plan_id = session.active_plan_id
            PlanBuilder.close_plan(artifacts_dir, closed_plan_id)
            session.active_plan_id = None
            if runner is not None:
                runner.broadcaster.broadcast_sync(
                    {
                        "type": "ARTIFACT_CLOSED",
                        "artifact_id": closed_plan_id,
                        "kind": "plans",
                    }
                )

        # Close any open questionnaires or forms so the new mode thread starts unblocked
        if artifacts_dir.is_dir():
            resolver = ArtifactResolver(artifacts_dir)
            for art in resolver.list_artifacts():
                if not art.is_closed:
                    del_file = artifacts_dir / art.kind / art.name / "closed.json"
                    del_file.write_text(
                        json.dumps({"closed": True}, indent=2),
                        encoding="utf-8",
                    )
                    if runner is not None:
                        runner.broadcaster.broadcast_sync(
                            {
                                "type": "ARTIFACT_CLOSED",
                                "artifact_id": art.name,
                                "kind": art.kind,
                            }
                        )

        session.config.mode = target_mode
        new_thread = session.create_thread(mode=target_mode, phase=target_phase)
        session.touch()
        agent.touch()

        if runner is not None:
            runner.sync_sandbox_mounts(new_thread)
            runner.broadcaster.broadcast_sync(
                {
                    "type": "THREAD_TRANSITION",
                    "from_thread_id": str(old_thread.id),
                    "to_thread_id": str(new_thread.id),
                    "thread_id": str(new_thread.id),
                    "mode": new_thread.mode,
                    "phase": new_thread.phase,
                    "mode_label": new_thread.mode_label,
                    "active_plan_id": session.active_plan_id,
                    "auto_wake": False,
                }
            )

        try:
            ws_mgr.commit_checkpoint_changes(agent.id, session.id, old_thread.id)
            ws_mgr.commit_session_config(session)
        except Exception:
            logger.exception("Failed to commit session mode switch for %s", session.id)

        return session

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
                    from seamus.vault.interpolator import strip_secret_versions

                    agent_payload = json.loads(main_raw)
                    agent_config = AgentConfig.model_validate(
                        strip_secret_versions(agent_payload.get("config", {}))
                    )
                    created_at_str = agent_payload.get("created_at")
                    agent_created_at = (
                        datetime.fromisoformat(created_at_str)
                        if created_at_str
                        else datetime.now(UTC)
                    )
                    agent = Agent(
                        id=agent_id,
                        custom_name=agent_payload.get("custom_name") or agent_payload.get("name"),
                        generated_name=agent_payload.get("generated_name"),
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
                        persisted_config = session_payload.get("config", {})
                        from seamus.vault.parser import find_secret_references

                        loaded_secret_versions: dict[str, int] = {}
                        for _, ref in find_secret_references(
                            json.dumps(persisted_config), allow_version=True
                        ):
                            if ref.version is not None:
                                loaded_secret_versions[f"{ref.normalized_path}:{ref.field}"] = (
                                    ref.version
                                )
                        session_config = AgentConfig.model_validate(
                            strip_secret_versions(persisted_config)
                        )
                        session_created_at_str = session_payload.get("created_at")
                        session_created_at = (
                            datetime.fromisoformat(session_created_at_str)
                            if session_created_at_str
                            else datetime.now(UTC)
                        )
                        status_val = session_payload.get("status", "ACTIVE")
                        session_status = (
                            SessionStatus(status_val)
                            if status_val in SessionStatus.__members__
                            else SessionStatus.ACTIVE
                        )
                        provenance_data = session_payload.get("provenance")
                        provenance = (
                            SessionBranchProvenance.model_validate(provenance_data)
                            if provenance_data
                            else None
                        )
                        lineage_data = session_payload.get("lineage")
                        lineage = (
                            [
                                SessionBranchProvenance.model_validate(entry)
                                for entry in lineage_data
                            ]
                            if isinstance(lineage_data, list)
                            else ([provenance] if provenance else [])
                        )
                        session = Session(
                            id=session_id,
                            agent_id=agent.id,
                            custom_name=(
                                session_payload.get("custom_name") or session_payload.get("name")
                            ),
                            daemon_name=session_payload.get("daemon_name"),
                            config=session_config,
                            status=session_status,
                            active_plan_id=session_payload.get("active_plan_id"),
                            secret_versions=loaded_secret_versions,
                            provenance=provenance,
                            lineage=lineage,
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
                                t_mode, t_phase = normalize_mode_and_phase(
                                    t_data.get("mode"),
                                    t_data.get("phase"),
                                )
                                thread = Thread(
                                    id=t_id,
                                    custom_name=t_data.get("custom_name") or t_data.get("name"),
                                    daemon_name=t_data.get("daemon_name"),
                                    exchange_count=int(t_data.get("exchange_count", 0)),
                                    is_open=bool(t_data.get("is_open", False)),
                                    status=status_enum,
                                    mode=t_mode,
                                    phase=t_phase,
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
