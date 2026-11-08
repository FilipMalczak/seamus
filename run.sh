#!/usr/bin/env bash
set -euo pipefail

# Prevent Docker Compose from attempting shell variable expansion on ${secret(...)} in .env;
# backend loads .env directly via env_file with format: raw.
export COMPOSE_ENV_FILES="${COMPOSE_ENV_FILES:-/dev/null}"

UI_URL="http://localhost:3000"
BACKEND_HEALTH_URL="http://localhost:8000/health"
GITEA_HEALTH_URL="http://localhost:3001/api/v1/version"
TIMEOUT_SECONDS=60
RESTART=false
CLEAN=false

usage() {
  cat <<EOF
Usage: $0 [OPTIONS]

Ensure Seamus services (FastAPI backend, React UI, OpenSandbox, Gitea, OpenBao, and PostgreSQL) are running and open in the default browser.

Options:
  -r, --restart    Restart application containers for which we own the image (backend, frontend, opensandbox, sandbox-image)
                   and rebuild to update code while preserving data and infrastructure containers
  -c, --clean      Reset Gitea, workspaces, and sandbox state while preserving OpenBao secrets, and start fresh
  -h, --help       Show this help message and exit
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    -r|--restart)
      RESTART=true
      shift
      ;;
    -c|--clean)
      CLEAN=true
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

if [ "$CLEAN" = true ]; then
  echo "Clean start requested. Resetting Gitea, workspaces, and sandbox state while preserving OpenBao secrets..."
  docker compose rm -f -s -v frontend backend opensandbox gitea gitea-init >/dev/null 2>&1 || true

  project_name="${COMPOSE_PROJECT_NAME:-$(basename "$(pwd)" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9_-]//g')}"
  docker volume rm -f \
    "${project_name}_gitea-data" \
    "seamus-workspaces" \
    "${project_name}_opensandbox-data" \
    "${project_name}_opensandbox-auth" >/dev/null 2>&1 || true
  rm -rf "${SEAMUS_WORKSPACE_DIR:-.seamus/workspaces}" .seamus/opensandbox

  docker compose up -d postgres
  until docker compose exec -T postgres pg_isready -U "${POSTGRES_USER:-gitea}" -d "${POSTGRES_DB:-gitea}" >/dev/null 2>&1; do
    sleep 1
  done
  docker compose exec -T postgres psql -U "${POSTGRES_USER:-gitea}" -d "${POSTGRES_DB:-gitea}" -c "
  DO \$\$ DECLARE
      r RECORD;
  BEGIN
      FOR r IN (
          SELECT tablename
          FROM pg_tables
          WHERE schemaname = 'public'
            AND tablename NOT IN ('vault_kv_store', 'vault_ha_locks')
      ) LOOP
          EXECUTE 'DROP TABLE IF EXISTS public.' || quote_ident(r.tablename) || ' CASCADE';
      END LOOP;
      FOR r IN (
          SELECT sequencename
          FROM pg_sequences
          WHERE schemaname = 'public'
      ) LOOP
          EXECUTE 'DROP SEQUENCE IF EXISTS public.' || quote_ident(r.sequencename) || ' CASCADE';
      END LOOP;
  END \$\$;
  " >/dev/null

  echo "Starting all services from clean state..."
  docker compose up -d --build
elif [ "$RESTART" = true ]; then
  echo "Restart requested. Rebuilding application containers (backend, frontend, opensandbox, sandbox-image) while preserving persistent data..."
  docker compose up -d --build opensandbox sandbox-image backend frontend
elif check_service_up "$UI_URL" && check_service_up "$BACKEND_HEALTH_URL" && check_service_up "$GITEA_HEALTH_URL"; then
  echo "Seamus services are already running at $UI_URL."
  echo "Opening Seamus UI in default web browser ($UI_URL)..."
  open_in_browser "$UI_URL"
  exit 0
else
  echo "Services are not fully up. Starting all services via Docker Compose..."
  docker compose up -d --build
fi

echo "Waiting for services to become healthy (timeout: ${TIMEOUT_SECONDS}s)..."
elapsed=0
while true; do
  if check_service_up "$UI_URL" && check_service_up "$BACKEND_HEALTH_URL" && check_service_up "$GITEA_HEALTH_URL"; then
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

echo "Ensuring Gitea default admin user exists..."
docker compose exec -T --user git gitea gitea admin user create \
  --username "${GITEA_ADMIN_USER:-seamus}" \
  --password "${GITEA_ADMIN_PASSWORD:-seamus-password-123}" \
  --email "${GITEA_ADMIN_EMAIL:-seamus@seamus.local}" \
  --admin --must-change-password=false >/dev/null 2>&1 || true

echo "Opening Seamus UI in default web browser ($UI_URL)..."
open_in_browser "$UI_URL"
