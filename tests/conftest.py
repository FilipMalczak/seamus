"""Global pytest fixtures and test environment configuration."""

import logging
import os
import re
import shutil
import subprocess
import time
import warnings
from collections.abc import Generator
from uuid import uuid4

import httpx
import pytest

from seamus.persistence.config import get_persistence_settings
from seamus.persistence.workspace import reset_workspace_manager

logger = logging.getLogger(__name__)


def is_docker_available() -> bool:
    """Return True if docker binary exists and daemon is responsive."""
    if not shutil.which("docker"):
        return False
    try:
        res = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        return res.returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False


@pytest.fixture(scope="session")
def ephemeral_gitea_session(
    tmp_path_factory: pytest.TempPathFactory,
) -> Generator[dict[str, str | int] | None, None, None]:
    """Session-scoped fixture starting an ephemeral Gitea container with SQLite and dynamic port."""
    if not is_docker_available():
        warnings.warn(
            "Docker is not available; disabling persistence for tests.",
            stacklevel=2,
        )
        yield None
        return

    container_name = f"seamus-test-gitea-{uuid4().hex[:8]}"
    workspace_root = tmp_path_factory.mktemp("test_workspaces")

    run_cmd = [
        "docker",
        "run",
        "-d",
        "--rm",
        "--name",
        container_name,
        "-p",
        "127.0.0.1::3000",
        "-e",
        "USER_UID=1000",
        "-e",
        "USER_GID=1000",
        "-e",
        "GITEA__database__DB_TYPE=sqlite3",
        "-e",
        "GITEA__security__INSTALL_LOCK=true",
        "-e",
        "GITEA__security__SECRET_KEY=test-secret-key-12345",
        "-e",
        "GITEA__server__DISABLE_SSH=true",
        "-e",
        "GITEA__service__DISABLE_REGISTRATION=false",
        "-e",
        "GITEA__service__REQUIRE_SIGNIN_VIEW=false",
        "gitea/gitea:latest",
    ]

    try:
        subprocess.run(run_cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        warnings.warn(
            f"Failed to start test Gitea: {exc.stderr}; falling back to disabled persistence.",
            stacklevel=2,
        )
        yield None
        return

    # Extract dynamic host port
    try:
        port_proc = subprocess.run(
            ["docker", "port", container_name, "3000"],
            check=True,
            capture_output=True,
            text=True,
        )
        port_match = re.search(r":(\d+)$", port_proc.stdout.strip())
        if not port_match:
            raise RuntimeError(f"Could not parse port from docker port output: {port_proc.stdout}")
        port = int(port_match.group(1))
    except Exception as exc:
        subprocess.run(["docker", "rm", "-f", container_name], capture_output=True)
        warnings.warn(
            f"Failed to resolve Gitea port: {exc}; falling back to disabled persistence.",
            stacklevel=2,
        )
        yield None
        return

    gitea_url = f"http://127.0.0.1:{port}"

    # Poll until Gitea is healthy
    deadline = time.time() + 25.0
    ready = False
    while time.time() < deadline:
        try:
            with httpx.Client(timeout=1.0) as client:
                res = client.get(f"{gitea_url}/api/v1/version")
                if res.status_code == 200:
                    ready = True
                    break
        except Exception:
            pass
        time.sleep(0.5)

    if not ready:
        subprocess.run(["docker", "rm", "-f", container_name], capture_output=True)
        warnings.warn(
            f"Test Gitea container on port {port} failed to become healthy; falling back.",
            stacklevel=2,
        )
        yield None
        return

    # Create admin user
    user_created = False
    create_cmd = [
        "docker",
        "exec",
        "-u",
        "1000:1000",
        container_name,
        "gitea",
        "admin",
        "user",
        "create",
        "--username",
        "seamus",
        "--password",
        "seamus-password-123",
        "--email",
        "seamus@seamus.local",
        "--admin",
        "--must-change-password=false",
    ]
    for _ in range(5):
        user_proc = subprocess.run(create_cmd, capture_output=True, text=True)
        if user_proc.returncode == 0:
            user_created = True
            break
        time.sleep(1.0)

    if not user_created:
        subprocess.run(["docker", "rm", "-f", container_name], capture_output=True)
        warnings.warn(
            f"Failed to create admin user in test Gitea: {user_proc.stderr}; falling back.",
            stacklevel=2,
        )
        yield None
        return

    session_info: dict[str, str | int] = {
        "container_name": container_name,
        "port": port,
        "url": gitea_url,
        "workspace_dir": str(workspace_root),
    }

    try:
        yield session_info
    finally:
        subprocess.run(["docker", "rm", "-f", container_name], capture_output=True)


@pytest.fixture(autouse=True, scope="session")
def configure_test_environment(
    ephemeral_gitea_session: dict[str, str | int] | None,
    tmp_path_factory: pytest.TempPathFactory,
) -> Generator[None, None, None]:
    """Configure persistence settings and environment variables for the entire test session."""
    original_env = os.environ.copy()
    os.environ.setdefault("LOGFIRE_TOKEN", "test-logfire-token")

    if ephemeral_gitea_session is not None:
        os.environ["GITEA_URL"] = str(ephemeral_gitea_session["url"])
        os.environ["GITEA_EXTERNAL_URL"] = str(ephemeral_gitea_session["url"])
        os.environ["GITEA_ADMIN_USER"] = "seamus"
        os.environ["GITEA_ADMIN_PASSWORD"] = "seamus-password-123"
        os.environ["GITEA_ADMIN_EMAIL"] = "seamus@seamus.local"
        os.environ["SEAMUS_WORKSPACE_DIR"] = str(ephemeral_gitea_session["workspace_dir"])
        os.environ["SEAMUS_PERSISTENCE_ENABLED"] = "true"
    else:
        fallback_dir = tmp_path_factory.mktemp("fallback_workspaces")
        os.environ["SEAMUS_WORKSPACE_DIR"] = str(fallback_dir)
        os.environ["SEAMUS_PERSISTENCE_ENABLED"] = "false"

    get_persistence_settings.cache_clear()
    reset_workspace_manager(None)

    yield

    os.environ.clear()
    os.environ.update(original_env)
    get_persistence_settings.cache_clear()
    reset_workspace_manager(None)


@pytest.fixture(autouse=True)
def reset_workspace_manager_per_test() -> Generator[None, None, None]:
    """Ensure singleton workspace manager is reset cleanly before and after each test."""
    reset_workspace_manager(None)
    get_persistence_settings.cache_clear()
    yield
    reset_workspace_manager(None)
    get_persistence_settings.cache_clear()
