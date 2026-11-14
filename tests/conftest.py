"""Global pytest fixtures and test environment configuration."""

import fcntl
import json
import logging
import os
import re
import shutil
import socket
import subprocess
import time
from collections.abc import Generator
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import pytest

from seamus.config.settings import reset_system_settings_store
from seamus.config.template import reset_config_template_store
from seamus.persistence.config import get_persistence_settings
from seamus.persistence.workspace import reset_workspace_manager

logger = logging.getLogger(__name__)


def pytest_load_initial_conftests(
    early_config: pytest.Config, parser: pytest.Parser, args: list[str]
) -> None:
    """Default e2e-only runs to parallel xdist execution while keeping non-e2e sequential."""
    has_e2e = "--e2e" in args
    targets_e2e_only = any("tests/e2e" in arg.replace("\\", "/") for arg in args)
    has_numprocesses = any(
        arg == "-n" or arg.startswith("-n") or arg.startswith("--numprocesses") for arg in args
    )
    if has_e2e and targets_e2e_only and not has_numprocesses:
        args.extend(["-n", "auto"])


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register CLI options for optional test suites."""
    parser.addoption(
        "--e2e",
        action="store_true",
        default=False,
        help="Run end-to-end tests under tests/e2e/.",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip end-to-end tests unless --e2e is explicitly passed."""
    run_e2e = bool(config.getoption("--e2e"))
    skip_e2e = pytest.mark.skip(reason="need --e2e option to run")
    for item in items:
        if "tests/e2e" in str(item.path).replace("\\", "/"):
            item.add_marker(pytest.mark.e2e)
            if not run_e2e:
                item.add_marker(skip_e2e)


def _probe_runtime(cmd: list[str]) -> bool:
    """Return True if the given container runtime CLI is installed and responsive."""
    if not all(shutil.which(part) for part in cmd if not part.startswith("-")):
        return False
    try:
        res = subprocess.run(
            [*cmd, "info"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return res.returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False


def get_container_runtime() -> list[str] | None:
    """Return the available container runtime command prefix (docker or nerdctl), or None."""
    if os.environ.get("SEAMUS_TEST_IN_MEMORY", "").lower() in ("true", "1", "yes"):
        return None
    for candidate in (["docker"], ["nerdctl"], ["sudo", "-n", "nerdctl"]):
        if _probe_runtime(candidate):
            return candidate
    return None


def is_docker_available() -> bool:
    """Return True if a supported container runtime (Docker or containerd/nerdctl) is available."""
    return get_container_runtime() is not None


def _allocate_ephemeral_port() -> int:
    """Bind an ephemeral localhost TCP port and return its port number."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _gitea_shared_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Return a directory shared across pytest-xdist workers for coordinating Gitea."""
    base = tmp_path_factory.getbasetemp()
    if os.environ.get("PYTEST_XDIST_WORKER"):
        return base.parent
    return base


def _start_gitea_container(runtime: list[str]) -> dict[str, Any]:
    """Start an ephemeral Gitea container, wait for health, and create the admin user."""
    container_name = f"seamus-test-gitea-{uuid4().hex[:8]}"
    # nerdctl's dynamic host port allocation can fall back to a static port; pick one explicitly.
    port_arg = (
        "127.0.0.1::3000"
        if runtime[-1] == "docker"
        else f"127.0.0.1:{_allocate_ephemeral_port()}:3000"
    )
    run_cmd = [
        *runtime,
        "run",
        "-d",
        "--rm",
        "--name",
        container_name,
        "-p",
        port_arg,
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
        raise RuntimeError(f"Failed to start test Gitea container: {exc.stderr}") from exc

    try:
        port_proc = subprocess.run(
            [*runtime, "port", container_name, "3000"],
            check=True,
            capture_output=True,
            text=True,
        )
        port_match = re.search(r":(\d+)$", port_proc.stdout.strip())
        if not port_match:
            raise RuntimeError(
                f"Could not parse port from {runtime[-1]} port output: {port_proc.stdout}"
            )
        port = int(port_match.group(1))
    except Exception as exc:
        subprocess.run([*runtime, "rm", "-f", container_name], capture_output=True)
        raise RuntimeError(f"Failed to resolve test Gitea port: {exc}") from exc

    gitea_url = f"http://127.0.0.1:{port}"

    deadline = time.time() + 45.0
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
        logs = subprocess.run(
            [*runtime, "logs", "--tail", "50", container_name],
            capture_output=True,
            text=True,
        )
        subprocess.run([*runtime, "rm", "-f", container_name], capture_output=True)
        raise RuntimeError(
            f"Test Gitea container on port {port} failed to become healthy within 45s.\n"
            f"Logs:\n{logs.stdout}\n{logs.stderr}"
        )

    create_cmd = [
        *runtime,
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
    user_proc: subprocess.CompletedProcess[str] | None = None
    for _ in range(5):
        user_proc = subprocess.run(create_cmd, capture_output=True, text=True)
        if user_proc.returncode == 0:
            break
        time.sleep(1.0)
    else:
        stderr = user_proc.stderr if user_proc is not None else "unknown error"
        subprocess.run([*runtime, "rm", "-f", container_name], capture_output=True)
        raise RuntimeError(f"Failed to create admin user in test Gitea: {stderr}")

    return {
        "container_name": container_name,
        "port": port,
        "url": gitea_url,
        "runtime": runtime,
    }


@pytest.fixture(scope="session")
def ephemeral_gitea_session(
    tmp_path_factory: pytest.TempPathFactory,
) -> Generator[dict[str, Any] | None, None, None]:
    """Session-scoped fixture sharing one ephemeral Gitea container across xdist workers."""
    if os.environ.get("SEAMUS_TEST_IN_MEMORY", "").lower() in ("true", "1", "yes"):
        logger.info("SEAMUS_TEST_IN_MEMORY is set; running tests with persistence disabled.")
        yield None
        return

    runtime = get_container_runtime()
    if runtime is None:
        raise RuntimeError(
            "No container runtime (Docker or containerd/nerdctl) is available, "
            "but SEAMUS_TEST_IN_MEMORY is not enabled. "
            "Start Docker/containerd or set SEAMUS_TEST_IN_MEMORY=true."
        )

    shared_root = _gitea_shared_root(tmp_path_factory)
    lock_path = shared_root / "gitea_session.lock"
    info_path = shared_root / "gitea_session.json"
    refs_path = shared_root / "gitea_session_refs.json"

    with open(lock_path, "a+") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        try:
            if info_path.exists():
                gitea_info: dict[str, Any] = json.loads(info_path.read_text())
                refs = int(refs_path.read_text()) if refs_path.exists() else 0
                refs_path.write_text(str(refs + 1))
            else:
                gitea_info = _start_gitea_container(runtime)
                info_path.write_text(json.dumps(gitea_info))
                refs_path.write_text("1")
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)

    workspace_root = tmp_path_factory.mktemp("test_workspaces")
    session_info: dict[str, Any] = {
        **gitea_info,
        "workspace_dir": str(workspace_root),
    }

    try:
        yield session_info
    finally:
        with open(lock_path, "a+") as lock_file:
            fcntl.flock(lock_file, fcntl.LOCK_EX)
            try:
                refs = int(refs_path.read_text()) if refs_path.exists() else 1
                remaining = refs - 1
                if remaining <= 0:
                    runtime_cmd = gitea_info.get("runtime", runtime)
                    subprocess.run(
                        [*runtime_cmd, "rm", "-f", str(gitea_info["container_name"])],
                        capture_output=True,
                    )
                    info_path.unlink(missing_ok=True)
                    refs_path.unlink(missing_ok=True)
                else:
                    refs_path.write_text(str(remaining))
            finally:
                fcntl.flock(lock_file, fcntl.LOCK_UN)


@pytest.fixture(autouse=True, scope="session")
def configure_test_environment(
    ephemeral_gitea_session: dict[str, Any] | None,
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
    """Ensure singleton stores and workspace manager are reset cleanly per test."""
    reset_workspace_manager(None)
    reset_system_settings_store(None)
    reset_config_template_store(None)
    get_persistence_settings.cache_clear()
    yield
    reset_workspace_manager(None)
    reset_system_settings_store(None)
    reset_config_template_store(None)
    get_persistence_settings.cache_clear()
