"""Git workspace manager orchestrating local clones and repositories."""

import contextlib
import json
import logging
import re
import subprocess
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from uuid import UUID

from ag_ui.core.events import Event
from pydantic import TypeAdapter

from seamus.domain.entities import Agent, Session
from seamus.persistence.client import GiteaClient
from seamus.persistence.config import PersistenceSettings, get_persistence_settings
from seamus.persistence.git_lock import (
    clean_stale_locks,
    extract_lock_paths_from_stderr,
    get_repo_lock,
    is_git_process_running_in_repo,
    sweep_workspace_stale_locks,
)

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


DEFAULT_WORKSPACE_GITIGNORE = """# Ephemeral build artifacts and caches
__pycache__/
*.py[cod]
*$py.class
*.so
.pytest_cache/
.mypy_cache/
.ruff_cache/

# Virtual environments
.venv/
venv/
env/

# Package and dependency directories
node_modules/
dist/
build/
*.egg-info/

# Ephemeral runtime data and logs
*.log
.DS_Store
"""


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
        try:
            sweep_workspace_stale_locks(self.workspace_root)
        except Exception:
            logger.debug("Failed to sweep stale locks during workspace initialization")
        try:
            from seamus.harness.sandbox import sync_bundled_skills

            sync_bundled_skills(self.workspace_root / "bundled_skills")
        except Exception:
            logger.debug("Failed to sync bundled skills during workspace initialization")

    def clean_stale_locks(self, repo_dir: Path, force: bool = False) -> list[Path]:
        """Find and remove stale git lock files in the specified repository."""
        return clean_stale_locks(repo_dir, force=force)

    def _run_git(
        self,
        cwd: Path,
        args: list[str],
        check: bool = True,
        max_retries: int = 2,
    ) -> subprocess.CompletedProcess[str]:
        """Execute a git command within the specified working directory with stale lock recovery."""
        repo_lock = get_repo_lock(cwd)
        with repo_lock:
            cmd = ["git", *args]
            for attempt in range(max_retries + 1):
                try:
                    res = subprocess.run(
                        cmd,
                        cwd=cwd,
                        check=check,
                        text=True,
                        capture_output=True,
                    )
                    return res
                except subprocess.CalledProcessError as exc:
                    stderr = exc.stderr or ""
                    lower_stderr = stderr.lower()
                    is_lock_error = (
                        (
                            "unable to create" in lower_stderr
                            and ".lock': file exists" in lower_stderr
                        )
                        or ("another git process seems to be running" in lower_stderr)
                        or ("index.lock': file exists" in lower_stderr)
                    )

                    if is_lock_error and attempt < max_retries:
                        # Extract any specific lock path mentioned in error message
                        extracted = extract_lock_paths_from_stderr(stderr)
                        for p in extracted:
                            try:
                                p.unlink(missing_ok=True)
                                logger.warning(
                                    "Removed stale lock file mentioned in git error: %s", p
                                )
                            except OSError:
                                pass

                        # Clean any other stale locks in cwd
                        removed = clean_stale_locks(cwd, force=False)
                        if not removed and not is_git_process_running_in_repo(cwd):
                            removed = clean_stale_locks(cwd, force=True)

                        logger.warning(
                            "Recovered from git lock error in %s; retrying (attempt %d/%d): %s",
                            cwd,
                            attempt + 1,
                            max_retries,
                            " ".join(cmd),
                        )
                        time.sleep(0.05)
                        continue

                    msg = (
                        f"Git command failed: '{' '.join(cmd)}' in {cwd}\n"
                        f"Exit code: {exc.returncode}\n"
                        f"Stdout: {exc.stdout}\n"
                        f"Stderr: {exc.stderr}"
                    )
                    logger.error(msg)
                    raise GitWorkspaceError(msg) from exc
            raise GitWorkspaceError(
                f"Git command unexpectedly terminated without result: {' '.join(cmd)}"
            )

    def _configure_git_identity(self, repo_dir: Path) -> None:
        """Configure local repository author name and email."""
        self._run_git(repo_dir, ["config", "user.name", "Seamus Agent"])
        self._run_git(repo_dir, ["config", "user.email", "agent@seamus.local"])

    def get_agent_org_name(self, agent_id: UUID) -> str:
        """Return standardized Gitea organization name for an agent."""
        return f"agent-{agent_id.hex}"

    def get_session_repo_name(self, session_id: UUID) -> str:
        """Return standardized repository name for a session."""
        return f"session-{session_id}"

    def get_agent_repo_name(self, agent_id: UUID | None = None) -> str:
        """Return standardized repository name for an agent baseline repository."""
        return "agent"

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

    def get_session_notes_dir(self, agent_id: UUID, session_id: UUID) -> Path:
        """Return path to the session's notes/ directory under data/."""
        return self.get_session_workspace_path(agent_id, session_id) / "data" / "notes"

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

        org_name = self.get_agent_org_name(agent.id)
        self.client.get_or_create_org(
            org_name=org_name,
            full_name=agent.name or f"Agent {agent.id}",
            description=f"Seamus organization for agent {agent.name or agent.id}",
        )

        repo_name = self.get_agent_repo_name(agent.id)
        self.client.get_or_create_repo(
            repo_name=repo_name,
            description=f"Seamus repository for agent {agent.name or agent.id}",
            owner=org_name,
        )

        agent_dir = self.get_agent_workspace_path(agent.id)
        clone_url = self.client.get_authenticated_clone_url(repo_name, owner=org_name)

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

            # Seed default .gitignore
            gitignore_file = agent_dir / ".gitignore"
            if not gitignore_file.exists():
                gitignore_file.write_text(DEFAULT_WORKSPACE_GITIGNORE, encoding="utf-8")

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
        else:
            clean_stale_locks(agent_dir)

        config_dir = agent_dir / "agent" / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_payload = {
            "id": str(agent.id),
            "name": agent.name,
            "custom_name": agent.custom_name,
            "generated_name": agent.generated_name,
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
            clean_stale_locks(system_dir)
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
            clean_stale_locks(system_dir)
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
        """Create or checkout session working tree in dedicated session repo."""
        if not self.settings.enabled:
            session_dir = self.get_session_workspace_path(session.agent_id, session.id)
            if (session_dir / ".git").exists():
                clean_stale_locks(session_dir)
            (session_dir / "data").mkdir(parents=True, exist_ok=True)
            (session_dir / "data" / "skills").mkdir(parents=True, exist_ok=True)
            (session_dir / "data" / ".skills").mkdir(parents=True, exist_ok=True)
            (session_dir / "data" / "notes").mkdir(parents=True, exist_ok=True)
            artifacts_dir = self.get_session_artifacts_dir(session.agent_id, session.id)
            artifacts_dir.mkdir(parents=True, exist_ok=True)
            from seamus.harness.artifacts import seed_default_artifacts

            seed_default_artifacts(artifacts_dir)
            return session_dir

        # Ensure base agent repo exists first
        agent_dir = self.get_agent_workspace_path(agent.id)
        if not (agent_dir / ".git").exists():
            self.initialize_agent_repo(agent)
        else:
            clean_stale_locks(agent_dir)

        org_name = self.get_agent_org_name(session.agent_id)
        session_repo_name = self.get_session_repo_name(session.id)
        agent_repo_name = self.get_agent_repo_name(agent.id)

        parent_session_id = None
        if session.provenance and session.provenance.parent_session_id:
            parent_session_id = session.provenance.parent_session_id

        # Check if session repo exists in Gitea org
        session_repo = self.client.get_repo(session_repo_name, owner=org_name)
        if not session_repo:
            # Fork from parent session if branched, otherwise from agent baseline repo
            if parent_session_id:
                parent_repo_name = self.get_session_repo_name(parent_session_id)
                if self.client.get_repo(parent_repo_name, owner=org_name):
                    source_repo = parent_repo_name
                else:
                    source_repo = agent_repo_name
            else:
                source_repo = agent_repo_name

            self.client.fork_repo(
                source_owner=org_name,
                source_repo=source_repo,
                target_org=org_name,
                fork_name=session_repo_name,
            )

        clone_url = self.client.get_authenticated_clone_url(session_repo_name, owner=org_name)
        session_dir = self.get_session_workspace_path(session.agent_id, session.id)
        branch_name = "main"

        if not (session_dir / ".git").exists():
            session_dir.parent.mkdir(parents=True, exist_ok=True)
            # If the remote repository was created empty (e.g. 409 multi-fork fallback),
            # seed it first
            source_dir = (
                self.get_session_workspace_path(session.agent_id, parent_session_id)
                if parent_session_id
                and (
                    self.get_session_workspace_path(session.agent_id, parent_session_id) / ".git"
                ).exists()
                else self.get_agent_workspace_path(session.agent_id)
            )
            if (source_dir / ".git").exists():
                with contextlib.suppress(GitWorkspaceError):
                    self._run_git(source_dir, ["push", clone_url, "main:main"])

            self._run_git(session_dir.parent, ["clone", clone_url, session_dir.name])
            self._configure_git_identity(session_dir)

            if branch_from:
                self._run_git(session_dir, ["checkout", "-B", branch_name, branch_from])
                self._run_git(session_dir, ["push", "--force", "-u", "origin", branch_name])
            else:
                try:
                    self._run_git(session_dir, ["checkout", branch_name])
                except Exception:
                    pass
        else:
            clean_stale_locks(session_dir)
            self._configure_git_identity(session_dir)
            self.sync_session_workspace(session)

        # Write session config
        self.commit_session_config(session)
        (session_dir / "data").mkdir(exist_ok=True)
        (session_dir / "data" / "skills").mkdir(parents=True, exist_ok=True)
        (session_dir / "data" / ".skills").mkdir(parents=True, exist_ok=True)
        (session_dir / "data" / "notes").mkdir(parents=True, exist_ok=True)
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
                active_branch = (
                    self._run_git(
                        session_dir, ["rev-parse", "--abbrev-ref", "HEAD"], check=False
                    ).stdout.strip()
                    or branch_name
                )
                if not active_branch or active_branch == "HEAD":
                    active_branch = branch_name
                self._run_git(session_dir, ["push", "origin", active_branch])

        return session_dir

    def sync_session_workspace(self, session: Session) -> bool:
        """Synchronize the local session working tree with its remote Gitea repository.

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

        clean_stale_locks(session_dir)
        try:
            active_branch = (
                self._run_git(
                    session_dir, ["rev-parse", "--abbrev-ref", "HEAD"], check=False
                ).stdout.strip()
                or "main"
            )
            self._run_git(session_dir, ["pull", "--rebase", "--autostash", "origin", active_branch])
            logger.info("Synchronized local session workspace with remote %s", active_branch)
            return True
        except Exception as exc:
            logger.warning("Failed to auto-pull session workspace %s: %s", session.id, exc)
            return False

    def write_session_config_file(
        self,
        session: Session,
        config_dict: dict[str, Any] | None = None,
        secret_versions: dict[tuple[str, str], int] | Mapping[Any, int] | None = None,
    ) -> Path | None:
        """Write session configuration JSON to agent/config/config.json in the session workspace."""
        session_dir = self.get_session_workspace_path(session.agent_id, session.id)
        if not session_dir.exists() and not self.settings.enabled:
            return None
        if self.settings.enabled and not (session_dir / ".git").exists():
            return None

        config_dir = session_dir / "agent" / "config"
        config_dir.mkdir(parents=True, exist_ok=True)

        raw_config = config_dict if config_dict is not None else session.config.model_dump()

        from seamus.vault.interpolator import (
            collect_secret_references,
            explode_secret_references,
            get_secret_versions_for_references_sync,
        )

        refs = collect_secret_references(raw_config, allow_version=True)
        if refs:
            v_map = dict(secret_versions or {})
            if not v_map and getattr(session, "secret_versions", None):
                v_map.update(session.secret_versions)
            if not v_map:
                try:
                    from seamus.harness.runner import get_runner_registry

                    runner = get_runner_registry().get_runner(session)
                    if runner and getattr(runner, "_loaded_secret_versions", None):
                        v_map.update(runner._loaded_secret_versions)
                except Exception:
                    pass
            resolved_versions = get_secret_versions_for_references_sync(refs, version_map=v_map)
            raw_config = explode_secret_references(raw_config, resolved_versions)

        config_payload = {
            "id": str(session.id),
            "agent_id": str(session.agent_id),
            "custom_name": session.custom_name,
            "daemon_name": session.daemon_name,
            "name": session.name,
            "created_at": session.created_at.isoformat(),
            "config": raw_config,
            "status": session.status.value,
            "active_plan_id": session.active_plan_id,
            "provenance": (
                session.provenance.model_dump(mode="json") if session.provenance else None
            ),
            "lineage": [entry.model_dump(mode="json") for entry in session.lineage],
            "threads": [
                {
                    "id": str(t.id),
                    "custom_name": t.custom_name,
                    "daemon_name": t.daemon_name,
                    "name": t.name,
                    "exchange_count": t.exchange_count,
                    "created_at": t.created_at.isoformat(),
                    "is_open": t.is_open,
                    "status": t.status.value,
                    "mode": t.mode,
                    "phase": t.phase,
                }
                for t in sorted(session.threads.values(), key=lambda t: t.created_at)
            ],
        }
        config_file = config_dir / "config.json"
        config_file.write_text(json.dumps(config_payload, indent=2), encoding="utf-8")
        return config_file

    def commit_session_config(
        self,
        session: Session,
        config_dict: dict[str, Any] | None = None,
        secret_versions: dict[tuple[str, str], int] | Mapping[Any, int] | None = None,
    ) -> None:
        """Serialize and commit session configuration directory to session branch."""
        if not self.settings.enabled:
            return

        session_dir = self.get_session_workspace_path(session.agent_id, session.id)
        if not (session_dir / ".git").exists():
            return

        clean_stale_locks(session_dir)

        self.write_session_config_file(
            session, config_dict=config_dict, secret_versions=secret_versions
        )

        status = self._run_git(session_dir, ["status", "--porcelain", "agent/config/"])
        if status.stdout.strip():
            active_branch = (
                self._run_git(
                    session_dir, ["rev-parse", "--abbrev-ref", "HEAD"], check=False
                ).stdout.strip()
                or "main"
            )
            if not active_branch or active_branch == "HEAD":
                active_branch = "main"
            self._run_git(session_dir, ["add", "-A", "agent/config/"])
            self._run_git(
                session_dir,
                ["commit", "-m", f"config: update session config [session={session.id}]"],
            )
            self._run_git(session_dir, ["push", "-u", "origin", active_branch])

    def get_active_sync_pr(self, session: Session, agent: Agent) -> dict[str, Any] | None:
        """Find the active open cross-fork Sync PR from session repo to agent repo."""
        if not self.settings.enabled:
            return None

        org_name = self.get_agent_org_name(session.agent_id)
        base_repo = self.get_agent_repo_name(session.agent_id)
        session_repo = self.get_session_repo_name(session.id)
        try:
            open_prs = self.client.list_pull_requests(base_repo, state="open", owner=org_name)
            for pr in open_prs:
                head_repo = pr.get("head", {}).get("repo", {}).get("name")
                head_label = pr.get("head", {}).get("label", "")
                if head_repo == session_repo or session_repo in head_label:
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

        org_name = self.get_agent_org_name(session.agent_id)
        base_repo = self.get_agent_repo_name(session.agent_id)
        pr_number = active_pr.get("number")
        if not pr_number:
            return active_pr, ""

        try:
            diff_text = self.client.get_pull_request_diff(base_repo, int(pr_number), owner=org_name)
            filtered_diff = filter_sync_pr_diff(diff_text)
            return active_pr, filtered_diff
        except Exception:
            logger.exception(
                "Failed to query diff for Sync PR #%s in %s/%s", pr_number, org_name, base_repo
            )
            return active_pr, ""

    def open_sync_pr(self, session: Session, agent: Agent) -> dict[str, Any] | None:
        """Open an automated cross-fork Sync PR from session repo to agent repo."""
        if not self.settings.enabled:
            return None

        active_pr = self.get_active_sync_pr(session, agent)
        if active_pr is not None:
            return active_pr

        org_name = self.get_agent_org_name(session.agent_id)
        base_repo = self.get_agent_repo_name(session.agent_id)
        session_repo = self.get_session_repo_name(session.id)
        head = f"{org_name}/{session_repo}:main"
        base = "main"
        title = f"Sync PR: session/{session.name or session.id}"
        body = f"Automated Sync PR for session `{session.id}` (agent `{agent.name or agent.id}`)."
        try:
            pr = self.client.create_pull_request(
                repo_name=base_repo,
                title=title,
                head=head,
                base=base,
                body=body,
                owner=org_name,
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
        org_name = self.get_agent_org_name(session.agent_id)
        base_repo = self.get_agent_repo_name(session.agent_id)

        # 1. Attempt approval review (log and continue if self-approval rejected)
        try:
            self.client.approve_pull_request(
                repo_name=base_repo,
                index=pr_number,
                body="Accepted by user",
                owner=org_name,
            )
        except Exception:
            logger.warning("Approval review failed on PR #%d (proceeding with merge)", pr_number)

        # 2. Wait briefly for Gitea to evaluate mergeability
        for _ in range(10):
            time.sleep(0.3)
            try:
                pr_data = self.client.get_pull_request(base_repo, pr_number, owner=org_name)
                if pr_data.get("mergeable") is True:
                    break
            except Exception:
                break

        # 3. Execute data-scoped merge into main on agent repo
        merge_sha: str | None = None
        try:
            agent_dir = self.get_agent_workspace_path(agent.id)
            if not (agent_dir / ".git").exists():
                self.initialize_agent_repo(agent)

            session_dir = self.get_session_workspace_path(session.agent_id, session.id)
            if (session_dir / ".git").exists():
                self._run_git(agent_dir, ["checkout", "main"])
                self._run_git(agent_dir, ["pull", "origin", "main"])
                self._run_git(agent_dir, ["fetch", str(session_dir.resolve()), "main"])

                try:
                    self._run_git(
                        agent_dir,
                        ["merge", "--no-commit", "--no-ff", "FETCH_HEAD"],
                    )
                except GitWorkspaceError:
                    # Discard conflicts arising in harness-internal state/config directories
                    pass

                # Reset and restore non-data directories to HEAD (main)
                for internal_dir in ("agent", "notes", "artifacts"):
                    with contextlib.suppress(GitWorkspaceError):
                        self._run_git(agent_dir, ["reset", "HEAD", "--", internal_dir])
                    with contextlib.suppress(GitWorkspaceError):
                        self._run_git(agent_dir, ["checkout", "HEAD", "--", internal_dir])
                    with contextlib.suppress(GitWorkspaceError):
                        self._run_git(agent_dir, ["clean", "-fd", internal_dir])

                # Stage only data/ deliverables
                if (agent_dir / "data").exists():
                    self._run_git(agent_dir, ["add", "-A", "data/"])

                status = self._run_git(agent_dir, ["status", "--porcelain"])
                if status.stdout.strip():
                    commit_msg = f"sync: session/{session.name or session.id} (data/ deliverables)"
                    self._run_git(agent_dir, ["commit", "-m", commit_msg])
                    self._run_git(agent_dir, ["push", "origin", "main"])
                    merge_sha = self._run_git(agent_dir, ["rev-parse", "HEAD"]).stdout.strip()
                else:
                    with contextlib.suppress(GitWorkspaceError):
                        self._run_git(agent_dir, ["merge", "--abort"])
        except Exception:
            logger.exception(
                "Failed to perform data-scoped git merge on main for session %s", session.id
            )

        # 4. Finalize Sync PR in Gitea
        try:
            if merge_sha:
                return self.client.merge_pull_request(
                    repo_name=base_repo,
                    index=pr_number,
                    do="manually-merged",
                    delete_branch=False,
                    merge_commit_id=merge_sha,
                    owner=org_name,
                )
            return self.client.merge_pull_request(
                repo_name=base_repo,
                index=pr_number,
                do="merge",
                delete_branch=False,
                owner=org_name,
            )
        except Exception:
            # Check if PR was already marked merged by Gitea auto-detection
            try:
                pr_info = self.client.get_pull_request(base_repo, pr_number, owner=org_name)
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

        org_name = self.get_agent_org_name(session.agent_id)
        base_repo = self.get_agent_repo_name(session.agent_id)
        try:
            res = self.client.close_pull_request(base_repo, int(pr_number), owner=org_name)
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
        before: bool = False,
    ) -> str | None:
        """Find the git commit SHA on the session branch that introduced the search string.

        If before is True, attempts to resolve the immediate parent commit (the state
        prior to this event).
        """
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
            if not sha:
                return None
            if before:
                try:
                    parent_res = self._run_git(session_dir, ["rev-parse", f"{sha}~1"])
                    parent_sha = parent_res.stdout.strip()
                    if parent_sha:
                        return parent_sha
                except Exception:
                    pass
            return sha
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

    def save_thread_external_checkpoints(
        self,
        agent_id: UUID,
        session_id: UUID,
        thread_id: UUID,
        manifest_data: dict[str, Any],
    ) -> Path:
        """Save mounted repository checkpoint metadata to thread state directory."""
        thread_dir = self.get_thread_state_dir(agent_id, session_id, thread_id)
        thread_dir.mkdir(parents=True, exist_ok=True)
        ext_cp_file = thread_dir / "external_checkpoints.json"
        ext_cp_file.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")
        return ext_cp_file

    def load_thread_external_checkpoints(
        self,
        agent_id: UUID,
        session_id: UUID,
        thread_id: UUID,
    ) -> dict[str, Any] | None:
        """Load mounted repository checkpoint metadata from thread state directory."""
        ext_cp_file = (
            self.get_thread_state_dir(agent_id, session_id, thread_id) / "external_checkpoints.json"
        )
        if not ext_cp_file.exists():
            return None
        try:
            content = ext_cp_file.read_text(encoding="utf-8")
            return json.loads(content)  # type: ignore[no-any-return]
        except Exception:
            logger.exception("Failed to load thread external checkpoints from %s", ext_cp_file)
            return None

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

        clean_stale_locks(session_dir)

        paths_to_check = [
            p
            for p in ["data", "agent/state", "agent/config", "artifacts", "notes"]
            if (session_dir / p).exists()
        ]
        if not paths_to_check:
            return False

        status = self._run_git(session_dir, ["status", "--porcelain", "--", *paths_to_check])
        if not status.stdout.strip():
            return False

        branch_name = (
            self._run_git(
                session_dir, ["rev-parse", "--abbrev-ref", "HEAD"], check=False
            ).stdout.strip()
            or "main"
        )
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

        branch_name = (
            self._run_git(
                session_dir, ["rev-parse", "--abbrev-ref", "HEAD"], check=False
            ).stdout.strip()
            or "main"
        )
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
