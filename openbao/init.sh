#!/bin/sh
set -e

export BAO_ADDR="http://openbao:8200"
AUTH_DIR="/var/run/seamus-openbao"
UNSEAL_KEY_FILE="$AUTH_DIR/unseal_key"
ROOT_TOKEN_FILE="$AUTH_DIR/root_token"

mkdir -p "$AUTH_DIR"

echo "[openbao-init] Waiting for OpenBao server to become available at $BAO_ADDR..."
while true; do
  set +e
  bao operator init -status > /dev/null 2>&1
  status=$?
  set -e
  if [ "$status" -eq 0 ] || [ "$status" -eq 2 ]; then
    break
  fi
  sleep 1
done

if [ "$status" -eq 2 ]; then
  echo "[openbao-init] OpenBao is uninitialized. Initializing now..."
  INIT_OUTPUT=$(bao operator init -key-shares=1 -key-threshold=1 -format=json)

  UNSEAL_KEY=$(echo "$INIT_OUTPUT" | grep -A 1 unseal_keys_b64 | tail -n 1 | cut -d'"' -f2)
  ROOT_TOKEN=$(echo "$INIT_OUTPUT" | grep root_token | cut -d'"' -f4)

  if [ -z "$UNSEAL_KEY" ] || [ -z "$ROOT_TOKEN" ]; then
    echo "[openbao-init] ERROR: Failed to parse unseal key or root token from init output!"
    exit 1
  fi

  echo "$UNSEAL_KEY" > "$UNSEAL_KEY_FILE"
  echo "$ROOT_TOKEN" > "$ROOT_TOKEN_FILE"
  chmod 644 "$UNSEAL_KEY_FILE" "$ROOT_TOKEN_FILE"

  echo "[openbao-init] Unsealing OpenBao..."
  bao operator unseal "$UNSEAL_KEY"

  export BAO_TOKEN="$ROOT_TOKEN"
  echo "[openbao-init] Mounting KV v2 engine at secret/..."
  bao secrets enable -path=secret -version=2 kv || true

  echo "[openbao-init] Initialization complete."
else
  echo "[openbao-init] OpenBao is already initialized."
  set +e
  bao status > /dev/null 2>&1
  sealed_status=$?
  set -e
  if [ "$sealed_status" -eq 2 ]; then
    if [ -f "$UNSEAL_KEY_FILE" ]; then
      UNSEAL_KEY=$(cat "$UNSEAL_KEY_FILE")
      echo "[openbao-init] OpenBao is sealed. Unsealing using saved key..."
      bao operator unseal "$UNSEAL_KEY"
      echo "[openbao-init] Unsealed successfully."
    else
      echo "[openbao-init] WARNING: OpenBao is sealed but $UNSEAL_KEY_FILE not found!"
      exit 1
    fi
  else
    echo "[openbao-init] OpenBao is already unsealed and active."
  fi
fi

