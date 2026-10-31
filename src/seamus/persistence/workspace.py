"""Git workspace manager orchestrating local clones and repositories."""

import json
import logging
import subprocess
import time
from pathlib import Path
from typing import Any
from uuid import UUID

from ag_ui.core.events import Event
from pydantic import TypeAdapter

from seamus.domain.entities import Agent, Session
from seamus.persistence.client import GiteaClient
from seamus.persistence.config import PersistenceSettings, get_persistence_settings

logger = logging.getLogger(__name__)

_EVENT_TYPE_ADAPTER: TypeAdapter[Event] | None = None


def get_event_type_adapter() -> TypeAdapter[Event]:
    """Return singleton TypeAdapter for AG-UI events."""
    global _EVENT_TYPE_ADAPTER
    if _EVENT_TYPE_ADAPTER is None:
        _EVENT_TYPE_ADAPTER = TypeAdapter(Event)
    return _EVENT_TYPE_ADAPTER


def parse_stored_event(data: Any) -> Any:
    """Deserialize stored JSON event dict into concrete AG-UI Event model."""
    if isinstance(data, dict):
        try:
            return get_event_type_adapter().validate_python(data)
        except Exception:
            return data
    return data


class GitWorkspaceError(RuntimeError):
    """Raised when a Git command or workspace operation fails."""


class GitWorkspaceManager:
    """Manages local git working copies and synchronizes them with Gitea."""

    def __init__(
        self,
        settings: PersistenceSettings | None = None,
        client: GiteaClient | None = None,
    ) -> None:
        self.settings = settings or get_persistence_settings()
        self.client = client or GiteaClient(self.settings)
        self.workspace_root = self.settings.workspace_dir
        self.workspace_root.mkdir(parents=True, exist_ok=True)

    def _run_git(self, cwd: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
        """Execute a git command within the specified working directory."""
        cmd = ["git", *args]
        try:
            return subprocess.run(
                cmd,
                cwd=cwd,
                check=True,
                text=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as exc:
            msg = (
                f"Git command failed: '{' '.join(cmd)}' in {cwd}\n"
                f"Exit code: {exc.returncode}\n"
                f"Stdout: {exc.stdout}\n"
                f"Stderr: {exc.stderr}"
            )
            logger.error(msg)
            raise GitWorkspaceError(msg) from exc

    def _configure_git_identity(self, repo_dir: Path) -> None:
        """Configure local repository author name and email."""
        self._run_git(repo_dir, ["config", "user.name", "Seamus Agent"])
        self._run_git(repo_dir, ["config", "user.email", "agent@seamus.local"])

    def get_agent_repo_name(self, agent_id: UUID) -> str:
        """Return standardized repository name for an agent."""
        return f"agent-{agent_id}"

    def get_agent_workspace_path(self, agent_id: UUID) -> Path:
        """Return path to the agent's base workspace directory."""
        return self.workspace_root / str(agent_id) / "_agent"

    def get_session_workspace_path(self, agent_id: UUID, session_id: UUID) -> Path:
        """Return path to the session's workspace directory."""
        return self.workspace_root / str(agent_id) / str(session_id)

    def get_session_data_dir(self, agent_id: UUID, session_id: UUID) -> Path:
        """Return path to the session's agent-accessible data/ directory."""
        return self.get_session_workspace_path(agent_id, session_id) / "data"

    def get_thread_state_dir(self, agent_id: UUID, session_id: UUID, thread_id: UUID) -> Path:
        """Return path to a specific thread's state directory within the session workspace."""
        return (
            self.get_session_workspace_path(agent_id, session_id)
            / "agent"
            / "state"
            / "threads"
            / str(thread_id)
        )

    def initialize_agent_repo(self, agent: Agent) -> Path:
        """Initialize remote repository and local clone on main branch."""
        if not self.settings.enabled:
            agent_dir = self.get_agent_workspace_path(agent.id)
            agent_dir.mkdir(parents=True, exist_ok=True)
            return agent_dir

        repo_name = self.get_agent_repo_name(agent.id)
        self.client.get_or_create_repo(
            repo_name=repo_name,
            description=f"Seamus repository for agent {agent.name or agent.id}",
        )

        agent_dir = self.get_agent_workspace_path(agent.id)
        clone_url = self.client.get_authenticated_clone_url(repo_name)

        if not (agent_dir / ".git").exists():
            agent_dir.mkdir(parents=True, exist_ok=True)
            self._run_git(agent_dir, ["init", "-b", "main"])
            self._configure_git_identity(agent_dir)
            self._run_git(agent_dir, ["remote", "add", "origin", clone_url])

            # Initialize repo structure: agent/config/, agent/state/, data/
            config_dir = agent_dir / "agent" / "config"
            state_dir = agent_dir / "agent" / "state"
            data_dir = agent_dir / "data"
            config_dir.mkdir(parents=True, exist_ok=True)
            state_dir.mkdir(parents=True, exist_ok=True)
            data_dir.mkdir(parents=True, exist_ok=True)

            state_gitkeep = state_dir / ".gitkeep"
            if not state_gitkeep.exists():
                state_gitkeep.touch()

            data_gitkeep = data_dir / ".gitkeep"
            if not data_gitkeep.exists():
                data_gitkeep.touch()

            # Write initial config
            config_payload = {
                "id": str(agent.id),
                "name": agent.name,
                "created_at": agent.created_at.isoformat(),
                "config": agent.config.model_dump(),
            }
            (config_dir / "config.json").write_text(
                json.dumps(config_payload, indent=2), encoding="utf-8"
            )

            self._run_git(agent_dir, ["add", "-A"])
            self._run_git(
                agent_dir,
                ["commit", "-m", f"config: initialize agent [agent={agent.id}]"],
            )
            self._run_git(agent_dir, ["push", "-u", "origin", "main"])
        else:
            self._configure_git_identity(agent_dir)

        return agent_dir

    def commit_agent_config(self, agent: Agent) -> None:
        """Commit and push updated agent configuration directory on main branch."""
        if not self.settings.enabled:
            return

        agent_dir = self.get_agent_workspace_path(agent.id)
        if not (agent_dir / ".git").exists():
            self.initialize_agent_repo(agent)

        config_dir = agent_dir / "agent" / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_payload = {
            "id": str(agent.id),
            "name": agent.name,
            "created_at": agent.created_at.isoformat(),
            "config": agent.config.model_dump(),
        }
        (config_dir / "config.json").write_text(
            json.dumps(config_payload, indent=2), encoding="utf-8"
        )

        status = self._run_git(agent_dir, ["status", "--porcelain", "agent/config/"])
        if status.stdout.strip():
            self._run_git(agent_dir, ["add", "-A", "agent/config/"])
            self._run_git(
                agent_dir,
                ["commit", "-m", f"config: update agent config [agent={agent.id}]"],
            )
            self._run_git(agent_dir, ["push", "origin", "main"])

    def create_session_workspace(self, session: Session, agent: Agent) -> Path:
        """Create or checkout session working tree on dedicated branch."""
        if not self.settings.enabled:
            session_dir = self.get_session_workspace_path(session.agent_id, session.id)
            (session_dir / "data").mkdir(parents=True, exist_ok=True)
            return session_dir

        # Ensure base agent repo exists first
        agent_dir = self.get_agent_workspace_path(agent.id)
        if not (agent_dir / ".git").exists():
            self.initialize_agent_repo(agent)

        repo_name = self.get_agent_repo_name(session.agent_id)
        clone_url = self.client.get_authenticated_clone_url(repo_name)
        session_dir = self.get_session_workspace_path(session.agent_id, session.id)
        branch_name = f"session/{session.id}"

        if not (session_dir / ".git").exists():
            session_dir.parent.mkdir(parents=True, exist_ok=True)
            self._run_git(session_dir.parent, ["clone", clone_url, session_dir.name])
            self._configure_git_identity(session_dir)

            # Check if remote branch exists
            remote_branches = self.client.list_branches(repo_name)
            if branch_name in remote_branches:
                self._run_git(session_dir, ["checkout", branch_name])
            else:
                self._run_git(session_dir, ["checkout", "-b", branch_name])
        else:
            self._configure_git_identity(session_dir)

        # Write session config
        self.commit_session_config(session)
        (session_dir / "data").mkdir(exist_ok=True)
        (session_dir / "agent" / "state").mkdir(parents=True, exist_ok=True)
        return session_dir

    def commit_session_config(self, session: Session) -> None:
        """Serialize and commit session configuration directory to session branch."""
        if not self.settings.enabled:
            return

        session_dir = self.get_session_workspace_path(session.agent_id, session.id)
        if not (session_dir / ".git").exists():
            return

        config_dir = session_dir / "agent" / "config"
        config_dir.mkdir(parents=True, exist_ok=True)

        config_payload = {
            "id": str(session.id),
            "agent_id": str(session.agent_id),
            "name": session.name,
            "created_at": session.created_at.isoformat(),
            "config": session.config.model_dump(),
            "threads": [
                {
                    "id": str(t.id),
                    "name": t.name,
                    "created_at": t.created_at.isoformat(),
                    "is_open": t.is_open,
                    "status": t.status.value,
                }
                for t in sorted(session.threads.values(), key=lambda t: t.created_at)
            ],
        }
        (config_dir / "config.json").write_text(
            json.dumps(config_payload, indent=2), encoding="utf-8"
        )

        status = self._run_git(session_dir, ["status", "--porcelain", "agent/config/"])
        if status.stdout.strip():
            branch_name = f"session/{session.id}"
            self._run_git(session_dir, ["add", "-A", "agent/config/"])
            self._run_git(
                session_dir,
                ["commit", "-m", f"config: update session config [session={session.id}]"],
            )
            self._run_git(session_dir, ["push", "-u", "origin", branch_name])

    def get_active_sync_pr(self, session: Session, agent: Agent) -> dict[str, Any] | None:
        """Find the active open Sync PR from session branch to main."""
        if not self.settings.enabled:
            return None

        repo_name = self.get_agent_repo_name(session.agent_id)
        head_branch = f"session/{session.id}"
        try:
            open_prs = self.client.list_pull_requests(repo_name, state="open")
            for pr in open_prs:
                head_ref = pr.get("head", {}).get("ref")
                if head_ref == head_branch:
                    return pr
            return None
        except Exception:
            logger.exception("Failed to query active Sync PR for session %s", session.id)
            return None

    def open_sync_pr(self, session: Session, agent: Agent) -> dict[str, Any] | None:
        """Open an automated Sync PR from session branch to main if not already present."""
        if not self.settings.enabled:
            return None

        active_pr = self.get_active_sync_pr(session, agent)
        if active_pr is not None:
            return active_pr

        repo_name = self.get_agent_repo_name(session.agent_id)
        head_branch = f"session/{session.id}"
        base_branch = "main"
        title = f"Sync PR: session/{session.name or session.id}"
        body = f"Automated Sync PR for session `{session.id}` (agent `{agent.name or agent.id}`)."
        try:
            pr = self.client.create_pull_request(
                repo_name=repo_name,
                title=title,
                head=head_branch,
                base=base_branch,
                body=body,
            )
            logger.info("Opened Sync PR #%s for session %s", pr.get("number"), session.id)
            return pr
        except Exception:
            logger.exception("Failed to open Sync PR for session %s", session.id)
            return None

    def merge_sync_pr(self, session: Session, agent: Agent) -> bool:
        """Approve and merge the active Sync PR from session branch into main."""
        if not self.settings.enabled:
            return True

        active_pr = self.get_active_sync_pr(session, agent)
        if active_pr is None:
            logger.warning("No active Sync PR found for session %s to merge", session.id)
            return False

        pr_number = active_pr["number"]
        repo_name = self.get_agent_repo_name(session.agent_id)

        # 1. Attempt approval review (log and continue if self-approval rejected)
        try:
            self.client.approve_pull_request(
                repo_name=repo_name,
                index=pr_number,
                body="Accepted by user",
            )
        except Exception:
            logger.warning("Approval review failed on PR #%d (proceeding with merge)", pr_number)

        # 2. Wait briefly for Gitea to evaluate mergeability
        for _ in range(10):
            time.sleep(0.3)
            try:
                pr_data = self.client.get_pull_request(repo_name, pr_number)
                if pr_data.get("mergeable") is True:
                    break
            except Exception:
                break

        # 3. Merge pull request (delete_branch=False retains the session branch)
        try:
            return self.client.merge_pull_request(
                repo_name=repo_name,
                index=pr_number,
                do="merge",
                delete_branch=False,
            )
        except Exception:
            logger.exception("Failed to merge Sync PR #%d for session %s", pr_number, session.id)
            return False

    def save_thread_events(
        self,
        agent_id: UUID,
        session_id: UUID,
        thread_id: UUID,
        events: list[Any],
    ) -> Path:
        """Serialize and save thread AG-UI events to agent/state/threads/{thread_id}/events.json."""
        thread_dir = self.get_thread_state_dir(agent_id, session_id, thread_id)
        thread_dir.mkdir(parents=True, exist_ok=True)
        events_file = thread_dir / "events.json"

        serialized: list[Any] = []
        for ev in events:
            if hasattr(ev, "model_dump"):
                serialized.append(ev.model_dump(mode="json", by_alias=True))
            elif isinstance(ev, dict):
                serialized.append(ev)
            else:
                serialized.append({"type": "RAW", "data": str(ev)})

        events_file.write_text(json.dumps(serialized, indent=2), encoding="utf-8")
        return events_file

    def load_thread_events(
        self,
        agent_id: UUID,
        session_id: UUID,
        thread_id: UUID,
    ) -> list[Any]:
        """Load and deserialize thread AG-UI events from the thread state directory."""
        events_file = self.get_thread_state_dir(agent_id, session_id, thread_id) / "events.json"
        if not events_file.exists():
            return []

        try:
            content = events_file.read_text(encoding="utf-8")
            data = json.loads(content)
            if not isinstance(data, list):
                return []
            return [parse_stored_event(item) for item in data]
        except Exception:
            logger.exception("Failed to load thread events from %s", events_file)
            return []

    def save_thread_checkpoints(
        self,
        agent_id: UUID,
        session_id: UUID,
        thread_id: UUID,
        checkpoint_data: dict[str, Any],
    ) -> Path:
        """Save serialized LangGraph checkpoint data to the thread state directory."""
        thread_dir = self.get_thread_state_dir(agent_id, session_id, thread_id)
        thread_dir.mkdir(parents=True, exist_ok=True)
        cp_file = thread_dir / "checkpoints.json"
        cp_file.write_text(json.dumps(checkpoint_data, indent=2), encoding="utf-8")
        return cp_file

    def load_thread_checkpoints(
        self,
        agent_id: UUID,
        session_id: UUID,
        thread_id: UUID,
    ) -> dict[str, Any] | None:
        """Load serialized LangGraph checkpoint data from the thread state directory."""
        cp_file = self.get_thread_state_dir(agent_id, session_id, thread_id) / "checkpoints.json"
        if not cp_file.exists():
            return None
        try:
            content = cp_file.read_text(encoding="utf-8")
            return json.loads(content)  # type: ignore[no-any-return]
        except Exception:
            logger.exception("Failed to load thread checkpoints from %s", cp_file)
            return None

    def load_all_thread_checkpoints(
        self,
        agent_id: UUID,
        session_id: UUID,
    ) -> list[dict[str, Any]]:
        """Load all checkpoints across all threads in a session workspace."""
        threads_dir = (
            self.get_session_workspace_path(agent_id, session_id) / "agent" / "state" / "threads"
        )
        if not threads_dir.exists():
            return []
        results: list[dict[str, Any]] = []
        for child in threads_dir.iterdir():
            if child.is_dir():
                cp_file = child / "checkpoints.json"
                if cp_file.exists():
                    try:
                        content = cp_file.read_text(encoding="utf-8")
                        results.append(json.loads(content))
                    except Exception:
                        logger.exception("Failed to read checkpoints from %s", cp_file)
        return results

    def save_thread_messages(
        self,
        agent_id: UUID,
        session_id: UUID,
        thread_id: UUID,
        messages: list[dict[str, Any]],
    ) -> Path:
        """Save human-readable conversation messages to the thread state directory."""
        thread_dir = self.get_thread_state_dir(agent_id, session_id, thread_id)
        thread_dir.mkdir(parents=True, exist_ok=True)
        msgs_file = thread_dir / "messages.json"
        msgs_file.write_text(json.dumps(messages, indent=2), encoding="utf-8")
        return msgs_file

    def load_thread_messages(
        self,
        agent_id: UUID,
        session_id: UUID,
        thread_id: UUID,
    ) -> list[dict[str, Any]]:
        """Load human-readable conversation messages from the thread state directory."""
        msgs_file = self.get_thread_state_dir(agent_id, session_id, thread_id) / "messages.json"
        if not msgs_file.exists():
            return []
        try:
            content = msgs_file.read_text(encoding="utf-8")
            data = json.loads(content)
            return data if isinstance(data, list) else []
        except Exception:
            logger.exception("Failed to load thread messages from %s", msgs_file)
            return []

    def get_session_git_info(
        self,
        agent_id: UUID,
        session_id: UUID,
    ) -> dict[str, str | None]:
        """Return git commit SHA, message, and timestamp for the session branch."""
        session_dir = self.get_session_workspace_path(agent_id, session_id)
        if not (session_dir / ".git").exists():
            return {
                "commit_sha": None,
                "commit_message": None,
                "commit_time": None,
            }
        try:
            sha = self._run_git(session_dir, ["rev-parse", "HEAD"]).stdout.strip()
            msg = self._run_git(session_dir, ["log", "-1", "--format=%s"]).stdout.strip()
            ts = self._run_git(session_dir, ["log", "-1", "--format=%cI"]).stdout.strip()
            return {
                "commit_sha": sha or None,
                "commit_message": msg or None,
                "commit_time": ts or None,
            }
        except Exception:
            return {
                "commit_sha": None,
                "commit_message": None,
                "commit_time": None,
            }

    def commit_checkpoint_changes(
        self,
        agent_id: UUID,
        session_id: UUID,
        thread_id: UUID,
        checkpoint_id: str | None = None,
    ) -> bool:
        """Commit all modified or untracked files in data/ and agent/state/ to session branch."""
        if not self.settings.enabled:
            return False

        session_dir = self.get_session_workspace_path(agent_id, session_id)
        if not (session_dir / ".git").exists():
            return False

        paths_to_check = [p for p in ["data", "agent/state"] if (session_dir / p).exists()]
        if not paths_to_check:
            return False

        status = self._run_git(session_dir, ["status", "--porcelain", "--", *paths_to_check])
        if not status.stdout.strip():
            return False

        branch_name = f"session/{session_id}"
        cp_ident = checkpoint_id or "none"
        commit_msg = f"checkpoint: [session={session_id} thread={thread_id} checkpoint={cp_ident}]"

        self._run_git(session_dir, ["add", "-A", "--", *paths_to_check])
        self._run_git(session_dir, ["commit", "-m", commit_msg])
        self._run_git(session_dir, ["push", "origin", branch_name])
        logger.info(
            "Committed checkpoint changes for session %s thread %s (checkpoint %s)",
            session_id,
            thread_id,
            cp_ident,
        )
        return True

    def commit_data_changes(
        self,
        agent_id: UUID,
        session_id: UUID,
        thread_id: UUID,
        checkpoint_id: str | None = None,
    ) -> bool:
        """Backward-compatible alias for commit_checkpoint_changes."""
        return self.commit_checkpoint_changes(
            agent_id=agent_id,
            session_id=session_id,
            thread_id=thread_id,
            checkpoint_id=checkpoint_id,
        )

    def commit_state_changes(
        self,
        agent_id: UUID,
        session_id: UUID,
        thread_id: UUID,
    ) -> bool:
        """Commit thread events and state updates in agent/state/ to session branch."""
        if not self.settings.enabled:
            return False

        session_dir = self.get_session_workspace_path(agent_id, session_id)
        if not (session_dir / ".git").exists():
            return False

        if not (session_dir / "agent" / "state").exists():
            return False

        status = self._run_git(session_dir, ["status", "--porcelain", "--", "agent/state"])
        if not status.stdout.strip():
            return False

        branch_name = f"session/{session_id}"
        commit_msg = f"state: update thread events [session={session_id} thread={thread_id}]"

        self._run_git(session_dir, ["add", "-A", "--", "agent/state"])
        self._run_git(session_dir, ["commit", "-m", commit_msg])
        self._run_git(session_dir, ["push", "origin", branch_name])
        logger.info(
            "Committed state changes for session %s thread %s",
            session_id,
            thread_id,
        )
        return True


_GLOBAL_WORKSPACE_MANAGER: GitWorkspaceManager | None = None


def get_workspace_manager() -> GitWorkspaceManager:
    """Return the global singleton GitWorkspaceManager instance."""
    global _GLOBAL_WORKSPACE_MANAGER
    if _GLOBAL_WORKSPACE_MANAGER is None:
        _GLOBAL_WORKSPACE_MANAGER = GitWorkspaceManager()
    return _GLOBAL_WORKSPACE_MANAGER
