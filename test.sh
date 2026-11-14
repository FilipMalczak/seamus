#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

RUN_UI=false
RUN_BACKEND=false
RUN_E2E=false
ANY_SELECTED=false
PERSISTENCE_MODE=""

usage() {
  cat <<EOF
Usage: $0 [[--ui] [--backend] [--e2e] | --all] [--docker | --in-memory]

Run Seamus test suites. With no suite flags, defaults to --backend.
With no persistence flag, defaults to --docker.

Options:
  --ui          Run frontend React tests (cd ui && npm test)
  --backend     Run backend unit and integration tests (uv run pytest)
  --e2e         Run end-to-end tests only (uv run pytest tests/e2e --e2e -n auto)
  --all         Run --backend, --e2e, and --ui
  --docker      Run Python tests against ephemeral Docker Gitea persistence (default)
  --in-memory   Run Python tests in-memory with Docker persistence disabled
                (with --e2e, deselects @pytest.mark.gitea tests)
  -h, --help    Show this help message and exit
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --ui)
      RUN_UI=true
      ANY_SELECTED=true
      shift
      ;;
    --backend)
      RUN_BACKEND=true
      ANY_SELECTED=true
      shift
      ;;
    --e2e)
      RUN_E2E=true
      ANY_SELECTED=true
      shift
      ;;
    --all)
      RUN_UI=true
      RUN_BACKEND=true
      RUN_E2E=true
      ANY_SELECTED=true
      shift
      ;;
    --docker)
      if [ "$PERSISTENCE_MODE" = "in-memory" ]; then
        echo "Cannot combine --docker and --in-memory" >&2
        exit 1
      fi
      PERSISTENCE_MODE="docker"
      shift
      ;;
    --in-memory)
      if [ "$PERSISTENCE_MODE" = "docker" ]; then
        echo "Cannot combine --docker and --in-memory" >&2
        exit 1
      fi
      PERSISTENCE_MODE="in-memory"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [ "$ANY_SELECTED" = false ]; then
  RUN_BACKEND=true
fi

if [ "$PERSISTENCE_MODE" = "in-memory" ]; then
  export SEAMUS_TEST_IN_MEMORY="true"
else
  export SEAMUS_TEST_IN_MEMORY="false"
fi

if [ "$RUN_BACKEND" = true ]; then
  echo "==> Running backend tests..."
  uv run pytest
fi

if [ "$RUN_E2E" = true ]; then
  echo "==> Running end-to-end tests..."
  if [ "$PERSISTENCE_MODE" = "in-memory" ]; then
    uv run pytest tests/e2e --e2e -n auto -m "not gitea"
  else
    uv run pytest tests/e2e --e2e -n auto
  fi
fi

if [ "$RUN_UI" = true ]; then
  echo "==> Running UI tests..."
  (cd ui && npm test)
fi

