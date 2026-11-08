# 0043. Dedicated First-Party Developer Sandbox Container Image & Per-Agent Image Configuration

Date: 2026-11-08

## Status

Accepted

## Context

In task [0042](0042-mount-external-git-repositories.md), Seamus established a dedicated Ubuntu 24.04-based container image (`opensandbox/Dockerfile.sandbox`, tagged `seamus-sandbox:latest`) to resolve missing `python3` runtime dependencies for DeepAgents file tools and provide `git` for external repository operations.

However, a productive coding agent developer environment requires broader foundational tooling beyond minimal `python3` and `git`:
1. **Core Developer Runtimes**: Standard coding workflows expect Astral `uv` / `uvx`, `python3-pip`, `python3-venv`, Node.js (LTS) + `npm`, `build-essential` (gcc, make, etc.), `curl`, `wget`, `jq`, `tree`, and `procps`.
2. **Declarative Environment Introspection**: The agent and operators need a reliable way to inspect pre-installed capabilities without guessing or running trial-and-error shell checks.
3. **Per-Agent/Session Customization**: Different agent tasks may require specialized environments or domain-specific container images while defaulting gracefully to the platform's `seamus-sandbox:latest` (or `OPENSANDBOX_IMAGE`).

## Decision

1. **Enhanced First-Party Sandbox Image (`opensandbox/Dockerfile.sandbox`)**:
   - Built on `ubuntu:24.04`.
   - Copies pre-compiled Astral `uv` and `uvx` binaries directly from `ghcr.io/astral-sh/uv:latest`.
   - Installs `python3`, `python3-pip`, `python3-venv`, `nodejs`, `npm`, `git`, `ca-certificates`, `curl`, `wget`, `jq`, `tree`, `build-essential`, `less`, and `procps`.
   - Embeds a machine-readable capability manifest at `/etc/seamus-sandbox.json` documenting the image name, base distro, and installed runtimes.
   - Embeds the source `Dockerfile.sandbox` at `/etc/seamus-sandbox.dockerfile` for full in-container provenance.

2. **Per-Agent/Session Sandbox Image Configuration**:
   - Add `sandbox_image: str | None = None` to `AgentConfig`.
   - In `AgentConfig.copy_with_overrides`, preserve or override `sandbox_image` across template, agent, and session derivation hierarchies.
   - Support symbolic secret references in `sandbox_image` if dynamically configured.
   - In `SessionAgentRunner._init_agent()`, if `session.config.sandbox_image` is configured, override the runtime `SandboxSettings.image` passed to `SeamusOpenSandboxBackend`. When `None`, execution defaults to `SandboxSettings.image` (`OPENSANDBOX_IMAGE`, defaulting to `seamus-sandbox:latest`).

3. **Web UI Support**:
   - Expose an optional `Sandbox Container Image` field in the Agent Configuration Modal (`ConfigModal.tsx`), allowing developers to specify a custom sandbox image or reset to the platform default.

## Consequences

- Sandboxed agents immediately have access to modern Python (`uv`, `pip`, `venv`), Node.js (`npm`), and C/C++ build tooling out of the box without runtime setup delay.
- In-container introspection via `/etc/seamus-sandbox.json` provides transparent visibility into environment capabilities.
- Advanced users can configure specialized container images per agent/session without modifying global server environment variables.

