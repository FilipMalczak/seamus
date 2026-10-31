#!/usr/bin/env sh
set -eu

KEY_FILE="${SEAMUS_OPENSANDBOX_KEY_FILE:-/var/run/seamus-opensandbox/api_key}"
KEY_DIR="$(dirname "$KEY_FILE")"
mkdir -p "$KEY_DIR"

if [ ! -s "$KEY_FILE" ]; then
  python3 -c "import os, pathlib, secrets; p = pathlib.Path('$KEY_FILE'); p.write_text(secrets.token_urlsafe(32) + '\n', encoding='utf-8'); os.chmod(p, 0o600)"
fi

export OPENSANDBOX_SERVER_API_KEY="$(tr -d '\r\n' < "$KEY_FILE")"

exec opensandbox-server --config "${SANDBOX_CONFIG_PATH:-/etc/opensandbox/config.toml}" "$@"

