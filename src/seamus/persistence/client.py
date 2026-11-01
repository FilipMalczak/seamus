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
    ) -> dict[str, Any]:
        """Fetch repository details, or create a new public repository if not found."""
        owner = self.settings.gitea_admin_user
        with httpx.Client(timeout=10.0, auth=self.auth) as client:
            # Check if repository already exists
            get_res = client.get(f"{self.base_url}/api/v1/repos/{owner}/{repo_name}")
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
                                f"{self.base_url}/api/v1/repos/{owner}/{repo_name}",
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
                # Create repository
                create_payload = {
                    "name": repo_name,
                    "description": description,
                    "private": private,
                    "auto_init": False,
                    "default_branch": "main",
                }
                create_res = client.post(
                    f"{self.base_url}/api/v1/user/repos",
                    json=create_payload,
                )
                if create_res.status_code in (200, 201):
                    data = create_res.json()
                    # Configure manual merge permissions on newly created repository
                    try:
                        client.patch(
                            f"{self.base_url}/api/v1/repos/{owner}/{repo_name}",
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
                    f"Failed to create Gitea repository '{repo_name}': "
                    f"status={create_res.status_code} body={create_res.text}"
                )
                raise GiteaAPIError(msg)

            msg = (
                f"Error retrieving repository '{repo_name}' from Gitea: "
                f"status={get_res.status_code} body={get_res.text}"
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

    def list_branches(self, repo_name: str) -> list[str]:
        """List all branch names for a repository."""
        owner = self.settings.gitea_admin_user
        with httpx.Client(timeout=10.0, auth=self.auth) as client:
            res = client.get(f"{self.base_url}/api/v1/repos/{owner}/{repo_name}/branches")
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
            msg = f"Failed to list branches for repo '{repo_name}': status={res.status_code}"
            raise GiteaAPIError(msg)

    def get_file_content(self, repo_name: str, branch: str, file_path: str) -> str | None:
        """Fetch raw file content from a branch, returning None if not found."""
        owner = self.settings.gitea_admin_user
        clean_path = file_path.lstrip("/")
        with httpx.Client(timeout=10.0, auth=self.auth) as client:
            res = client.get(
                f"{self.base_url}/api/v1/repos/{owner}/{repo_name}/raw/{branch}/{clean_path}"
            )
            if res.status_code == 200:
                return res.text
            if res.status_code == 404:
                return None
            msg = (
                f"Failed to fetch file '{file_path}' from repo '{repo_name}' "
                f"branch '{branch}': status={res.status_code}"
            )
            raise GiteaAPIError(msg)

    def delete_repo(self, repo_name: str) -> bool:
        """Delete a repository (used primarily in test cleanup)."""
        owner = self.settings.gitea_admin_user
        with httpx.Client(timeout=10.0, auth=self.auth) as client:
            res = client.delete(f"{self.base_url}/api/v1/repos/{owner}/{repo_name}")
            return res.status_code in (200, 204)

    def create_pull_request(
        self,
        repo_name: str,
        title: str,
        head: str,
        base: str = "main",
        body: str = "",
    ) -> dict[str, Any]:
        """Create a new pull request in the repository."""
        owner = self.settings.gitea_admin_user
        payload = {
            "title": title,
            "head": head,
            "base": base,
            "body": body,
        }
        with httpx.Client(timeout=10.0, auth=self.auth) as client:
            res = client.post(
                f"{self.base_url}/api/v1/repos/{owner}/{repo_name}/pulls",
                json=payload,
            )
            if res.status_code in (200, 201):
                data = res.json()
                if isinstance(data, dict):
                    return data
                return {}
            msg = (
                f"Failed to create pull request for '{repo_name}' ({head} -> {base}): "
                f"status={res.status_code} body={res.text}"
            )
            raise GiteaAPIError(msg)

    def get_pull_request(self, repo_name: str, index: int) -> dict[str, Any]:
        """Retrieve details of a pull request by index."""
        owner = self.settings.gitea_admin_user
        with httpx.Client(timeout=10.0, auth=self.auth) as client:
            res = client.get(f"{self.base_url}/api/v1/repos/{owner}/{repo_name}/pulls/{index}")
            if res.status_code == 200:
                data = res.json()
                if isinstance(data, dict):
                    return data
                return {}
            msg = (
                f"Failed to get pull request #{index} for '{repo_name}': "
                f"status={res.status_code} body={res.text}"
            )
            raise GiteaAPIError(msg)

    def list_pull_requests(
        self,
        repo_name: str,
        state: str = "open",
    ) -> list[dict[str, Any]]:
        """List pull requests in the repository matching state ('open', 'closed', 'all')."""
        owner = self.settings.gitea_admin_user
        with httpx.Client(timeout=10.0, auth=self.auth) as client:
            res = client.get(
                f"{self.base_url}/api/v1/repos/{owner}/{repo_name}/pulls",
                params={"state": state},
            )
            if res.status_code == 200:
                data = res.json()
                if isinstance(data, list):
                    return [p for p in data if isinstance(p, dict)]
                return []
            msg = (
                f"Failed to list pull requests for '{repo_name}': "
                f"status={res.status_code} body={res.text}"
            )
            raise GiteaAPIError(msg)

    def approve_pull_request(
        self,
        repo_name: str,
        index: int,
        body: str = "Accepted by user",
    ) -> dict[str, Any] | None:
        """Submit an approval review on a pull request. Returns None if self-approval rejected."""
        owner = self.settings.gitea_admin_user
        payload = {
            "event": "APPROVED",
            "body": body,
        }
        with httpx.Client(timeout=10.0, auth=self.auth) as client:
            res = client.post(
                f"{self.base_url}/api/v1/repos/{owner}/{repo_name}/pulls/{index}/reviews",
                json=payload,
            )
            if res.status_code in (200, 201):
                data = res.json()
                if isinstance(data, dict):
                    return data
                return {}
            if res.status_code == 422:
                logger.debug(
                    "Self-approval rejected on PR #%d for '%s': %s",
                    index,
                    repo_name,
                    res.text,
                )
                return None
            msg = (
                f"Failed to approve pull request #{index} for '{repo_name}': "
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
    ) -> bool:
        """Merge a pull request."""
        owner = self.settings.gitea_admin_user
        payload: dict[str, Any] = {
            "Do": do,
            "delete_branch_after_merge": delete_branch,
        }
        if merge_commit_id is not None:
            payload["merge_commit_id"] = merge_commit_id
        with httpx.Client(timeout=10.0, auth=self.auth) as client:
            res = client.post(
                f"{self.base_url}/api/v1/repos/{owner}/{repo_name}/pulls/{index}/merge",
                json=payload,
            )
            if res.status_code in (200, 204):
                return True
            msg = (
                f"Failed to merge pull request #{index} for '{repo_name}': "
                f"status={res.status_code} body={res.text}"
            )
            raise GiteaAPIError(msg)

    def get_pull_request_diff(self, repo_name: str, index: int) -> str:
        """Retrieve raw unified diff for a pull request by index."""
        owner = self.settings.gitea_admin_user
        with httpx.Client(timeout=10.0, auth=self.auth) as client:
            res = client.get(f"{self.base_url}/api/v1/repos/{owner}/{repo_name}/pulls/{index}.diff")
            if res.status_code == 200:
                return res.text
            if res.status_code == 404:
                return ""
            msg = (
                f"Failed to get pull request diff #{index} for '{repo_name}': "
                f"status={res.status_code} body={res.text}"
            )
            raise GiteaAPIError(msg)

    def get_authenticated_clone_url(self, repo_name: str) -> str:
        """Construct authenticated git clone URL with credentials embedded."""
        parsed = urlparse(self.base_url)
        user = self.settings.gitea_admin_user
        password = self.settings.gitea_admin_password
        netloc = f"{user}:{password}@{parsed.netloc}"
        path = f"/{user}/{repo_name}.git"
        return urlunparse((parsed.scheme, netloc, path, "", "", ""))
