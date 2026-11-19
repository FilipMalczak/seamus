#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

RUN_UI=false
RUN_BACKEND=false
RUN_E2E=false
ANY_SELECTED=false
PERSISTENCE_MODE=""
PARALLEL="true"
PARALLEL_EXPLICIT=false

usage() {
  cat <<EOF
Usage: $0 [[--ui] [--backend] [--e2e] | --all] [--docker | --in-memory] [--parallel true|false|N]

Run Seamus test suites. With no suite flags, defaults to --backend.
With no persistence flag, defaults to --docker.
With no parallel flag, defaults to --parallel true.

Options:
  --ui                    Run frontend React tests (cd ui && npm test)
  --backend               Run backend unit and integration tests (uv run pytest)
  --e2e                   Run end-to-end tests only (uv run pytest tests/e2e --e2e)
  --all                   Run --backend, --e2e, and --ui
  --docker                Run Python tests against ephemeral Docker Gitea persistence (default)
  --in-memory             Run Python tests in-memory with Docker persistence disabled
                          (with --e2e, deselects @pytest.mark.gitea tests)
  --parallel true|false|N Control parallel execution for Python tests (default: true).
                          true maps to -n auto, false runs sequentially, N sets worker count.
                          Ignored with a warning if used without Python suites (e.g. only --ui).
  -h, --help              Show this help message and exit
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
    --parallel)
      if [ "$#" -lt 2 ]; then
        echo "Error: --parallel requires an argument (true, false, or a positive integer)" >&2
        exit 1
      fi
      PARALLEL="$2"
      PARALLEL_EXPLICIT=true
      shift 2
      ;;
    --parallel=*)
      PARALLEL="${1#*=}"
      PARALLEL_EXPLICIT=true
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

if [ -z "$PERSISTENCE_MODE" ]; then
  PERSISTENCE_MODE="docker"
fi

if [ "$PERSISTENCE_MODE" = "in-memory" ]; then
  export SEAMUS_TEST_IN_MEMORY="true"
else
  export SEAMUS_TEST_IN_MEMORY="false"
fi

case "$PARALLEL" in
  true|True|TRUE)
    PYTEST_PARALLEL_ARGS=("-n" "auto")
    PARALLEL_DISPLAY="auto"
    ;;
  false|False|FALSE)
    PYTEST_PARALLEL_ARGS=()
    PARALLEL_DISPLAY="sequential"
    ;;
  *)
    if [[ "$PARALLEL" =~ ^[1-9][0-9]*$ ]]; then
      PYTEST_PARALLEL_ARGS=("-n" "$PARALLEL")
      PARALLEL_DISPLAY="$PARALLEL workers"
    else
      echo "Error: Invalid value for --parallel: '$PARALLEL' (expected 'true', 'false', or a positive integer)" >&2
      exit 1
    fi
    ;;
esac

if [ "$PARALLEL_EXPLICIT" = true ] && [ "$RUN_BACKEND" = false ] && [ "$RUN_E2E" = false ]; then
  echo "Warning: --parallel has no effect because no Python test suites (--backend, --e2e, or --all) were selected (UI tests do not run in parallel)." >&2
fi

if [ "$RUN_BACKEND" = true ]; then
  echo "==> Running backend tests (persistence: $PERSISTENCE_MODE, parallel: $PARALLEL_DISPLAY)..."
  uv run pytest ${PYTEST_PARALLEL_ARGS[@]+"${PYTEST_PARALLEL_ARGS[@]}"}
fi

if [ "$RUN_E2E" = true ]; then
  echo "==> Running end-to-end tests (persistence: $PERSISTENCE_MODE, parallel: $PARALLEL_DISPLAY)..."
  if [ "$PERSISTENCE_MODE" = "in-memory" ]; then
    uv run pytest tests/e2e --e2e ${PYTEST_PARALLEL_ARGS[@]+"${PYTEST_PARALLEL_ARGS[@]}"} -m "not gitea"
  else
    uv run pytest tests/e2e --e2e ${PYTEST_PARALLEL_ARGS[@]+"${PYTEST_PARALLEL_ARGS[@]}"}
  fi
fi

if [ "$RUN_UI" = true ]; then
  echo "==> Running UI tests..."
  (cd ui && npm test)
fi

echo "==> All selected test suites passed successfully!"

