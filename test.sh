#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

RUN_UI=false
RUN_BACKEND=false
RUN_E2E=false
ANY_SELECTED=false

usage() {
  cat <<EOF
Usage: $0 [[--ui] [--backend] [--e2e] | --all]

Run Seamus test suites. With no flags, defaults to --backend.

Options:
  --ui        Run frontend React tests (cd ui && npm test)
  --backend   Run backend unit and integration tests (uv run pytest)
  --e2e       Run end-to-end tests only (uv run pytest tests/e2e --e2e)
  --all       Run --backend, --e2e, and --ui
  -h, --help  Show this help message and exit
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

if [ "$RUN_BACKEND" = true ]; then
  echo "==> Running backend tests..."
  uv run pytest
fi

if [ "$RUN_E2E" = true ]; then
  echo "==> Running end-to-end tests..."
  uv run pytest tests/e2e --e2e -n auto
fi

if [ "$RUN_UI" = true ]; then
  echo "==> Running UI tests..."
  (cd ui && npm test)
fi

