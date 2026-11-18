"""Gitea REST API client for repository and branch management."""

import logging
from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx

from seamus.persistence.config import PersistenceSettings, get_persistence_settings

logger = logging.getLogger(__name__)


class GiteaAPIError(RuntimeError):
    """Raised when an operation against the Gitea REST API fails."""


class GiteaClient:
    """Client for interacting with Gitea's v1 REST API."""

    def __init__(self, settings: PersistenceSettings | None = None) -> None:
        self.settings = settings or get_persistence_settings()
        self.base_url = self.settings.gitea_url.rstrip("/")
        self.auth = (self.settings.gitea_admin_user, self.settings.gitea_admin_password)

    def is_healthy(self) -> bool:
        """Probe Gitea service version endpoint to check connectivity."""
        if not self.settings.enabled:
            return False
        try:
            with httpx.Client(timeout=3.0) as client:
                res = client.get(f"{self.base_url}/api/v1/version")
                return res.status_code == 200
        except Exception:
            return False

    def ensure_admin_user(self) -> bool:
        """Verify that the configured service user exists and can authenticate."""
        if not self.settings.enabled:
            return False
        try:
            with httpx.Client(timeout=5.0, auth=self.auth) as client:
                res = client.get(f"{self.base_url}/api/v1/user")
                return res.status_code == 200
        except Exception:
            logger.exception(
                "Failed to authenticate with Gitea as %s", self.settings.gitea_admin_user
            )
            return False

    def get_or_create_repo(
        self,
        repo_name: str,
        description: str = "",
        private: bool = False,
        owner: str | None = None,
    ) -> dict[str, Any]:
        """Fetch repository details, or create a new public/private repository if not found."""
        repo_owner = owner or self.settings.gitea_admin_user
        with httpx.Client(timeout=10.0, auth=self.auth) as client:
            # Check if repository already exists
            get_res = client.get(f"{self.base_url}/api/v1/repos/{repo_owner}/{repo_name}")
            if get_res.status_code == 200:
                data = get_res.json()
                if isinstance(data, dict):
                    # Ensure public visibility and manual merge capability
                    patch_payload: dict[str, Any] = {}
                    if not private and data.get("private") is True:
                        patch_payload["private"] = False
                    if not data.get("allow_manual_merge") or not data.get(
                        "autodetect_manual_merge"
                    ):
                        patch_payload["allow_manual_merge"] = True
                        patch_payload["autodetect_manual_merge"] = True

                    if patch_payload:
                        try:
                            patch_res = client.patch(
                                f"{self.base_url}/api/v1/repos/{repo_owner}/{repo_name}",
                                json=patch_payload,
                            )
                            if patch_res.status_code == 200:
                                updated = patch_res.json()
                                if isinstance(updated, dict):
                                    return updated
                        except Exception:
                            logger.exception("Failed to update repository %s settings", repo_name)
                    return data
                return {}

            if get_res.status_code == 404:
                # Create repository under user or organization
                create_payload = {
                    "name": repo_name,
                    "description": description,
                    "private": private,
                    "auto_init": False,
                    "default_branch": "main",
                }
                if repo_owner == self.settings.gitea_admin_user:
                    create_url = f"{self.base_url}/api/v1/user/repos"
                else:
                    create_url = f"{self.base_url}/api/v1/orgs/{repo_owner}/repos"

                create_res = client.post(create_url, json=create_payload)
                if create_res.status_code in (200, 201):
                    data = create_res.json()
                    # Configure manual merge permissions on newly created repository
                    try:
                        client.patch(
                            f"{self.base_url}/api/v1/repos/{repo_owner}/{repo_name}",
                            json={
                                "allow_manual_merge": True,
                                "autodetect_manual_merge": True,
                            },
                        )
                    except Exception:
                        logger.exception(
                            "Failed to configure merge policy for repository %s", repo_name
                        )
                    if isinstance(data, dict):
                        return data
                    return {}

                msg = (
                    f"Failed to create Gitea repository '{repo_name}' for owner '{repo_owner}': "
                    f"status={create_res.status_code} body={create_res.text}"
                )
                raise GiteaAPIError(msg)

            msg = (
                f"Error retrieving repository '{repo_name}' from Gitea: "
                f"status={get_res.status_code} body={get_res.text}"
            )
            raise GiteaAPIError(msg)

    def get_or_create_org(
        self,
        org_name: str,
        full_name: str = "",
        description: str = "",
        visibility: str = "public",
    ) -> dict[str, Any]:
        """Fetch organization details, or create a new organization if not found."""
        with httpx.Client(timeout=10.0, auth=self.auth) as client:
            get_res = client.get(f"{self.base_url}/api/v1/orgs/{org_name}")
            if get_res.status_code == 200:
                data = get_res.json()
                return data if isinstance(data, dict) else {}

            if get_res.status_code == 404:
                create_payload = {
                    "username": org_name,
                    "full_name": full_name,
                    "description": description,
                    "visibility": visibility,
                }
                create_res = client.post(f"{self.base_url}/api/v1/orgs", json=create_payload)
                if create_res.status_code in (200, 201):
                    data = create_res.json()
                    return data if isinstance(data, dict) else {}
                msg = (
                    f"Failed to create Gitea organization '{org_name}': "
                    f"status={create_res.status_code} body={create_res.text}"
                )
                raise GiteaAPIError(msg)

            msg = (
                f"Error retrieving organization '{org_name}' from Gitea: "
                f"status={get_res.status_code} body={get_res.text}"
            )
            raise GiteaAPIError(msg)

    def get_org(self, org_name: str) -> dict[str, Any] | None:
        """Retrieve details of an organization, returning None if not found."""
        with httpx.Client(timeout=10.0, auth=self.auth) as client:
            res = client.get(f"{self.base_url}/api/v1/orgs/{org_name}")
            if res.status_code == 200:
                data = res.json()
                return data if isinstance(data, dict) else None
            if res.status_code == 404:
                return None
            msg = (
                f"Failed to get organization '{org_name}': status={res.status_code} body={res.text}"
            )
            raise GiteaAPIError(msg)

    def list_orgs(self) -> list[dict[str, Any]]:
        """List all organizations visible to the authenticated user."""
        with httpx.Client(timeout=10.0, auth=self.auth) as client:
            res = client.get(f"{self.base_url}/api/v1/orgs")
            if res.status_code == 200:
                data = res.json()
                if isinstance(data, list):
                    return [o for o in data if isinstance(o, dict)]
                return []
            msg = f"Failed to list organizations: status={res.status_code} body={res.text}"
            raise GiteaAPIError(msg)

    def list_org_repos(self, org_name: str) -> list[dict[str, Any]]:
        """List all repositories belonging to the specified organization."""
        with httpx.Client(timeout=10.0, auth=self.auth) as client:
            res = client.get(f"{self.base_url}/api/v1/orgs/{org_name}/repos")
            if res.status_code == 200:
                data = res.json()
                if isinstance(data, list):
                    return [r for r in data if isinstance(r, dict)]
                return []
            if res.status_code == 404:
                return []
            msg = (
                f"Failed to list repos for organization '{org_name}': "
                f"status={res.status_code} body={res.text}"
            )
            raise GiteaAPIError(msg)

    def delete_org(self, org_name: str) -> bool:
        """Delete an organization (used in agent hard delete and test cleanup)."""
        with httpx.Client(timeout=10.0, auth=self.auth) as client:
            res = client.delete(f"{self.base_url}/api/v1/orgs/{org_name}")
            return res.status_code in (200, 204, 404)

    def rename_org(self, org_name: str, new_name: str) -> bool:
        """Rename an organization (e.g. prefixing with archived-)."""
        payload = {"new_name": new_name}
        with httpx.Client(timeout=10.0, auth=self.auth) as client:
            res = client.post(f"{self.base_url}/api/v1/orgs/{org_name}/rename", json=payload)
            if res.status_code in (200, 204):
                return True
            msg = (
                f"Failed to rename organization '{org_name}' to '{new_name}': "
                f"status={res.status_code} body={res.text}"
            )
            raise GiteaAPIError(msg)

    def migrate_repo_as_mirror(
        self,
        clone_addr: str,
        repo_name: str,
        repo_owner: str = "mirrors",
        mirror_interval: str = "10m",
        auth_token: str | None = None,
        auth_username: str | None = None,
        auth_password: str | None = None,
        private: bool = True,
    ) -> dict[str, Any]:
        """Migrate a remote repository as a read-only pull mirror into an organization."""
        payload: dict[str, Any] = {
            "clone_addr": clone_addr,
            "repo_name": repo_name,
            "repo_owner": repo_owner,
            "mirror": True,
            "mirror_interval": mirror_interval,
            "private": private,
            "service": "git",
        }
        if auth_token:
            payload["auth_token"] = auth_token
        elif auth_username and auth_password:
            payload["auth_username"] = auth_username
            payload["auth_password"] = auth_password

        with httpx.Client(timeout=60.0, auth=self.auth) as client:
            res = client.post(f"{self.base_url}/api/v1/repos/migrate", json=payload)
            if res.status_code in (200, 201):
                data = res.json()
                return data if isinstance(data, dict) else {}
            msg = (
                f"Failed to migrate mirror '{repo_name}' for owner '{repo_owner}' "
                f"from {clone_addr}: status={res.status_code} body={res.text}"
            )
            raise GiteaAPIError(msg)

    def fork_repo(
        self,
        source_owner: str,
        source_repo: str,
        target_org: str,
        fork_name: str,
    ) -> dict[str, Any]:
        """Fork a repository into a target organization."""
        payload = {
            "organization": target_org,
            "name": fork_name,
        }
        with httpx.Client(timeout=30.0, auth=self.auth) as client:
            res = client.post(
                f"{self.base_url}/api/v1/repos/{source_owner}/{source_repo}/forks",
                json=payload,
            )
            if res.status_code in (200, 201, 202):
                data = res.json()
                return data if isinstance(data, dict) else {}
            if res.status_code == 409 and fork_name:
                # Gitea limitation: a user/org cannot have multiple native forks of the same repo.
                # Fallback to creating a new repository within the target organization.
                logger.info(
                    "Repository '%s/%s' is already forked in '%s'; creating repo '%s'",
                    source_owner,
                    source_repo,
                    target_org,
                    fork_name,
                )
                return self.get_or_create_repo(repo_name=fork_name, owner=target_org)
            msg = (
                f"Failed to fork repository '{source_owner}/{source_repo}' to "
                f"'{target_org}/{fork_name}': status={res.status_code} body={res.text}"
            )
            raise GiteaAPIError(msg)

    def get_repo(self, repo_name: str, owner: str | None = None) -> dict[str, Any] | None:
        """Retrieve repository details, returning None if not found."""
        repo_owner = owner or self.settings.gitea_admin_user
        with httpx.Client(timeout=10.0, auth=self.auth) as client:
            res = client.get(f"{self.base_url}/api/v1/repos/{repo_owner}/{repo_name}")
            if res.status_code == 200:
                data = res.json()
                return data if isinstance(data, dict) else None
            if res.status_code == 404:
                return None
            msg = (
                f"Failed to get repo '{repo_owner}/{repo_name}': "
                f"status={res.status_code} body={res.text}"
            )
            raise GiteaAPIError(msg)

    def list_user_repos(self) -> list[dict[str, Any]]:
        """List all repositories owned by the service user."""
        with httpx.Client(timeout=10.0, auth=self.auth) as client:
            res = client.get(f"{self.base_url}/api/v1/user/repos")
            if res.status_code == 200:
                data = res.json()
                if isinstance(data, list):
                    return [r for r in data if isinstance(r, dict)]
                return []
            msg = f"Failed to list Gitea repositories: status={res.status_code} body={res.text}"
            raise GiteaAPIError(msg)

    def list_branches(self, repo_name: str, owner: str | None = None) -> list[str]:
        """List all branch names for a repository."""
        repo_owner = owner or self.settings.gitea_admin_user
        with httpx.Client(timeout=10.0, auth=self.auth) as client:
            res = client.get(f"{self.base_url}/api/v1/repos/{repo_owner}/{repo_name}/branches")
            if res.status_code == 200:
                data = res.json()
                if isinstance(data, list):
                    return [
                        b["name"]
                        for b in data
                        if isinstance(b, dict) and "name" in b and isinstance(b["name"], str)
                    ]
                return []
            if res.status_code == 404:
                return []
            msg = (
                f"Failed to list branches for repo '{repo_owner}/{repo_name}': "
                f"status={res.status_code}"
            )
            raise GiteaAPIError(msg)

    def get_file_content(
        self,
        repo_name: str,
        branch: str,
        file_path: str,
        owner: str | None = None,
    ) -> str | None:
        """Fetch raw file content from a branch, returning None if not found."""
        repo_owner = owner or self.settings.gitea_admin_user
        clean_path = file_path.lstrip("/")
        with httpx.Client(timeout=10.0, auth=self.auth) as client:
            res = client.get(
                f"{self.base_url}/api/v1/repos/{repo_owner}/{repo_name}/raw/{branch}/{clean_path}"
            )
            if res.status_code == 200:
                return res.text
            if res.status_code == 404:
                return None
            msg = (
                f"Failed to fetch file '{file_path}' from repo '{repo_owner}/{repo_name}' "
                f"branch '{branch}': status={res.status_code}"
            )
            raise GiteaAPIError(msg)

    def delete_repo(self, repo_name: str, owner: str | None = None) -> bool:
        """Delete a repository (used primarily in test cleanup and hard delete)."""
        repo_owner = owner or self.settings.gitea_admin_user
        with httpx.Client(timeout=10.0, auth=self.auth) as client:
            res = client.delete(f"{self.base_url}/api/v1/repos/{repo_owner}/{repo_name}")
            return res.status_code in (200, 204, 404)

    def archive_repo(self, repo_name: str, owner: str | None = None) -> bool:
        """Mark a repository as archived via Gitea Danger Zone settings."""
        repo_owner = owner or self.settings.gitea_admin_user
        payload = {"archived": True}
        with httpx.Client(timeout=10.0, auth=self.auth) as client:
            res = client.patch(
                f"{self.base_url}/api/v1/repos/{repo_owner}/{repo_name}",
                json=payload,
            )
            if res.status_code == 200:
                return True
            if res.status_code == 404:
                return False
            msg = (
                f"Failed to archive repository '{repo_owner}/{repo_name}': "
                f"status={res.status_code} body={res.text}"
            )
            raise GiteaAPIError(msg)

    def create_pull_request(
        self,
        repo_name: str,
        title: str,
        head: str,
        base: str = "main",
        body: str = "",
        owner: str | None = None,
    ) -> dict[str, Any]:
        """Create a new pull request in the repository (supports cross-fork head)."""
        repo_owner = owner or self.settings.gitea_admin_user
        payload = {
            "title": title,
            "head": head,
            "base": base,
            "body": body,
        }
        with httpx.Client(timeout=10.0, auth=self.auth) as client:
            res = client.post(
                f"{self.base_url}/api/v1/repos/{repo_owner}/{repo_name}/pulls",
                json=payload,
            )
            if res.status_code in (200, 201):
                data = res.json()
                if isinstance(data, dict):
                    return data
                return {}
            msg = (
                f"Failed to create pull request for '{repo_owner}/{repo_name}' ({head} -> {base}): "
                f"status={res.status_code} body={res.text}"
            )
            raise GiteaAPIError(msg)

    def get_pull_request(
        self,
        repo_name: str,
        index: int,
        owner: str | None = None,
    ) -> dict[str, Any]:
        """Retrieve details of a pull request by index."""
        repo_owner = owner or self.settings.gitea_admin_user
        with httpx.Client(timeout=10.0, auth=self.auth) as client:
            res = client.get(f"{self.base_url}/api/v1/repos/{repo_owner}/{repo_name}/pulls/{index}")
            if res.status_code == 200:
                data = res.json()
                if isinstance(data, dict):
                    return data
                return {}
            msg = (
                f"Failed to get pull request #{index} for '{repo_owner}/{repo_name}': "
                f"status={res.status_code} body={res.text}"
            )
            raise GiteaAPIError(msg)

    def list_pull_requests(
        self,
        repo_name: str,
        state: str = "open",
        owner: str | None = None,
    ) -> list[dict[str, Any]]:
        """List pull requests in the repository matching state ('open', 'closed', 'all')."""
        repo_owner = owner or self.settings.gitea_admin_user
        with httpx.Client(timeout=10.0, auth=self.auth) as client:
            res = client.get(
                f"{self.base_url}/api/v1/repos/{repo_owner}/{repo_name}/pulls",
                params={"state": state},
            )
            if res.status_code == 200:
                data = res.json()
                if isinstance(data, list):
                    return [p for p in data if isinstance(p, dict)]
                return []
            msg = (
                f"Failed to list pull requests for '{repo_owner}/{repo_name}': "
                f"status={res.status_code} body={res.text}"
            )
            raise GiteaAPIError(msg)

    def approve_pull_request(
        self,
        repo_name: str,
        index: int,
        body: str = "Accepted by user",
        owner: str | None = None,
    ) -> dict[str, Any] | None:
        """Submit an approval review on a pull request. Returns None if self-approval rejected."""
        repo_owner = owner or self.settings.gitea_admin_user
        payload = {
            "event": "APPROVED",
            "body": body,
        }
        with httpx.Client(timeout=10.0, auth=self.auth) as client:
            res = client.post(
                f"{self.base_url}/api/v1/repos/{repo_owner}/{repo_name}/pulls/{index}/reviews",
                json=payload,
            )
            if res.status_code in (200, 201):
                data = res.json()
                if isinstance(data, dict):
                    return data
                return {}
            if res.status_code == 422:
                logger.debug(
                    "Self-approval rejected on PR #%d for '%s/%s': %s",
                    index,
                    repo_owner,
                    repo_name,
                    res.text,
                )
                return None
            msg = (
                f"Failed to approve pull request #{index} for '{repo_owner}/{repo_name}': "
                f"status={res.status_code} body={res.text}"
            )
            raise GiteaAPIError(msg)

    def merge_pull_request(
        self,
        repo_name: str,
        index: int,
        do: str = "merge",
        delete_branch: bool = False,
        merge_commit_id: str | None = None,
        owner: str | None = None,
    ) -> bool:
        """Merge a pull request."""
        repo_owner = owner or self.settings.gitea_admin_user
        payload: dict[str, Any] = {
            "Do": do,
            "delete_branch_after_merge": delete_branch,
        }
        if merge_commit_id is not None:
            payload["merge_commit_id"] = merge_commit_id
        with httpx.Client(timeout=10.0, auth=self.auth) as client:
            res = client.post(
                f"{self.base_url}/api/v1/repos/{repo_owner}/{repo_name}/pulls/{index}/merge",
                json=payload,
            )
            if res.status_code in (200, 204):
                return True
            msg = (
                f"Failed to merge pull request #{index} for '{repo_owner}/{repo_name}': "
                f"status={res.status_code} body={res.text}"
            )
            raise GiteaAPIError(msg)

    def close_pull_request(
        self,
        repo_name: str,
        index: int,
        owner: str | None = None,
    ) -> bool:
        """Close an open pull request without merging."""
        repo_owner = owner or self.settings.gitea_admin_user
        payload = {"state": "closed"}
        with httpx.Client(timeout=10.0, auth=self.auth) as client:
            res = client.patch(
                f"{self.base_url}/api/v1/repos/{repo_owner}/{repo_name}/pulls/{index}",
                json=payload,
            )
            return res.status_code == 200

    def get_pull_request_diff(
        self,
        repo_name: str,
        index: int,
        owner: str | None = None,
    ) -> str:
        """Retrieve raw unified diff for a pull request by index."""
        repo_owner = owner or self.settings.gitea_admin_user
        with httpx.Client(timeout=10.0, auth=self.auth) as client:
            res = client.get(
                f"{self.base_url}/api/v1/repos/{repo_owner}/{repo_name}/pulls/{index}.diff"
            )
            if res.status_code == 200:
                return res.text
            if res.status_code == 404:
                return ""
            msg = (
                f"Failed to get pull request diff #{index} for '{repo_owner}/{repo_name}': "
                f"status={res.status_code} body={res.text}"
            )
            raise GiteaAPIError(msg)

    def get_authenticated_clone_url(self, repo_name: str, owner: str | None = None) -> str:
        """Construct authenticated git clone URL with credentials embedded."""
        parsed = urlparse(self.base_url)
        user = self.settings.gitea_admin_user
        password = self.settings.gitea_admin_password
        repo_owner = owner or user
        netloc = f"{user}:{password}@{parsed.netloc}"
        path = f"/{repo_owner}/{repo_name}.git"
        return urlunparse((parsed.scheme, netloc, path, "", "", ""))
