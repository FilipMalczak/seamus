# 0045. Ollama Local Model Provider Support & Active Model Execution Management

Date: 2026-11-08

## Status

Accepted

## Context

Seamus previously assumed inference APIs followed standard cloud-hosted OpenAI/OpenRouter conventions requiring mandatory API keys.

To enable completely offline, private, and zero-cost local LLM development workflows, first-class support for Ollama as a local model provider was needed. However:
1. **Background Service Assumption**: Ollama can be assumed to run as a background service/daemon (e.g. `http://localhost:11434`), verified via an HTTP healthcheck.
2. **Active Model Management**: Unlike cloud endpoints where models are always loaded and ready on remote servers, local Ollama instances do not necessarily have the desired model loaded in memory, or the model might not exist. Running the target model on the local instance must be managed actively by Seamus, not assumed.
3. **No Mandatory API Keys**: Local model execution does not require external API keys. Configuration validation must treat API keys as optional when targeting Ollama.

## Decision

1. **Inference Configuration & Format (`src/seamus/config/models.py`)**:
   - Add `OLLAMA = "ollama"` to `InferenceFormat`.
   - In `InferenceConfig.is_complete()` and `AgentConfig.validate_complete()`, relax the requirement for `api_key` when `format == InferenceFormat.OLLAMA` or when `base_url` points to an Ollama instance (port `11434`).
   - Allow agents targeting Ollama to initialize with `api_key: None`.

2. **Ollama Healthcheck, Container Networking & Active Model Execution Management (`src/seamus/harness/runner.py`, `docker-compose.yml`, `src/seamus/server/routes/sessions.py`)**:
   - In `docker-compose.yml`, add `extra_hosts: ["host.docker.internal:host-gateway"]` to the `backend` service container.
2. **Containerized Ollama (CPU Mode), Networking & Active Model Management (`src/seamus/harness/runner.py`, `docker-compose.yml`, `src/seamus/server/routes/sessions.py`)**:
   - In `docker-compose.yml`, add an `ollama` service running `ollama/ollama:latest` in CPU mode with named volume `ollama-data:/root/.ollama` and healthcheck, and add `extra_hosts: ["host.docker.internal:host-gateway"]` to the `backend` container.
   - In `_ensure_ollama_model(base_url: str, model_name: str) -> str`:
     - Parses the Ollama root host (e.g. `http://localhost:11434`).
     - If `base_url` points to `localhost` or `127.0.0.1`, builds fallback candidate endpoints: the internal Docker service (`http://ollama:11434`) followed by the host gateway (`http://host.docker.internal:11434`).
     - Performs an HTTP healthcheck against `{ollama_base}/api/generate` with payload `{"model": model_name}`.
     - If `base_url` points to `localhost` or `127.0.0.1` and fails with connection refused inside Docker, automatically attempts fallback to `host.docker.internal` and returns the working effective URL.
     - If the Ollama daemon is unreachable on both, raises a detailed `RuntimeError` advising that Ollama must be running and listening on all interfaces (`OLLAMA_HOST=0.0.0.0`) when Seamus runs inside Docker.
     - If Ollama reports an error (e.g. model not found), raises `RuntimeError("Failed to run model '{model_name}' on Ollama: {error}")`.
     - Confirms the model is actively loaded into memory and ready for generation.
     - If the model is not found, automatically triggers `POST {ollama_base}/api/pull` (`stream: False`) to fetch the model into Ollama before retrying the memory load request.
     - Confirms the model is actively loaded into memory and returns the working effective URL.
   - In `src/seamus/server/routes/sessions.py`, map `RuntimeError` on runner initialization to HTTP 400 Bad Request with clear diagnostics, preventing unhandled 500 server errors.
   - In `ui/src/api/client.ts`, surface response error details in SSE connection error toasts.
   - When initializing `ReasoningChatOpenAI` in `_build_deep_agent()` or refreshing in `_apply_resolved_config_to_llm()`:
     - Automatically trigger `_ensure_ollama_model` if `format == InferenceFormat.OLLAMA` or `"11434"` in `base_url`.
     - Normalize base URLs missing `/v1` to `{base_url}/v1` for OpenAI client compatibility.
     - Supply a fallback API key string (`"ollama"`) when `api_key` is unset so LangChain's client initializes cleanly without requiring dummy secrets in OpenBao.
   - Defer GPU passthrough / NVIDIA Container Toolkit acceleration to the backlog ([backlog.md](../knowledge/backlog.md)).

3. **Web UI Support (`ui/src/components/ConfigModal.tsx`, `ui/src/api/types.ts`)**:
   - Add `"ollama"` to the `InferenceConfig.format` type union.
   - Add `Ollama` (`http://localhost:11434/v1`) to `BASE_URL_PRESETS`.
   - Add `ollama (Local Ollama)` to the format selection dropdown.
   - Add local model presets (`gemma4:e4b`, `llama3.2:3b`, `qwen3.8:latest`) to `MODEL_PRESETS`.

## Consequences

- Agents can execute fully offline against local Ollama models with zero external API key requirements.
- Seamus actively guarantees the target model is loaded in memory before inference begins, failing fast with informative diagnostics if Ollama is not running or the model is missing.
- Reusable presets in the UI enable one-click switching between local Ollama models and cloud inference providers.

