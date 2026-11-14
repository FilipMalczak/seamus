"""Configuration tests for the containerised launch stack.

`REQ-010` specifies a one-command launch with a safe service restart and a
clean reset. The launch path is the first thing a new user touches, and a
broken compose topology is otherwise discovered only at first run.

These tests validate the *configuration* — the compose service graph, the
volume mounts, the health-check wiring, and the `run.sh` control flow — without
starting any container. They are deliberately static: they assert the shape of
the deployment, not the behaviour of a running stack.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
COMPOSE_PATH = REPO_ROOT / "docker-compose.yml"
RUN_SH_PATH = REPO_ROOT / "run.sh"
CI_PATH = REPO_ROOT / ".github" / "workflows" / "ci.yml"


@pytest.fixture(scope="module")
def compose() -> dict[str, Any]:
    """The parsed compose file."""
    with COMPOSE_PATH.open(encoding="utf-8") as handle:
        parsed = yaml.safe_load(handle)
    assert isinstance(parsed, dict)
    return parsed


@pytest.fixture(scope="module")
def services(compose: dict[str, Any]) -> dict[str, Any]:
    """The compose service definitions."""
    service_map = compose.get("services")
    assert isinstance(service_map, dict)
    return service_map


@pytest.fixture(scope="module")
def run_script() -> str:
    """The raw text of `run.sh`."""
    return RUN_SH_PATH.read_text(encoding="utf-8")


def test_compose_file_is_valid_yaml_with_services(compose: dict[str, Any]) -> None:
    """REQ-010: the compose file parses and declares a service graph."""
    assert "services" in compose
    assert compose["services"], "expected at least one service"


def test_compose_declares_the_expected_services(services: dict[str, Any]) -> None:
    """REQ-010: every service the product depends on is present."""
    expected = {
        "postgres",
        "gitea",
        "gitea-init",
        "openbao",
        "openbao-init",
        "openbao-db-init",
        "opensandbox",
        "sandbox-image",
        "ollama",
        "backend",
        "frontend",
    }
    assert expected <= set(services)


def test_backend_waits_for_its_dependencies_to_be_healthy(services: dict[str, Any]) -> None:
    """REQ-010: the backend must not start before its dependencies are ready."""
    depends_on = services["backend"].get("depends_on", {})

    assert depends_on["gitea"]["condition"] == "service_healthy"
    assert depends_on["gitea-init"]["condition"] == "service_completed_successfully"
    assert depends_on["openbao-init"]["condition"] == "service_completed_successfully"
    assert depends_on["opensandbox"]["condition"] == "service_healthy"
    assert depends_on["sandbox-image"]["condition"] == "service_completed_successfully"
    assert depends_on["ollama"]["condition"] == "service_healthy"


def test_frontend_waits_for_a_healthy_backend(services: dict[str, Any]) -> None:
    """REQ-010: the UI must not start before the API is serving."""
    depends_on = services["frontend"].get("depends_on", {})
    assert depends_on["backend"]["condition"] == "service_healthy"


def test_gitea_waits_for_postgres(services: dict[str, Any]) -> None:
    """REQ-010: Gitea must not start before its database is ready."""
    depends_on = services["gitea"].get("depends_on", {})
    assert depends_on["postgres"]["condition"] == "service_healthy"


def test_openbao_waits_for_its_database_initialisation(services: dict[str, Any]) -> None:
    """REQ-010: OpenBao must not start before its schema exists."""
    depends_on = services["openbao"].get("depends_on", {})
    assert depends_on["postgres"]["condition"] == "service_healthy"
    assert depends_on["openbao-db-init"]["condition"] == "service_completed_successfully"


def test_services_that_are_depended_on_declare_a_healthcheck(services: dict[str, Any]) -> None:
    """REQ-010: a `service_healthy` dependency is only meaningful with a healthcheck."""
    for name in ("postgres", "gitea", "ollama"):
        healthcheck = services[name].get("healthcheck")
        assert healthcheck is not None, f"{name} must declare a healthcheck"
        assert healthcheck.get("test"), f"{name} must declare a healthcheck command"


def test_backend_and_frontend_publish_their_expected_ports(services: dict[str, Any]) -> None:
    """REQ-010: the published ports are part of the launch contract."""
    assert "8000:8000" in services["backend"]["ports"]
    assert "3000:3000" in services["frontend"]["ports"]
    assert "3001:3000" in services["gitea"]["ports"]
    assert "8200:8200" in services["openbao"]["ports"]


def test_backend_mounts_the_workspace_and_secret_volumes(services: dict[str, Any]) -> None:
    """REQ-010: the backend needs the workspace volume and read-only secret mounts."""
    volumes = services["backend"]["volumes"]

    assert "backend-workspaces:/app/workspaces" in volumes
    assert "opensandbox-auth:/var/run/seamus-opensandbox:ro" in volumes
    assert "openbao-auth:/var/run/seamus-openbao:ro" in volumes


def test_backend_reads_the_env_file_without_interpolation(services: dict[str, Any]) -> None:
    """REQ-010: `${secret(...)}` references in `.env` must not be expanded by Compose."""
    env_file = services["backend"]["env_file"]
    assert isinstance(env_file, list)
    assert env_file[0]["path"] == ".env"
    assert env_file[0]["required"] is False
    assert env_file[0]["format"] == "raw"


def test_compose_declares_the_named_volumes(
    services: dict[str, Any], compose: dict[str, Any]
) -> None:
    """REQ-010: every referenced volume is declared."""
    volumes = compose.get("volumes", {})
    assert "postgres-data" in volumes
    assert "gitea-data" in volumes
    assert "backend-workspaces" in volumes
    assert "opensandbox-data" in volumes
    assert "opensandbox-auth" in volumes
    assert "openbao-auth" in volumes
    assert "ollama-data" in volumes


def test_workspace_volume_has_a_stable_name(
    services: dict[str, Any], compose: dict[str, Any]
) -> None:
    """REQ-010: the workspace volume is shared with the sandbox and must be stable."""
    assert compose["volumes"]["backend-workspaces"]["name"] == "seamus-workspaces"


def test_sandbox_image_is_built_from_the_sandbox_dockerfile(services: dict[str, Any]) -> None:
    """REQ-010: the sandbox image is a first-class build target."""
    build = services["sandbox-image"]["build"]
    assert build["dockerfile"] == "Dockerfile.sandbox"
    assert services["sandbox-image"]["image"] == "seamus-sandbox:latest"


def test_opensandbox_server_is_built_from_its_own_dockerfile(services: dict[str, Any]) -> None:
    """REQ-010: the sandbox server is built from the opensandbox context."""
    build = services["opensandbox"]["build"]
    assert build["context"] == "./opensandbox"
    assert build["dockerfile"] == "Dockerfile"


def test_run_script_is_executable_and_strict(run_script: str) -> None:
    """REQ-010: the launcher must fail fast on errors."""
    assert RUN_SH_PATH.exists()
    assert shutil.which("bash") is not None
    assert run_script.startswith("#!/usr/bin/env bash")
    assert "set -euo pipefail" in run_script


def test_run_script_supports_restart_and_clean(run_script: str) -> None:
    """REQ-010: the documented `--restart` and `--clean` flags exist."""
    assert "-r|--restart" in run_script
    assert "-c|--clean" in run_script
    assert "-h|--help" in run_script


def test_run_script_clean_preserves_openbao_secrets(run_script: str) -> None:
    """REQ-010: a clean reset must not destroy the secrets vault."""
    clean_block = run_script.split('if [ "$CLEAN" = true ]', 1)[1].split("elif", 1)[0]

    assert "openbao-auth" not in clean_block
    assert "openbao-data" not in clean_block
    # ...but the Gitea and workspace state is reset.
    assert "gitea-data" in clean_block
    assert "seamus-workspaces" in clean_block


def test_run_script_restart_preserves_persistent_data(run_script: str) -> None:
    """REQ-010: a restart rebuilds application containers without wiping data."""
    restart_block = run_script.split('elif [ "$RESTART" = true ]', 1)[1].split("elif", 1)[0]

    assert (
        "docker compose up -d --build opensandbox sandbox-image backend frontend" in restart_block
    )
    assert "rm -f" not in restart_block
    assert "volume rm" not in restart_block


def test_run_script_waits_for_the_health_endpoints(run_script: str) -> None:
    """REQ-010: the launcher waits for the UI, the API, and Gitea."""
    assert "http://localhost:3000" in run_script
    assert "http://localhost:8000/health" in run_script
    assert "http://localhost:3001/api/v1/version" in run_script
    assert "Timed out waiting for Seamus services to become healthy." in run_script


def test_run_script_disables_compose_env_interpolation(run_script: str) -> None:
    """REQ-010: `${secret(...)}` in `.env` must survive Compose's own expansion."""
    assert 'export COMPOSE_ENV_FILES="${COMPOSE_ENV_FILES:-/dev/null}"' in run_script


def test_run_script_rejects_unknown_options(run_script: str) -> None:
    """REQ-010: an unknown flag must fail loudly rather than silently start the stack."""
    assert "Unknown option:" in run_script
    assert "exit 1" in run_script


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash is not available")
def test_run_script_help_exits_successfully() -> None:
    """REQ-010: `--help` must not attempt to start anything."""
    result = subprocess.run(
        [str(RUN_SH_PATH), "--help"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0
    assert "Usage:" in result.stdout
    assert "--restart" in result.stdout
    assert "--clean" in result.stdout


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash is not available")
def test_run_script_rejects_unknown_flags() -> None:
    """REQ-010: an unknown flag must exit non-zero."""
    result = subprocess.run(
        [str(RUN_SH_PATH), "--not-a-flag"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 1
    assert "Unknown option" in result.stderr


def test_ci_workflow_runs_the_python_and_frontend_suites() -> None:
    """REQ-028: CI must exercise both the Python and the frontend suites."""
    workflow = CI_PATH.read_text(encoding="utf-8")

    assert "pytest" in workflow
    assert "npm test" in workflow or "npm run test" in workflow


def test_ci_workflow_runs_the_end_to_end_suite() -> None:
    """REQ-052: the deterministic end-to-end suite must run in CI."""
    workflow = CI_PATH.read_text(encoding="utf-8")

    assert re.search(r"pytest\s+tests/e2e", workflow)
