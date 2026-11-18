"""External Git repository manager, dual-index snapshot engine, and Gitea backing."""

from __future__ import annotations

import hashlib
import logging
import os
import re
import shutil
import subprocess
import tarfile
import time
from collections import Counter, defaultdict
from collections.abc import Sequence
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID

from seamus.config.models import ExternalRepositoryConfig
from seamus.domain.repositories import MountedRepositoryCheckpointRecord
from seamus.persistence.config import PersistenceSettings

if TYPE_CHECKING:
    from seamus.persistence.client import GiteaClient
    from seamus.vault.client import VaultClient

logger = logging.getLogger(__name__)


def canonicalize_git_url(url: str) -> str:
    """Normalize a Git repository URL for deterministic project identity hashing."""
    trimmed = url.strip()
    if not trimmed:
        return ""

    # Strip trailing slashes and .git suffix
    cleaned = trimmed.rstrip("/")
    if cleaned.endswith(".git"):
        cleaned = cleaned[:-4].rstrip("/")

    # Normalize scheme and host if HTTP/HTTPS
    if "://" in cleaned:
        scheme, rest = cleaned.split("://", 1)
        # Remove embedded user:password if present
        if "@" in rest:
            _, rest = rest.split("@", 1)
        if "/" in rest:
            host, path = rest.split("/", 1)
            return f"{scheme.lower()}://{host.lower()}/{path.lower()}"
        return f"{scheme.lower()}://{rest.lower()}"

    # Handle scp-style SSH URLs: git@github.com:user/repo
    if "@" in cleaned and ":" in cleaned and not cleaned.startswith("/"):
        user_host, path = cleaned.split(":", 1)
        return f"{user_host.lower()}:{path.lower()}"

    return cleaned


MIRRORS_ORG_NAME: str = "mirrors"


def derive_project_url_hash(url: str) -> str:
    """Derive a deterministic 8-character hash from a Git URL."""
    norm = canonicalize_git_url(url)
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:8]


def derive_session_hash(session_id: UUID) -> str:
    """Derive an 8-character identifier from a session UUID."""
    return session_id.hex[:8]


def derive_project_id(canonical_url: str) -> str:
    """Derive a deterministic 8-character project identifier from a canonical Git URL."""
    return f"proj-{derive_project_url_hash(canonical_url)}"


def derive_repository_mount_name(url: str) -> str:
    """Derive a clean, safe directory name from a Git repository URL."""
    cleaned = url.strip().rstrip("/")
    if cleaned.endswith(".git"):
        cleaned = cleaned[:-4].rstrip("/")

    # Extract last path component
    raw_name = cleaned.split("/")[-1].split(":")[-1]
    # Sanitize: allow lowercase alphanumeric, underscores, hyphens
    sanitized = re.sub(r"[^a-zA-Z0-9_\-]", "-", raw_name).lower().strip("-")
    # Prevent path traversal tokens or empty names
    if not sanitized or sanitized in (".", ".."):
        return "repo"
    return sanitized


def derive_project_name(url: str) -> str:
    """Derive the project name component from a Git repository URL."""
    return derive_repository_mount_name(url)


def calculate_mount_paths(
    repositories: Sequence[ExternalRepositoryConfig],
) -> dict[str, str]:
    """Map repository IDs to deterministic, collision-proof mount names under /projects/.

    When multiple repositories produce the same base name, numeric suffixes are appended
    to ALL colliding entries based on their encounter order (_0, _1, ...). Unique names
    remain suffix-free.
    """
    base_names = [derive_repository_mount_name(r.url) for r in repositories]
    counts = Counter(base_names)

    occurrences: dict[str, int] = defaultdict(int)
    mapping: dict[str, str] = {}

    for repo, base in zip(repositories, base_names, strict=True):
        if counts[base] == 1:
            mapping[repo.id] = base
        else:
            idx = occurrences[base]
            occurrences[base] += 1
            mapping[repo.id] = f"{base}_{idx}"

    return mapping


def get_mirror_repo_name(url: str) -> str:
    """Return standardized Gitea repository name for an upstream mirror in mirrors org."""
    project_name = derive_project_name(url)
    url_hash = derive_project_url_hash(url)
    return f"project-{project_name}-{url_hash}"


def get_session_fork_repo_name(url: str, session_id: UUID) -> str:
    """Return standardized Gitea repository name for a session fork in agent org."""
    project_name = derive_project_name(url)
    url_hash = derive_project_url_hash(url)
    session_hash = derive_session_hash(session_id)
    return f"project-{project_name}-{url_hash}-{session_hash}"


class ExternalRepositoryManager:
    """Orchestrates external Git project cloning, dual-index checkpointing, and Gitea backing."""

    def __init__(
        self,
        workspace_root: Path,
        settings: PersistenceSettings | None = None,
        client: GiteaClient | None = None,
        vault_client: VaultClient | None = None,
    ) -> None:
        self.workspace_root = workspace_root
        self.settings = settings or PersistenceSettings()
        self._client = client
        self._vault_client = vault_client
        try:
            from seamus.persistence.git_lock import sweep_workspace_stale_locks

            sweep_workspace_stale_locks(self.workspace_root)
        except Exception:
            logger.debug("Failed to sweep stale locks during external repo manager initialization")

    @property
    def client(self) -> GiteaClient:
        if self._client is None:
            from seamus.persistence.client import GiteaClient

            self._client = GiteaClient(self.settings)
        return self._client

    @property
    def vault_client(self) -> VaultClient:
        if self._vault_client is None:
            from seamus.vault.client import get_default_vault_client

            self._vault_client = get_default_vault_client()
        return self._vault_client

    def clean_stale_locks(self, repo_dir: Path, force: bool = False) -> list[Path]:
        """Find and remove stale git lock files in the specified repository."""
        from seamus.persistence.git_lock import clean_stale_locks

        return clean_stale_locks(repo_dir, force=force)

    def _run_git(
        self,
        cwd: Path,
        args: list[str],
        env: dict[str, str] | None = None,
        check: bool = True,
        max_retries: int = 2,
    ) -> subprocess.CompletedProcess[str]:
        from seamus.persistence.git_lock import (
            clean_stale_locks,
            extract_lock_paths_from_stderr,
            get_repo_lock,
            is_git_process_running_in_repo,
        )

        repo_lock = get_repo_lock(cwd)
        with repo_lock:
            full_env = os.environ.copy()
            if env:
                full_env.update(env)
            # Prevent prompt hangs
            full_env["GIT_TERMINAL_PROMPT"] = "0"
            cmd = ["git", *args]

            for attempt in range(max_retries + 1):
                try:
                    res = subprocess.run(
                        cmd,
                        cwd=cwd,
                        env=full_env,
                        check=check,
                        capture_output=True,
                        text=True,
                    )
                    if not check and res.returncode == 128:
                        stderr = res.stderr or ""
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
                            extracted = extract_lock_paths_from_stderr(stderr)
                            for p in extracted:
                                try:
                                    p.unlink(missing_ok=True)
                                except OSError:
                                    pass
                            clean_stale_locks(cwd, force=True)
                            logger.warning(
                                "Recovered from git lock error (check=False) in %s; "
                                "retrying (attempt %d/%d): %s",
                                cwd,
                                attempt + 1,
                                max_retries,
                                " ".join(cmd),
                            )
                            time.sleep(0.05)
                            continue
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
                        extracted = extract_lock_paths_from_stderr(stderr)
                        for p in extracted:
                            try:
                                p.unlink(missing_ok=True)
                            except OSError:
                                pass
                        removed = clean_stale_locks(cwd, force=False)
                        if not removed and not is_git_process_running_in_repo(cwd):
                            clean_stale_locks(cwd, force=True)
                        logger.warning(
                            "Recovered from git lock error in %s; retrying (attempt %d/%d): %s",
                            cwd,
                            attempt + 1,
                            max_retries,
                            " ".join(cmd),
                        )
                        time.sleep(0.05)
                        continue
                    raise
            raise RuntimeError(
                f"Git command unexpectedly terminated without result: {' '.join(cmd)}"
            )

    def _configure_git_identity(self, repo_dir: Path) -> None:
        self._run_git(repo_dir, ["config", "user.name", "Seamus Agent"])
        self._run_git(repo_dir, ["config", "user.email", "agent@seamus.local"])
        self._run_git(repo_dir, ["config", "safe.directory", "*"])

    @staticmethod
    def get_mirror_repo_name(url: str) -> str:
        """Return standardized Gitea repository name for an upstream mirror in mirrors org."""
        return get_mirror_repo_name(url)

    @staticmethod
    def get_session_fork_repo_name(url: str, session_id: UUID) -> str:
        """Return standardized Gitea repository name for a session fork in agent org."""
        return get_session_fork_repo_name(url, session_id)

    def get_project_repo_name(self, project_id: str) -> str:
        """Return the Gitea repository name for an external project (backward compatibility)."""
        return f"project-{project_id}"

    def get_session_projects_dir(self, agent_id: UUID, session_id: UUID) -> Path:
        """Return directory where external repo working copies reside for a session."""
        return self.workspace_root / str(agent_id) / str(session_id) / "projects"

    def get_session_indexes_dir(self, agent_id: UUID, session_id: UUID) -> Path:
        """Return directory where alternate checkpoint indexes reside outside mounts."""
        return self.workspace_root / str(agent_id) / str(session_id) / ".seamus_indexes"

    def get_working_copy_path(
        self,
        agent_id: UUID,
        session_id: UUID,
        mount_name: str,
    ) -> Path:
        """Return local filesystem path of a session's mounted repository working copy."""
        return self.get_session_projects_dir(agent_id, session_id) / mount_name

    def ensure_mirror_in_gitea(
        self,
        repo_config: ExternalRepositoryConfig,
    ) -> str:
        """Ensure mirrors organization exists and mirror repository is migrated from upstream."""
        mirror_name = self.get_mirror_repo_name(repo_config.url)
        if not self.settings.enabled:
            return mirror_name

        # 1. Ensure mirrors organization exists
        self.client.get_or_create_org(
            org_name=MIRRORS_ORG_NAME,
            full_name="External Mirrors",
            description="Central organization holding read-only upstream Git mirrors for Seamus",
        )

        # 2. Check if mirror repository already exists in mirrors org
        mirror_repo = self.client.get_repo(mirror_name, owner=MIRRORS_ORG_NAME)
        if mirror_repo:
            return mirror_name

        # 3. Migrate remote repository as a read-only pull mirror with frequent sync
        token = self._resolve_credentials_sync(repo_config.credentials)
        auth_token = None
        auth_username = None
        auth_password = None
        if token:
            if ":" in token:
                auth_username, auth_password = token.split(":", 1)
            else:
                auth_token = token

        logger.info(
            "Provisioning Gitea pull mirror %s in org %s from %s",
            mirror_name,
            MIRRORS_ORG_NAME,
            repo_config.url,
        )
        try:
            self.client.migrate_repo_as_mirror(
                clone_addr=repo_config.url,
                repo_name=mirror_name,
                repo_owner=MIRRORS_ORG_NAME,
                mirror_interval="10m",
                auth_token=auth_token,
                auth_username=auth_username,
                auth_password=auth_password,
                private=True,
            )
        except Exception:
            logger.exception(
                "Failed to migrate pull mirror %s; verifying repo existence", mirror_name
            )
            if not self.client.get_repo(mirror_name, owner=MIRRORS_ORG_NAME):
                raise

        return mirror_name

    def ensure_session_fork_in_gitea(
        self,
        agent_id: UUID,
        session_id: UUID,
        repo_config: ExternalRepositoryConfig,
        parent_session_id: UUID | None = None,
    ) -> str:
        """Ensure session fork exists in agent organization, forked from parent or mirror."""
        mirror_name = self.ensure_mirror_in_gitea(repo_config)
        agent_org = f"agent-{agent_id.hex}"
        fork_name = self.get_session_fork_repo_name(repo_config.url, session_id)

        if not self.settings.enabled:
            return fork_name

        # Ensure agent organization exists
        self.client.get_or_create_org(
            org_name=agent_org,
            full_name=f"Agent {agent_id}",
            description=f"Seamus organization for agent {agent_id}",
        )

        existing_fork = self.client.get_repo(fork_name, owner=agent_org)
        if existing_fork:
            return fork_name

        # Determine fork source: parent session fork if available, else central mirror
        source_owner = MIRRORS_ORG_NAME
        source_repo = mirror_name
        if parent_session_id:
            parent_fork_name = self.get_session_fork_repo_name(repo_config.url, parent_session_id)
            if self.client.get_repo(parent_fork_name, owner=agent_org):
                source_owner = agent_org
                source_repo = parent_fork_name

        logger.info(
            "Forking external repo %s/%s into %s/%s for session %s",
            source_owner,
            source_repo,
            agent_org,
            fork_name,
            session_id,
        )
        self.client.fork_repo(
            source_owner=source_owner,
            source_repo=source_repo,
            target_org=agent_org,
            fork_name=fork_name,
        )
        return fork_name

    def ensure_project_repo_in_gitea(
        self,
        repo_config: ExternalRepositoryConfig,
    ) -> str:
        """Ensure Gitea mirror repository exists and return project id."""
        self.ensure_mirror_in_gitea(repo_config)
        canonical_url = canonicalize_git_url(repo_config.url)
        return derive_project_id(canonical_url)

    def _resolve_credentials_sync(self, credentials_ref: str | None) -> str | None:
        """Resolve OpenBao credential reference synchronously without leaking secrets."""
        if not credentials_ref or not credentials_ref.strip():
            return None
        trimmed = credentials_ref.strip()
        if not trimmed.startswith("${secret("):
            return trimmed

        try:
            from seamus.vault.interpolator import resolve_secret_string_with_versions_sync

            resolved, _ = resolve_secret_string_with_versions_sync(
                trimmed,
                client=self.vault_client,
            )
            return resolved
        except Exception:
            logger.exception("Failed to resolve secret reference for Git credentials")
            return None

    def _mirror_upstream_to_gitea(
        self,
        repo_config: ExternalRepositoryConfig,
        gitea_repo_name: str,
    ) -> None:
        """Clone upstream repo temporarily and push initial branches to Gitea."""
        temp_dir = self.workspace_root / ".temp_mirrors" / gitea_repo_name
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
        temp_dir.parent.mkdir(parents=True, exist_ok=True)

        token = self._resolve_credentials_sync(repo_config.credentials)
        upstream_url = repo_config.url
        if token and upstream_url.startswith("https://"):
            # Insert token into clone URL for temporary fetch
            clean_url = upstream_url[8:]
            auth_clone_url = f"https://oauth2:{token}@{clean_url}"
        else:
            auth_clone_url = upstream_url

        try:
            # Clone bare or single branch
            self._run_git(
                temp_dir.parent,
                ["clone", "--bare", auth_clone_url, temp_dir.name],
            )
            self._configure_git_identity(temp_dir)

            gitea_url = self.client.get_authenticated_clone_url(
                gitea_repo_name, owner=MIRRORS_ORG_NAME
            )
            self._run_git(temp_dir, ["remote", "add", "gitea", gitea_url])
            self._run_git(temp_dir, ["push", "--all", "gitea"])
            self._run_git(temp_dir, ["push", "--tags", "gitea"])
        except Exception:
            logger.exception(
                "Failed to mirror upstream %s to Gitea %s", repo_config.url, gitea_repo_name
            )
        finally:
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)

    def provision_session_working_copy(
        self,
        agent_id: UUID,
        session_id: UUID,
        repo_config: ExternalRepositoryConfig,
        mount_name: str,
        start_commit: str | None = None,
        parent_session_id: UUID | None = None,
    ) -> Path:
        """Create or checkout a session working copy for a mounted repository."""
        fork_name = self.ensure_session_fork_in_gitea(
            agent_id, session_id, repo_config, parent_session_id=parent_session_id
        )
        working_copy = self.get_working_copy_path(agent_id, session_id, mount_name)

        if not self.settings.enabled:
            # Local offline fallback
            working_copy.mkdir(parents=True, exist_ok=True)
            if not (working_copy / ".git").exists():
                self._run_git(working_copy, ["init", "-b", repo_config.branch])
                self._configure_git_identity(working_copy)
                (working_copy / "README.md").write_text(f"# {mount_name}\n", encoding="utf-8")
                self._run_git(working_copy, ["add", "README.md"])
                self._run_git(working_copy, ["commit", "-m", "Initial commit"])
                self._record_initial_base_commit(agent_id, session_id, repo_config, working_copy)
            return working_copy

        agent_org = f"agent-{agent_id.hex}"
        clone_url = self.client.get_authenticated_clone_url(fork_name, owner=agent_org)
        target_branch = repo_config.branch

        if not (working_copy / ".git").exists():
            working_copy.parent.mkdir(parents=True, exist_ok=True)
            self._run_git(working_copy.parent, ["clone", clone_url, working_copy.name])
            self._configure_git_identity(working_copy)

            # Check if remote repository was empty (e.g. from 409 multi-fork fallback)
            has_commits = (
                self._run_git(
                    working_copy, ["rev-parse", "--verify", "HEAD"], check=False
                ).returncode
                == 0
            )
            if not has_commits:
                source_owner = MIRRORS_ORG_NAME
                source_repo = self.get_mirror_repo_name(repo_config.url)
                if parent_session_id:
                    parent_fork = self.get_session_fork_repo_name(
                        repo_config.url, parent_session_id
                    )
                    if self.client.get_repo(parent_fork, owner=agent_org):
                        source_owner = agent_org
                        source_repo = parent_fork
                source_url = self.client.get_authenticated_clone_url(
                    source_repo, owner=source_owner
                )
                self._run_git(working_copy, ["pull", source_url, target_branch or "main"])
                self._run_git(working_copy, ["push", "-u", "origin", target_branch or "main"])

            if start_commit:
                self._run_git(working_copy, ["checkout", "-B", target_branch, start_commit])
            else:
                try:
                    self._run_git(working_copy, ["checkout", target_branch])
                except Exception:
                    try:
                        self._run_git(
                            working_copy,
                            ["checkout", "-B", target_branch, f"origin/{target_branch}"],
                        )
                    except Exception:
                        logger.warning(
                            "Failed to checkout configured branch %s for %s",
                            target_branch,
                            mount_name,
                        )
            self._record_initial_base_commit(agent_id, session_id, repo_config, working_copy)
        else:
            self.clean_stale_locks(working_copy)
            self._configure_git_identity(working_copy)
            self._configure_git_identity(working_copy)

        return working_copy

    def _get_base_commit_file(
        self,
        agent_id: UUID,
        session_id: UUID,
        attachment_id: str,
    ) -> Path:
        return self.get_session_indexes_dir(agent_id, session_id) / f"{attachment_id}.base_commit"

    def _record_initial_base_commit(
        self,
        agent_id: UUID,
        session_id: UUID,
        repo_config: ExternalRepositoryConfig,
        working_copy: Path,
    ) -> str | None:
        """Persist the initial HEAD SHA at mount time outside the working tree."""
        head_res = self._run_git(working_copy, ["rev-parse", "HEAD"], check=False)
        if head_res.returncode != 0:
            return None
        head_sha = head_res.stdout.strip()
        if not head_sha:
            return None
        base_file = self._get_base_commit_file(agent_id, session_id, repo_config.id)
        base_file.parent.mkdir(parents=True, exist_ok=True)
        base_file.write_text(head_sha, encoding="utf-8")
        return head_sha

    def _resolve_base_commit(
        self,
        agent_id: UUID,
        session_id: UUID,
        repo_config: ExternalRepositoryConfig,
        working_copy: Path,
        head_commit: str,
    ) -> str:
        """Resolve the base commit SHA for diffing changes since initial mount."""
        base_file = self._get_base_commit_file(agent_id, session_id, repo_config.id)
        candidates: list[str] = []
        if base_file.exists():
            recorded = base_file.read_text(encoding="utf-8").strip()
            if recorded:
                candidates.append(recorded)
        candidates.extend([f"origin/{repo_config.branch}", repo_config.branch])

        for ref in candidates:
            res = self._run_git(
                working_copy, ["rev-parse", "--verify", f"{ref}^{{commit}}"], check=False
            )
            if res.returncode == 0 and res.stdout.strip():
                return res.stdout.strip()
        return head_commit

    def get_working_copy_changes(
        self,
        agent_id: UUID,
        session_id: UUID,
        repo_config: ExternalRepositoryConfig,
        mount_name: str,
    ) -> dict[str, Any] | None:
        """Return commits, branch status, and unified diff since initial mount."""
        working_copy = self.get_working_copy_path(agent_id, session_id, mount_name)
        if not (working_copy / ".git").exists():
            return None

        head_res = self._run_git(working_copy, ["rev-parse", "HEAD"], check=False)
        if head_res.returncode != 0 or not head_res.stdout.strip():
            return None
        head_commit = head_res.stdout.strip()

        branch_res = self._run_git(working_copy, ["symbolic-ref", "--short", "HEAD"], check=False)
        current_branch = (
            branch_res.stdout.strip()
            if branch_res.returncode == 0 and branch_res.stdout.strip()
            else head_commit[:8]
        )
        branch_changed = current_branch != repo_config.branch

        base_commit = self._resolve_base_commit(
            agent_id, session_id, repo_config, working_copy, head_commit
        )

        repo_name = self.get_session_fork_repo_name(repo_config.url, session_id)
        agent_org = f"agent-{agent_id.hex}"
        gitea_base: str | None = None
        if self.settings.enabled and self.settings.gitea_external_url:
            gitea_base = (
                f"{self.settings.gitea_external_url.rstrip('/')}/"
                f"{agent_org}/{repo_name}"
            )

        commits: list[dict[str, Any]] = []
        if base_commit != head_commit:
            log_res = self._run_git(
                working_copy,
                [
                    "log",
                    "--format=%H%x1f%h%x1f%s%x1f%an%x1f%aI%x1f%P%x1f%D",
                    f"{base_commit}..HEAD",
                ],
                check=False,
            )
            if log_res.returncode == 0:
                for line in log_res.stdout.splitlines():
                    parts = line.split("\x1f")
                    if len(parts) == 7:
                        sha = parts[0]
                        parents = [p for p in parts[5].split() if p]
                        refs = [r.strip() for r in parts[6].split(",") if r.strip()]
                        commits.append(
                            {
                                "sha": sha,
                                "short_sha": parts[1],
                                "message": parts[2],
                                "author": parts[3],
                                "date": parts[4],
                                "parents": parents,
                                "is_merge": len(parents) > 1,
                                "refs": refs,
                                "gitea_url": f"{gitea_base}/commit/{sha}" if gitea_base else None,
                            }
                        )

        local_branches: list[dict[str, Any]] = []
        branches_res = self._run_git(
            working_copy,
            [
                "for-each-ref",
                "--format=%(refname:short)\t%(objectname:short)\t%(HEAD)",
                "refs/heads",
            ],
            check=False,
        )
        if branches_res.returncode == 0:
            for line in branches_res.stdout.splitlines():
                parts = line.split("\t")
                if len(parts) == 3:
                    local_branches.append(
                        {
                            "name": parts[0],
                            "short_sha": parts[1],
                            "is_current": parts[2].strip() == "*",
                        }
                    )

        status_res = self._run_git(working_copy, ["status", "--porcelain"], check=False)
        uncommitted_files: list[dict[str, Any]] = []
        for line in status_res.stdout.splitlines():
            if len(line) < 4:
                continue
            xy = line[:2]
            raw_path = line[3:]
            if xy == "??":
                uncommitted_files.append(
                    {
                        "path": raw_path,
                        "status": "untracked",
                        "staged": False,
                        "unstaged": True,
                    }
                )
            else:
                staged = xy[0] != " "
                unstaged = xy[1] != " "
                code = xy[0] if staged else xy[1]
                status_map = {
                    "M": "modified",
                    "A": "added",
                    "D": "deleted",
                    "R": "renamed",
                    "C": "copied",
                    "U": "unmerged",
                }
                uncommitted_files.append(
                    {
                        "path": raw_path,
                        "status": status_map.get(code, "modified"),
                        "staged": staged,
                        "unstaged": unstaged,
                    }
                )
        has_uncommitted_changes = len(uncommitted_files) > 0

        indexes_dir = self.get_session_indexes_dir(agent_id, session_id)
        indexes_dir.mkdir(parents=True, exist_ok=True)
        alt_index = indexes_dir / f"{repo_config.id}.diff.idx"
        env = {"GIT_INDEX_FILE": str(alt_index.resolve())}
        self._run_git(working_copy, ["read-tree", head_commit], env=env)
        self._run_git(working_copy, ["add", "-A", "--", "."], env=env)
        diff_res = self._run_git(
            working_copy,
            ["diff", "--cached", "--no-color", base_commit],
            env=env,
            check=False,
        )
        diff_text = diff_res.stdout if diff_res.returncode in (0, 1) else ""

        return {
            "attachment_id": repo_config.id,
            "mount_name": mount_name,
            "mount_path": f"/projects/{mount_name}",
            "url": repo_config.url,
            "configured_branch": repo_config.branch,
            "current_branch": current_branch,
            "branch_changed": branch_changed,
            "base_commit": base_commit,
            "head_commit": head_commit,
            "commits": commits,
            "local_branches": local_branches,
            "uncommitted_files": uncommitted_files,
            "diff": diff_text,
            "has_uncommitted_changes": has_uncommitted_changes,
            "gitea_repo_url": gitea_base,
            "gitea_semantic_branch_url": (
                f"{gitea_base}/src/branch/seamus/semantic/{session_id}/{mount_name}"
                if gitea_base
                else None
            ),
            "gitea_checkpoint_branch_url": (
                f"{gitea_base}/src/branch/seamus/checkpoints/{session_id}/{mount_name}"
                if gitea_base
                else None
            ),
            "gitea_compare_url": (
                f"{gitea_base}/compare/{base_commit}...{head_commit}"
                if gitea_base and base_commit != head_commit
                else None
            ),
        }

    def checkpoint_working_copy(
        self,
        agent_id: UUID,
        session_id: UUID,
        repo_config: ExternalRepositoryConfig,
        mount_name: str,
        checkpoint_id: str,
        prev_record: MountedRepositoryCheckpointRecord | None = None,
    ) -> MountedRepositoryCheckpointRecord:
        """Capture a dual-index snapshot of the working tree without mutating the agent's index."""
        working_copy = self.get_working_copy_path(agent_id, session_id, mount_name)
        if not (working_copy / ".git").exists():
            raise FileNotFoundError(f"Repository working copy not found at {working_copy}")

        self.clean_stale_locks(working_copy)

        canonical_url = canonicalize_git_url(repo_config.url)
        project_id = derive_project_id(canonical_url)

        # 1. Capture the ordinary index state (staged files)
        staged_tree_res = self._run_git(working_copy, ["write-tree"])
        staged_tree = staged_tree_res.stdout.strip()

        # 2. Capture semantic HEAD and active branch
        head_res = self._run_git(working_copy, ["rev-parse", "HEAD"])
        semantic_head = head_res.stdout.strip()

        branch_res = self._run_git(working_copy, ["symbolic-ref", "--short", "HEAD"], check=False)
        semantic_branch = branch_res.stdout.strip() if branch_res.returncode == 0 else semantic_head

        # 3. Capture working tree contents into alternate index
        indexes_dir = self.get_session_indexes_dir(agent_id, session_id)
        indexes_dir.mkdir(parents=True, exist_ok=True)
        alt_index = indexes_dir / f"{repo_config.id}.idx"

        env = {"GIT_INDEX_FILE": str(alt_index.resolve())}
        # Initialize alternate index from semantic HEAD
        self._run_git(working_copy, ["read-tree", semantic_head], env=env)
        # Stage all working-tree changes (respecting .gitignore natively)
        self._run_git(working_copy, ["add", "-A", "--", "."], env=env)
        # Write the full working tree snapshot
        snapshot_tree_res = self._run_git(working_copy, ["write-tree"], env=env)
        snapshot_tree = snapshot_tree_res.stdout.strip()

        # 4. Check for idempotency against previous record
        if (
            prev_record is not None
            and prev_record.snapshot_tree == snapshot_tree
            and prev_record.staged_tree == staged_tree
            and prev_record.semantic_head == semantic_head
        ):
            return prev_record

        # 5. Create a snapshot commit with separate ancestry
        prev_parent: list[str] = []
        if prev_record and prev_record.checkpoint_sha:
            prev_parent = ["-p", prev_record.checkpoint_sha]

        commit_msg = (
            f"checkpoint: [session={session_id} attachment={repo_config.id} "
            f"checkpoint={checkpoint_id} head={semantic_head}]"
        )
        cp_commit_res = self._run_git(
            working_copy,
            ["commit-tree", snapshot_tree, *prev_parent, "-m", commit_msg],
        )
        checkpoint_sha = cp_commit_res.stdout.strip()

        # 6. Push checkpoint commit and session branch to durable Gitea storage
        repo_name = self.get_session_fork_repo_name(repo_config.url, session_id)
        agent_org = f"agent-{agent_id.hex}"
        gitea_url: str | None = None
        if self.settings.enabled:
            gitea_url = (
                f"{self.settings.gitea_url.rstrip('/')}/"
                f"{agent_org}/{repo_name}"
            )
            ref_spec = (
                f"{checkpoint_sha}:refs/seamus/sessions/{session_id}/"
                f"attachments/{repo_config.id}/checkpoints/{checkpoint_id}"
            )
            latest_ref = f"+{checkpoint_sha}:refs/seamus/snapshots/{session_id}/{repo_config.id}"
            # Also push as a visible branch in Gitea so users can inspect it in the Gitea UI
            branch_ref = (
                f"+{checkpoint_sha}:refs/heads/seamus/checkpoints/{session_id}/{mount_name}"
            )
            try:
                push_refs = [ref_spec, latest_ref, branch_ref]
                if semantic_head:
                    push_refs.append(
                        f"+{semantic_head}:refs/heads/seamus/semantic/{session_id}/{mount_name}"
                    )
                self._run_git(working_copy, ["push", "origin", *push_refs])
            except Exception:
                logger.exception("Failed to push checkpoint ref to Gitea for %s", mount_name)
                raise

        return MountedRepositoryCheckpointRecord(
            project_id=project_id,
            attachment_id=repo_config.id,
            mount_name=mount_name,
            url=repo_config.url,
            branch=repo_config.branch,
            checkpoint_sha=checkpoint_sha,
            snapshot_tree=snapshot_tree,
            semantic_head=semantic_head,
            semantic_branch=semantic_branch,
            staged_tree=staged_tree,
            gitea_repo_name=repo_name,
            gitea_repo_url=gitea_url,
        )

    def restore_working_copy_checkpoint(
        self,
        agent_id: UUID,
        session_id: UUID,
        record: MountedRepositoryCheckpointRecord,
    ) -> Path:
        """Restore working copy to exact historical state: semantic HEAD, index, and files."""
        working_copy = self.get_working_copy_path(agent_id, session_id, record.mount_name)
        if not (working_copy / ".git").exists():
            repo_config = ExternalRepositoryConfig(
                id=record.attachment_id,
                url=record.url,
                branch=record.branch,
            )
            self.provision_session_working_copy(
                agent_id,
                session_id,
                repo_config,
                record.mount_name,
                start_commit=record.semantic_head,
            )

        # Fetch custom checkpoint refs if on Gitea
        if self.settings.enabled:
            try:
                self._run_git(working_copy, ["fetch", "origin", "refs/seamus/*:refs/seamus/*"])
            except Exception:
                logger.debug("Failed to fetch refs/seamus/* for %s", record.mount_name)

        # 1. Checkout the semantic HEAD and branch
        self._run_git(
            working_copy, ["checkout", "-B", record.semantic_branch, record.semantic_head]
        )

        # 2. Extract snapshot tree files to working copy without altering git index
        archive_res = subprocess.run(
            ["git", "archive", record.snapshot_tree],
            cwd=working_copy,
            check=True,
            capture_output=True,
        )
        with tarfile.open(fileobj=BytesIO(archive_res.stdout)) as tar:
            tar.extractall(path=working_copy, filter="data")

        # 3. Restore the ordinary index from staged_tree
        self._run_git(working_copy, ["read-tree", record.staged_tree])

        return working_copy

    def unmount_working_copy(
        self,
        agent_id: UUID,
        session_id: UUID,
        mount_name: str,
    ) -> None:
        """Clean up local working tree on unmount. Uncommitted changes are permanently discarded."""
        working_copy = self.get_working_copy_path(agent_id, session_id, mount_name)
        if working_copy.exists():
            try:
                shutil.rmtree(working_copy, ignore_errors=True)
                logger.info("Unmounted and removed working copy for %s", mount_name)
            except Exception:
                logger.exception("Failed to remove working copy directory %s", working_copy)


_GLOBAL_EXTERNAL_REPO_MANAGER: ExternalRepositoryManager | None = None


def get_external_repo_manager() -> ExternalRepositoryManager:
    """Return the global singleton ExternalRepositoryManager instance."""
    global _GLOBAL_EXTERNAL_REPO_MANAGER
    if _GLOBAL_EXTERNAL_REPO_MANAGER is None:
        from seamus.persistence.workspace import get_workspace_manager

        ws_mgr = get_workspace_manager()
        _GLOBAL_EXTERNAL_REPO_MANAGER = ExternalRepositoryManager(
            workspace_root=ws_mgr.workspace_root,
            settings=ws_mgr.settings,
            client=ws_mgr.client,
        )
    return _GLOBAL_EXTERNAL_REPO_MANAGER


def reset_external_repo_manager(
    manager: ExternalRepositoryManager | None = None,
) -> ExternalRepositoryManager:
    """Reset the global singleton instance (useful in tests)."""
    global _GLOBAL_EXTERNAL_REPO_MANAGER
    _GLOBAL_EXTERNAL_REPO_MANAGER = manager
    return get_external_repo_manager()
