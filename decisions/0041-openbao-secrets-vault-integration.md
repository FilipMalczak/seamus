# 0041: OpenBao Secrets Vault Integration (MVP)

## Status

Accepted

## Context

Previously, sensitive credentials such as inference API keys (`InferenceConfig.api_key`) were stored directly in configuration files (`config.json`) committed to Gitea repositories (`seamus-system`, `agent-{agent_id}`, and `session/{session_id}` branches). Persisting cleartext secrets in Git history creates a credential exposure risk and prevents clean rotation across active sessions. Furthermore, upcoming features (such as mounting custom external Git repositories into sandboxes) will require storing and resolving Git checkout credentials safely.

A preliminary exploration on the `spike-openbao-secrets-vault-integration` branch solved core operational challenges with OpenBao (PostgreSQL storage schema constraints, container initialization exit codes, auto-unsealing via a shared volume, and KV v2 mounting), while leaving the exact expression grammar, per-inference version watching, checkpoint provenance recording, and Web UI surfaces to be aligned with the target architecture.

## Decision

We integrate **OpenBao** (KV v2 secrets engine mounted at `secret/`) as an MVP secrets vault across the Docker Compose stack, Python harness, Git persistence layer, and React Web UI:

1. **Docker Compose & Auxiliary Initialization (`openbao` + `openbao-init`)**:
   - Add `openbao` (`openbao/openbao:latest` on port `8200` with Web UI enabled) backed by PostgreSQL (`vault_kv_store` and `vault_ha_locks` tables initialized by `openbao-db-init`).
   - Add an auxiliary `openbao-init` container running `openbao/init.sh` that checks initialization status (handling `bao operator init -status` exit code `2`), initializes OpenBao on first boot, persists `unseal_key` and `root_token` to the `openbao-auth` volume (`/var/run/seamus-openbao`), unseals the vault on every container start, and ensures the KV v2 secrets engine is enabled at `secret/`.
   - Note: Sharing the `gitea` PostgreSQL user/database and using the root token via a shared volume are accepted MVP compromises recorded in [backlog.md](../knowledge/backlog.md) for dedicated database isolation and security hardening.

2. **Symbolic Secret Reference Grammar (`${secret(...)}`)**:
   - String configuration fields in `AgentConfig`, `InferenceConfig`, and `ConfigTemplate` accept symbolic secret references:
     - Keyword form: `"${secret(path='/api-key/inference/openrouter', field='value')}"`
     - Positional shorthand: `"${secret('/api-key/inference/openrouter')}"` or `"${secret('/api-key/inference/openrouter', field='value')}"`
   - `field` is optional and defaults to `'value'`.
   - Only string secret values are supported.
   - The `version` parameter is **disallowed** in user-authored configurations (`ConfigTemplate`, `AgentConfig`, `InferenceConfig` saved via API or UI) and rejected by Pydantic validation (`allow_version=False`).

3. **In-Memory Evaluation & Per-Inference Secret Version Watching**:
   - Secret references are evaluated exclusively in memory via `VaultClient` (`src/seamus/vault/`). Cleartext secret values are never written to disk or committed to Git.
   - `SessionAgentRunner` tracks the loaded version of every referenced `(path, field)` in `_loaded_secret_versions: dict[tuple[str, str], int]`.
   - Before each inference run and model invocation (`refresh_secrets` / `refresh_secrets_sync`), the runner queries OpenBao for the current version of each referenced secret path. If `current_version > loaded_version`, the runner automatically reloads the secret value, updates the in-memory `ReasoningChatOpenAI` instance and resolved prompt, and updates `_loaded_secret_versions`.

4. **Checkpoint Explosion for Reproducibility & Future Time-Travel**:
   - Whenever a checkpoint is persisted (`GitCheckpointSaver._save_checkpoint_to_disk` and `GitWorkspaceManager.commit_checkpoint_changes`), every `${secret(...)}` expression in the on-disk `agent/config/config.json` is exploded into its canonical versioned form:
     `"${secret(path='/api-key/inference/openrouter', field='value', version=N)}"`
     explicitly recording `path=`, `field=` (even when default `'value'`), and `version=N` (the version active during the inference preceding that checkpoint).
   - `agent/config` is staged and committed alongside `agent/state`, `artifacts`, and `data` in the checkpoint commit.
   - Meanwhile, the live in-memory `session.config` (and API responses to the UI) remains unversioned so subsequent turns continue watching for newer secret versions. When hydrating sessions from Gitea on startup, any persisted `version=...` parameter in `config.json` is stripped back to unversioned form for the live in-memory session config.

5. **Web UI Surfaces**:
   - **Navigation Sidebar Footer (`Sidebar.tsx`)**: Adds a direct external link button to the OpenBao Web UI token login page (`http://localhost:8200/ui/vault/auth?with=token`) exposed via `GET /api/v-alpha/system/info` (`vault.login_url`).
   - **System Settings -> Secrets Tab (`SettingsModal.tsx`)**: Adds a tabbed navigation (`General` | `Secrets`) in System Settings. The `Secrets` tab provides:
     - OpenBao Login Token reveal (`GET /api/v-alpha/vault/token`) with show/hide, copy token, and "Open OpenBao Login" link.
     - Existing secrets list (`GET /api/v-alpha/vault/secrets`) displaying paths, version badges, and one-click copyable `${secret(...)}` expression pills for each field.
     - Create/Update Secret form (`POST /api/v-alpha/vault/secrets`) with a path input and key-value field editor (defaulting to the `value` field).

## Consequences

- Credentials referenced via `${secret(...)}` never leak into Git repositories (`seamus-system` or `agent-{agent_id}`), while checkpoint commits preserve exact secret version provenance (`version=N`) for future time-travel reproducibility.
- Rotating a secret in OpenBao (or via the System Settings -> Secrets tab) automatically takes effect on the next inference call of running sessions without restarting the session or server.
- Follow-up security hardening (isolated PostgreSQL credentials/instance and comprehensive security review of token handling) is tracked in [backlog.md](../knowledge/backlog.md).

