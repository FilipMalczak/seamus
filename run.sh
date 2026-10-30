#!/usr/bin/env bash
set -euo pipefail

UI_URL="http://localhost:3000"
BACKEND_HEALTH_URL="http://localhost:8000/health"
TIMEOUT_SECONDS=60
RESTART=false

usage() {
  cat <<EOF
Usage: $0 [OPTIONS]

Ensure Seamus services (FastAPI backend and React UI) are running and open in the default browser.

Options:
  -r, --restart    Restart all services and rebuild images to update to the latest version
                   (preserves persistent data volumes; does not wipe state)
  -h, --help       Show this help message and exit
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    -r|--restart)
      RESTART=true
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

check_service_up() {
  if command -v curl >/dev/null 2>&1; then
    curl -s -f -m 2 "$1" >/dev/null 2>&1
  else
    python3 -c "import urllib.request; urllib.request.urlopen('$1', timeout=2)" >/dev/null 2>&1
  fi
}

open_in_browser() {
  local target_url="$1"
  if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$target_url" >/dev/null 2>&1 || true
  elif command -v open >/dev/null 2>&1; then
    open "$target_url" >/dev/null 2>&1 || true
  elif command -v sensible-browser >/dev/null 2>&1; then
    sensible-browser "$target_url" >/dev/null 2>&1 || true
  elif command -v powershell.exe >/dev/null 2>&1; then
    powershell.exe -NoProfile -Command "Start-Process '$target_url'" >/dev/null 2>&1 || true
  elif command -v cmd.exe >/dev/null 2>&1; then
    cmd.exe /c start "$target_url" >/dev/null 2>&1 || true
  else
    echo "Please open $target_url in your browser."
  fi
}

echo "Checking Seamus service status..."

if [ "$RESTART" = false ] && check_service_up "$UI_URL" && check_service_up "$BACKEND_HEALTH_URL"; then
  echo "Seamus services are already running at $UI_URL."
else
  if [ "$RESTART" = true ]; then
    echo "Restart requested. Rebuilding containers to update to latest version (preserving persistent data)..."
  else
    echo "Services are not fully up. Starting all services via Docker Compose..."
  fi

  docker compose up -d --build --force-recreate

  echo "Waiting for services to become healthy (timeout: ${TIMEOUT_SECONDS}s)..."
  elapsed=0
  while true; do
    if check_service_up "$UI_URL" && check_service_up "$BACKEND_HEALTH_URL"; then
      echo "All Seamus services are up and healthy!"
      break
    fi

    sleep 1
    elapsed=$((elapsed + 1))
    if [ "$elapsed" -ge "$TIMEOUT_SECONDS" ]; then
      echo "Timed out waiting for Seamus services to become healthy."
      echo "Check container logs with: docker compose logs"
      exit 1
    fi
  done
fi

echo "Opening Seamus UI in default web browser ($UI_URL)..."
open_in_browser "$UI_URL"
