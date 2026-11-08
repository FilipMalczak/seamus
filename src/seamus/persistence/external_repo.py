"""External Git repository manager, dual-index snapshot engine, and Gitea backing."""

from __future__ import annotations

import hashlib
import logging
import os
import re
import shutil
import subprocess
import tarfile
from collections import Counter, defaultdict
from collections.abc import Sequence
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING
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


def derive_project_id(canonical_url: str) -> str:
    """Derive a deterministic 12-character project identifier from a canonical Git URL."""
    norm = canonicalize_git_url(canonical_url)
    digest = hashlib.sha256(norm.encode("utf-8")).hexdigest()[:12]
    return f"proj-{digest}"


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

    def _run_git(
        self,
        cwd: Path,
        args: list[str],
        env: dict[str, str] | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        full_env = os.environ.copy()
        if env:
            full_env.update(env)
        # Prevent prompt hangs
        full_env["GIT_TERMINAL_PROMPT"] = "0"
        return subprocess.run(
            ["git", *args],
            cwd=cwd,
            env=full_env,
            check=check,
            capture_output=True,
            text=True,
        )

    def _configure_git_identity(self, repo_dir: Path) -> None:
        self._run_git(repo_dir, ["config", "user.name", "Seamus Agent"])
        self._run_git(repo_dir, ["config", "user.email", "agent@seamus.local"])
        self._run_git(repo_dir, ["config", "safe.directory", "*"])

    def get_project_repo_name(self, project_id: str) -> str:
        """Return the Gitea repository name for an external project."""
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

    def ensure_project_repo_in_gitea(
        self,
        repo_config: ExternalRepositoryConfig,
    ) -> str:
        """Ensure Gitea mirror repository exists and is populated from upstream."""
        canonical_url = canonicalize_git_url(repo_config.url)
        project_id = derive_project_id(canonical_url)
        repo_name = self.get_project_repo_name(project_id)

        if not self.settings.enabled:
            return project_id

        # 1. Check or create repo in Gitea
        self.client.get_or_create_repo(
            repo_name=repo_name,
            private=True,
        )

        # 2. Check if the configured branch already exists in Gitea
        existing_branches = self.client.list_branches(repo_name)
        if repo_config.branch in existing_branches or "main" in existing_branches:
            return project_id

        # 3. Seed repository from upstream into Gitea
        logger.info(
            "Mirroring upstream external repository %s (branch %s) into Gitea repo %s",
            repo_config.url,
            repo_config.branch,
            repo_name,
        )
        self._mirror_upstream_to_gitea(repo_config, repo_name)
        return project_id

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

            gitea_url = self.client.get_authenticated_clone_url(gitea_repo_name)
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
    ) -> Path:
        """Create or checkout a session working copy for a mounted repository."""
        project_id = self.ensure_project_repo_in_gitea(repo_config)
        working_copy = self.get_working_copy_path(agent_id, session_id, mount_name)
        session_branch = f"session/{session_id}"

        if not self.settings.enabled:
            # Local offline fallback
            working_copy.mkdir(parents=True, exist_ok=True)
            if not (working_copy / ".git").exists():
                self._run_git(working_copy, ["init", "-b", repo_config.branch])
                self._configure_git_identity(working_copy)
                (working_copy / "README.md").write_text(f"# {mount_name}\n", encoding="utf-8")
                self._run_git(working_copy, ["add", "README.md"])
                self._run_git(working_copy, ["commit", "-m", "Initial commit"])
            return working_copy

        repo_name = self.get_project_repo_name(project_id)
        clone_url = self.client.get_authenticated_clone_url(repo_name)

        if not (working_copy / ".git").exists():
            working_copy.parent.mkdir(parents=True, exist_ok=True)
            self._run_git(working_copy.parent, ["clone", clone_url, working_copy.name])
            self._configure_git_identity(working_copy)

            # Check if session branch exists on remote
            remote_branches = self.client.list_branches(repo_name)
            if session_branch in remote_branches and not start_commit:
                self._run_git(working_copy, ["checkout", session_branch])
            else:
                target_start = start_commit or f"origin/{repo_config.branch}"
                try:
                    self._run_git(working_copy, ["checkout", "-b", session_branch, target_start])
                except Exception:
                    # Fallback to origin/main or HEAD if configured branch wasn't found
                    self._run_git(working_copy, ["checkout", "-b", session_branch, "origin/main"])
                try:
                    self._run_git(working_copy, ["push", "-u", "origin", session_branch])
                except Exception:
                    logger.debug(
                        "Failed to push initial session branch %s to Gitea", session_branch
                    )
        else:
            self._configure_git_identity(working_copy)
            try:
                self._run_git(
                    working_copy, ["pull", "--rebase", "--autostash", "origin", session_branch]
                )
            except Exception:
                logger.debug(
                    "Failed to pull session branch for %s; continuing with local state",
                    mount_name,
                )

        return working_copy

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
        repo_name = self.get_project_repo_name(project_id)
        gitea_url: str | None = None
        if self.settings.enabled:
            gitea_url = (
                f"{self.settings.gitea_url.rstrip('/')}/"
                f"{self.settings.gitea_admin_user}/{repo_name}"
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
                self._run_git(working_copy, ["push", "origin", ref_spec, latest_ref, branch_ref])
                # If the agent made semantic commits, also push the session branch
                if semantic_branch.startswith("session/"):
                    self._run_git(working_copy, ["push", "origin", semantic_branch], check=False)
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
