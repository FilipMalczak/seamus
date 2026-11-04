"""Git workspace manager orchestrating local clones and repositories."""

import json
import logging
import re
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


def filter_sync_pr_diff(raw_diff: str) -> str:
    """Filter reviewable PR diff so that only files under data/ and artifacts/ are kept."""
    if not raw_diff:
        return ""
    pattern = re.compile(r"(?=^diff --git )", re.MULTILINE)
    chunks = pattern.split(raw_diff)
    kept: list[str] = []
    for chunk in chunks:
        if not chunk.strip():
            continue
        first_line = chunk.split("\n", 1)[0]
        # Restrict to deliverables under data/ and renderable artifacts under artifacts/
        if (
            " a/data/" in first_line
            or " b/data/" in first_line
            or " a/artifacts/" in first_line
            or " b/artifacts/" in first_line
        ):
            kept.append(chunk)
    return "".join(kept)


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

    def get_system_repo_name(self) -> str:
        """Return standardized repository name for system settings and templates."""
        return "system"

    def get_system_workspace_path(self) -> Path:
        """Return path to the local system repository clone."""
        return self.workspace_root / "_system"

    def get_agent_workspace_path(self, agent_id: UUID) -> Path:
        """Return path to the agent's base workspace directory."""
        return self.workspace_root / str(agent_id) / "_agent"

    def get_session_workspace_path(self, agent_id: UUID, session_id: UUID) -> Path:
        """Return path to the session's workspace directory."""
        return self.workspace_root / str(agent_id) / str(session_id)

    def get_session_data_dir(self, agent_id: UUID, session_id: UUID) -> Path:
        """Return path to the session's agent-accessible data/ directory."""
        return self.get_session_workspace_path(agent_id, session_id) / "data"

    def get_session_artifacts_dir(self, agent_id: UUID, session_id: UUID) -> Path:
        """Return path to the session's artifacts/ directory."""
        return self.get_session_workspace_path(agent_id, session_id) / "artifacts"

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

    def initialize_system_repo(
        self,
        default_settings: dict[str, Any] | None = None,
        default_config_template: dict[str, Any] | None = None,
    ) -> Path:
        """Initialize remote system repository and local clone on main branch."""
        system_dir = self.get_system_workspace_path()
        if not self.settings.enabled:
            system_dir.mkdir(parents=True, exist_ok=True)
            settings_file = system_dir / "settings.json"
            template_file = system_dir / "config-template.json"
            if not settings_file.exists():
                settings_file.write_text(
                    json.dumps(
                        default_settings
                        or {"skill_directories": ["~/.seamus/skills", "~/.skills"]},
                        indent=2,
                    ),
                    encoding="utf-8",
                )
            if not template_file.exists() and default_config_template is not None:
                template_file.write_text(
                    json.dumps(default_config_template, indent=2),
                    encoding="utf-8",
                )
            return system_dir

        repo_name = self.get_system_repo_name()
        self.client.get_or_create_repo(
            repo_name=repo_name,
            description="Seamus system settings and configuration templates",
        )

        clone_url = self.client.get_authenticated_clone_url(repo_name)

        if not (system_dir / ".git").exists():
            remote_branches = self.client.list_branches(repo_name)
            if "main" in remote_branches:
                system_dir.parent.mkdir(parents=True, exist_ok=True)
                self._run_git(system_dir.parent, ["clone", clone_url, system_dir.name])
                self._configure_git_identity(system_dir)
            else:
                system_dir.mkdir(parents=True, exist_ok=True)
                self._run_git(system_dir, ["init", "-b", "main"])
                self._configure_git_identity(system_dir)
                self._run_git(system_dir, ["remote", "add", "origin", clone_url])

            settings_file = system_dir / "settings.json"
            template_file = system_dir / "config-template.json"
            needs_commit = False
            if not settings_file.exists():
                settings_file.write_text(
                    json.dumps(
                        default_settings
                        or {"skill_directories": ["~/.seamus/skills", "~/.skills"]},
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                needs_commit = True
            if not template_file.exists() and default_config_template is not None:
                template_file.write_text(
                    json.dumps(default_config_template, indent=2),
                    encoding="utf-8",
                )
                needs_commit = True

            if needs_commit:
                self._run_git(system_dir, ["add", "-A"])
                self._run_git(
                    system_dir,
                    ["commit", "-m", "system: initialize settings and configuration template"],
                )
                self._run_git(system_dir, ["push", "-u", "origin", "main"])
        else:
            self._configure_git_identity(system_dir)

        return system_dir

    def read_system_settings(self) -> dict[str, Any] | None:
        """Read and deserialize system settings from the system repository."""
        system_dir = self.get_system_workspace_path()
        settings_file = system_dir / "settings.json"
        if not settings_file.exists():
            if self.settings.enabled:
                self.initialize_system_repo()
            else:
                return None
        if not settings_file.exists():
            return None
        try:
            data = json.loads(settings_file.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else None
        except Exception:
            logger.exception("Failed to parse settings.json from %s", settings_file)
            return None

    def commit_system_settings(self, settings_dict: dict[str, Any]) -> None:
        """Persist, commit, and push updated system settings."""
        system_dir = self.get_system_workspace_path()
        if not (system_dir / ".git").exists() and self.settings.enabled:
            self.initialize_system_repo(default_settings=settings_dict)
        else:
            system_dir.mkdir(parents=True, exist_ok=True)

        settings_file = system_dir / "settings.json"
        settings_file.write_text(json.dumps(settings_dict, indent=2), encoding="utf-8")

        if self.settings.enabled and (system_dir / ".git").exists():
            status = self._run_git(system_dir, ["status", "--porcelain", "settings.json"])
            if status.stdout.strip():
                self._run_git(system_dir, ["add", "settings.json"])
                self._run_git(system_dir, ["commit", "-m", "settings: update system settings"])
                self._run_git(system_dir, ["push", "origin", "main"])

    def read_system_config_template(self) -> dict[str, Any] | None:
        """Read and deserialize agent config template from the system repository."""
        system_dir = self.get_system_workspace_path()
        template_file = system_dir / "config-template.json"
        if not template_file.exists():
            if self.settings.enabled:
                self.initialize_system_repo()
            else:
                return None
        if not template_file.exists():
            return None
        try:
            data = json.loads(template_file.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else None
        except Exception:
            logger.exception("Failed to parse config-template.json from %s", template_file)
            return None

    def commit_system_config_template(self, template_dict: dict[str, Any]) -> None:
        """Persist, commit, and push updated configuration template."""
        system_dir = self.get_system_workspace_path()
        if not (system_dir / ".git").exists() and self.settings.enabled:
            self.initialize_system_repo(default_config_template=template_dict)
        else:
            system_dir.mkdir(parents=True, exist_ok=True)

        template_file = system_dir / "config-template.json"
        template_file.write_text(json.dumps(template_dict, indent=2), encoding="utf-8")

        if self.settings.enabled and (system_dir / ".git").exists():
            status = self._run_git(system_dir, ["status", "--porcelain", "config-template.json"])
            if status.stdout.strip():
                self._run_git(system_dir, ["add", "config-template.json"])
                self._run_git(system_dir, ["commit", "-m", "config: update template"])
                self._run_git(system_dir, ["push", "origin", "main"])

    def create_session_workspace(
        self,
        session: Session,
        agent: Agent,
        branch_from: str | None = None,
    ) -> Path:
        """Create or checkout session working tree on dedicated branch."""
        if not self.settings.enabled:
            session_dir = self.get_session_workspace_path(session.agent_id, session.id)
            (session_dir / "data").mkdir(parents=True, exist_ok=True)
            (session_dir / "data" / "skills").mkdir(parents=True, exist_ok=True)
            (session_dir / "data" / ".skills").mkdir(parents=True, exist_ok=True)
            artifacts_dir = self.get_session_artifacts_dir(session.agent_id, session.id)
            artifacts_dir.mkdir(parents=True, exist_ok=True)
            from seamus.harness.artifacts import seed_default_artifacts

            seed_default_artifacts(artifacts_dir)
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
                start_point = branch_from if branch_from else "origin/main"
                self._run_git(session_dir, ["checkout", "-b", branch_name, start_point])
        else:
            self._configure_git_identity(session_dir)
            self.sync_session_workspace(session)

        # Write session config
        self.commit_session_config(session)
        (session_dir / "data").mkdir(exist_ok=True)
        (session_dir / "data" / "skills").mkdir(parents=True, exist_ok=True)
        (session_dir / "data" / ".skills").mkdir(parents=True, exist_ok=True)
        (session_dir / "agent" / "state").mkdir(parents=True, exist_ok=True)
        artifacts_dir = self.get_session_artifacts_dir(session.agent_id, session.id)
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        from seamus.harness.artifacts import seed_default_artifacts

        seed_default_artifacts(artifacts_dir)

        if (session_dir / ".git").exists() and self.settings.enabled:
            status = self._run_git(session_dir, ["status", "--porcelain", "--", "artifacts"])
            if status.stdout.strip():
                self._run_git(session_dir, ["add", "artifacts"])
                self._run_git(session_dir, ["commit", "-m", "artifacts: initialize defaults"])
                self._run_git(session_dir, ["push", "origin", branch_name])

        return session_dir

    def sync_session_workspace(self, session: Session) -> bool:
        """Synchronize the local session working tree with its remote Gitea branch.

        Rationale: The agent workspace is not a freely accessible content base.
        External modifications in Gitea (e.g. administrator intervention or manual skill
        provisioning) represent purposeful changes that must immediately reflect in the agent's
        live workspace.
        """
        if not self.settings.enabled:
            return False

        session_dir = self.get_session_workspace_path(session.agent_id, session.id)
        if not (session_dir / ".git").exists():
            return False

        branch_name = f"session/{session.id}"
        try:
            self._run_git(session_dir, ["pull", "--rebase", "--autostash", "origin", branch_name])
            logger.info("Synchronized local session workspace with remote %s", branch_name)
            return True
        except Exception as exc:
            logger.warning("Failed to auto-pull session workspace %s: %s", session.id, exc)
            return False

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
            "status": session.status.value,
            "provenance": (
                session.provenance.model_dump(mode="json") if session.provenance else None
            ),
            "lineage": [entry.model_dump(mode="json") for entry in session.lineage],
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

    def get_sync_pr_diff(self, session: Session, agent: Agent) -> tuple[dict[str, Any] | None, str]:
        """Find the active open Sync PR and retrieve its unified diff."""
        if not self.settings.enabled:
            return None, ""

        active_pr = self.get_active_sync_pr(session, agent)
        if active_pr is None:
            return None, ""

        repo_name = self.get_agent_repo_name(session.agent_id)
        pr_number = active_pr.get("number")
        if not pr_number:
            return active_pr, ""

        try:
            diff_text = self.client.get_pull_request_diff(repo_name, int(pr_number))
            filtered_diff = filter_sync_pr_diff(diff_text)
            return active_pr, filtered_diff
        except Exception:
            logger.exception("Failed to query diff for Sync PR #%s in %s", pr_number, repo_name)
            return active_pr, ""

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
        """Approve and merge active Sync PR into main, restricted to data/ deliverables."""
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

        # 3. Execute data-scoped merge into main
        merge_sha: str | None = None
        try:
            agent_dir = self.get_agent_workspace_path(agent.id)
            if not (agent_dir / ".git").exists():
                self.initialize_agent_repo(agent)

            session_branch = f"session/{session.id}"
            remote_branches = self.client.list_branches(repo_name)
            if session_branch in remote_branches:
                self._run_git(agent_dir, ["checkout", "main"])
                self._run_git(agent_dir, ["pull", "origin", "main"])
                self._run_git(agent_dir, ["fetch", "origin"])

                try:
                    self._run_git(
                        agent_dir,
                        ["merge", "--no-commit", "--no-ff", f"origin/{session_branch}"],
                    )
                except GitWorkspaceError:
                    # Discard conflicts arising in harness-internal state/config directories
                    pass

                # Reset and restore agent/ to HEAD (main)
                self._run_git(agent_dir, ["reset", "HEAD", "--", "agent"])
                self._run_git(agent_dir, ["checkout", "HEAD", "--", "agent"])
                self._run_git(agent_dir, ["clean", "-fd", "agent"])

                # Stage only data/ deliverables
                if (agent_dir / "data").exists():
                    self._run_git(agent_dir, ["add", "-A", "data/"])

                commit_msg = f"sync: session/{session.name or session.id} (data/ deliverables)"
                self._run_git(agent_dir, ["commit", "-m", commit_msg])
                self._run_git(agent_dir, ["push", "origin", "main"])
                merge_sha = self._run_git(agent_dir, ["rev-parse", "HEAD"]).stdout.strip()
        except Exception:
            logger.exception(
                "Failed to perform data-scoped git merge on main for session %s", session.id
            )

        # 4. Finalize Sync PR in Gitea
        try:
            if merge_sha:
                return self.client.merge_pull_request(
                    repo_name=repo_name,
                    index=pr_number,
                    do="manually-merged",
                    delete_branch=False,
                    merge_commit_id=merge_sha,
                )
            return self.client.merge_pull_request(
                repo_name=repo_name,
                index=pr_number,
                do="merge",
                delete_branch=False,
            )
        except Exception:
            # Check if PR was already marked merged by Gitea auto-detection
            try:
                pr_info = self.client.get_pull_request(repo_name, pr_number)
                if pr_info.get("merged") is True:
                    return True
            except Exception:
                pass
            logger.exception("Failed to finalize Sync PR #%d for session %s", pr_number, session.id)
            return False

    def close_sync_pr(self, session: Session, agent: Agent) -> bool:
        """Close any active open Sync PR for the session without merging."""
        if not self.settings.enabled:
            return True

        active_pr = self.get_active_sync_pr(session, agent)
        if active_pr is None:
            return False

        pr_number = active_pr.get("number")
        if not pr_number:
            return False

        repo_name = self.get_agent_repo_name(session.agent_id)
        try:
            res = self.client.close_pull_request(repo_name, int(pr_number))
            logger.info("Closed Sync PR #%d for session %s", pr_number, session.id)
            return res
        except Exception:
            logger.exception("Failed to close Sync PR #%d for session %s", pr_number, session.id)
            return False

    def find_commit_for_event(
        self,
        agent_id: UUID,
        session_id: UUID,
        search_string: str,
    ) -> str | None:
        """Find the git commit SHA on the session branch that introduced the search string."""
        if not self.settings.enabled:
            return None

        session_dir = self.get_session_workspace_path(agent_id, session_id)
        if not (session_dir / ".git").exists():
            return None

        try:
            res = self._run_git(
                session_dir,
                ["log", f"-S{search_string}", "-n", "1", "--format=%H"],
            )
            sha = res.stdout.strip()
            return sha if sha else None
        except Exception:
            logger.debug(
                "No commit found for search string %s in session %s", search_string, session_id
            )
            return None

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

    def save_thread_todos(
        self,
        agent_id: UUID,
        session_id: UUID,
        thread_id: UUID,
        todos: list[dict[str, Any]],
    ) -> Path:
        """Save task todos to the thread state directory."""
        thread_dir = self.get_thread_state_dir(agent_id, session_id, thread_id)
        thread_dir.mkdir(parents=True, exist_ok=True)
        todos_file = thread_dir / "todos.json"
        todos_file.write_text(json.dumps(todos, indent=2), encoding="utf-8")
        return todos_file

    def load_thread_todos(
        self,
        agent_id: UUID,
        session_id: UUID,
        thread_id: UUID,
    ) -> list[dict[str, Any]]:
        """Load task todos from the thread state directory."""
        todos_file = self.get_thread_state_dir(agent_id, session_id, thread_id) / "todos.json"
        if not todos_file.exists():
            return []
        try:
            content = todos_file.read_text(encoding="utf-8")
            data = json.loads(content)
            return data if isinstance(data, list) else []
        except Exception:
            logger.exception("Failed to load thread todos from %s", todos_file)
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

        paths_to_check = [
            p for p in ["data", "agent/state", "artifacts"] if (session_dir / p).exists()
        ]
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
        try:
            self._run_git(session_dir, ["push", "origin", branch_name])
        except Exception:
            logger.info(
                "Remote contains external changes; rebasing session %s before retry push",
                session_id,
            )
            self._run_git(session_dir, ["pull", "--rebase", "--autostash", "origin", branch_name])
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


def reset_workspace_manager(manager: GitWorkspaceManager | None = None) -> None:
    """Reset or override the global GitWorkspaceManager singleton instance."""
    global _GLOBAL_WORKSPACE_MANAGER
    _GLOBAL_WORKSPACE_MANAGER = manager
