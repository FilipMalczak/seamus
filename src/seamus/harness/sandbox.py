"""OpenSandbox backend integration, runtime-managed API key, and sandbox system prompt."""

import contextlib
import logging
import os
import secrets
from datetime import timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import UUID

from langchain_opensandbox import OpenSandboxBackend
from opensandbox import SandboxSync
from opensandbox.config.connection_sync import ConnectionConfigSync
from opensandbox.models.sandboxes import PVC, Host, Volume
from pydantic import BaseModel, Field

from seamus.config.settings import resolve_skill_path
from seamus.harness.prompt import build_scaffold_prompt

logger = logging.getLogger(__name__)

DEFAULT_OPERATIONAL_DIR = "/workspace"
DEFAULT_API_KEY_FILE = Path(".seamus/opensandbox/api_key")
BUNDLED_SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills" / "bundled"


class SandboxSettings(BaseModel):
    """Runtime settings for OpenSandbox server connection and container mounts."""

    domain: str = Field(default_factory=lambda: os.getenv("OPENSANDBOX_DOMAIN", "localhost:8080"))
    protocol: str = Field(default_factory=lambda: os.getenv("OPENSANDBOX_PROTOCOL", "http"))
    image: str = Field(default_factory=lambda: os.getenv("OPENSANDBOX_IMAGE", "python:3.12-slim"))
    timeout: int = Field(default_factory=lambda: int(os.getenv("OPENSANDBOX_TIMEOUT", "300")))
    sandbox_timeout: int = Field(
        default_factory=lambda: int(os.getenv("OPENSANDBOX_SANDBOX_TIMEOUT", "3600"))
    )
    workdir: str = Field(
        default_factory=lambda: os.getenv("OPENSANDBOX_WORKDIR", DEFAULT_OPERATIONAL_DIR)
    )
    workspace_volume: str | None = Field(
        default_factory=lambda: os.getenv("OPENSANDBOX_WORKSPACE_VOLUME", "").strip() or None
    )
    use_server_proxy: bool = Field(
        default_factory=lambda: (
            os.getenv("OPENSANDBOX_USE_SERVER_PROXY", "true").lower() in ("true", "1", "yes")
        )
    )
    api_key_file: Path = Field(
        default_factory=lambda: Path(
            os.getenv("SEAMUS_OPENSANDBOX_KEY_FILE", str(DEFAULT_API_KEY_FILE))
        )
    )


@lru_cache(maxsize=1)
def get_sandbox_settings() -> SandboxSettings:
    """Return cached singleton OpenSandbox settings."""
    return SandboxSettings()


def get_or_create_sandbox_api_key(settings: SandboxSettings | None = None) -> str:
    """Retrieve or autogenerate the runtime-managed OpenSandbox server API key.

    The API key is strictly internal to the runtime and is never exposed to users.
    """
    env_key = os.getenv("OPENSANDBOX_SERVER_API_KEY", "").strip()
    if env_key:
        return env_key

    cfg = settings or get_sandbox_settings()
    key_path = cfg.api_key_file

    if key_path.exists():
        existing = key_path.read_text(encoding="utf-8").strip()
        if existing:
            return existing

    key_path.parent.mkdir(parents=True, exist_ok=True)
    generated = secrets.token_urlsafe(32)
    key_path.write_text(f"{generated}\n", encoding="utf-8")
    with contextlib.suppress(OSError):
        key_path.chmod(0o600)
    return generated


def build_sandbox_system_prompt(operational_dir: str = DEFAULT_OPERATIONAL_DIR) -> str:
    """Construct the XML-formatted sandbox scaffolding prompt via seamus.harness.prompt."""
    return build_scaffold_prompt(operational_dir)


class SeamusOpenSandboxBackend(OpenSandboxBackend):  # type: ignore[misc]
    """Session-scoped OpenSandboxBackend with lazy container provisioning and volume mounting."""

    def __init__(
        self,
        *,
        agent_id: UUID,
        session_id: UUID,
        data_dir: Path,
        artifacts_dir: Path | None = None,
        notes_dir: Path | None = None,
        workspace_readonly: bool = False,
        notes_mounted: bool = False,
        notes_readonly: bool = True,
        settings: SandboxSettings | None = None,
        skill_directories: list[str] | None = None,
        sandbox: SandboxSync | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.session_id = session_id
        self.data_dir = data_dir
        self.artifacts_dir = artifacts_dir or (data_dir.parent / "artifacts")
        self.notes_dir = notes_dir or (data_dir / "notes")
        self.workspace_readonly = workspace_readonly
        self.notes_mounted = notes_mounted
        self.notes_readonly = notes_readonly
        self.settings = settings or get_sandbox_settings()
        self.skill_directories = skill_directories if skill_directories is not None else []
        self._active_sandbox: SandboxSync | None = sandbox
        super().__init__(sandbox=sandbox, timeout=self.settings.timeout)

    def reconfigure_mounts(
        self,
        *,
        workspace_readonly: bool,
        notes_mounted: bool = False,
        notes_readonly: bool = True,
    ) -> None:
        """Update volume mount flags and recycle the active sandbox if flags changed."""
        changed = (
            self.workspace_readonly != workspace_readonly
            or self.notes_mounted != notes_mounted
            or self.notes_readonly != notes_readonly
        )
        self.workspace_readonly = workspace_readonly
        self.notes_mounted = notes_mounted
        self.notes_readonly = notes_readonly
        if changed and self._active_sandbox is not None:
            logger.info(
                "Reconfiguring OpenSandbox mounts for session %s "
                "(workspace_ro=%s, notes_mounted=%s, notes_ro=%s)",
                self.session_id,
                workspace_readonly,
                notes_mounted,
                notes_readonly,
            )
            self.destroy()

    @property
    def _sandbox(self) -> SandboxSync:
        """Lazily initialize and return the underlying OpenSandbox SandboxSync instance."""
        return self._ensure_sandbox()

    @_sandbox.setter
    def _sandbox(self, value: SandboxSync | None) -> None:
        self._active_sandbox = value

    def build_workspace_volume(self) -> Volume:
        """Build the OpenSandbox Volume mounting only the session's data/ directory."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if self.settings.workspace_volume:
            return Volume(
                name="workspace",
                mountPath=self.settings.workdir,
                readOnly=self.workspace_readonly,
                pvc=PVC(
                    claimName=self.settings.workspace_volume,
                    createIfNotExists=True,
                    deleteOnSandboxTermination=False,
                ),
                subPath=f"{self.agent_id}/{self.session_id}/data",
            )
        return Volume(
            name="workspace",
            mountPath=self.settings.workdir,
            readOnly=self.workspace_readonly,
            host=Host(path=str(self.data_dir.resolve())),
        )

    def build_notes_volume(self) -> Volume | None:
        """Build the OpenSandbox Volume mounting the session's notes/ directory when enabled."""
        if not self.notes_mounted:
            return None
        self.notes_dir.mkdir(parents=True, exist_ok=True)
        if self.settings.workspace_volume:
            return Volume(
                name="notes",
                mountPath="/workspace/notes",
                readOnly=self.notes_readonly,
                pvc=PVC(
                    claimName=self.settings.workspace_volume,
                    createIfNotExists=True,
                    deleteOnSandboxTermination=False,
                ),
                subPath=f"{self.agent_id}/{self.session_id}/data/notes",
            )
        return Volume(
            name="notes",
            mountPath="/workspace/notes",
            readOnly=self.notes_readonly,
            host=Host(path=str(self.notes_dir.resolve())),
        )

    def build_artifact_volume(self) -> Volume:
        """Build the read-only OpenSandbox Volume mounting the session's artifacts/ directory."""
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        if self.settings.workspace_volume:
            return Volume(
                name="artifacts",
                mountPath="/artifacts",
                readOnly=True,
                pvc=PVC(
                    claimName=self.settings.workspace_volume,
                    createIfNotExists=True,
                    deleteOnSandboxTermination=False,
                ),
                subPath=f"{self.agent_id}/{self.session_id}/artifacts",
            )
        return Volume(
            name="artifacts",
            mountPath="/artifacts",
            readOnly=True,
            host=Host(path=str(self.artifacts_dir.resolve())),
        )

    def build_bundled_skill_volume(self) -> Volume | None:
        """Build read-only OpenSandbox Volume for built-in platform skills if present."""
        if BUNDLED_SKILLS_DIR.is_dir():
            return Volume(
                name="skills-bundled",
                mountPath="/skills/bundled",
                readOnly=True,
                host=Host(path=str(BUNDLED_SKILLS_DIR.resolve())),
            )
        return None

    def build_skill_volumes(self) -> list[Volume]:
        """Build read-only OpenSandbox Volumes for system-wide skill directories.

        Each configured system skill directory is mounted at `/skills/system/{idx}`,
        where `idx` matches its 0-based position in `self.skill_directories`.
        Non-existent directories are cleanly skipped while preserving index mapping.
        """
        volumes: list[Volume] = []
        for idx, skill_dir_str in enumerate(self.skill_directories):
            skill_path = resolve_skill_path(skill_dir_str)
            if skill_path is None:
                # Non-existent or invalid directories are cleanly skipped
                continue
            volumes.append(
                Volume(
                    name=f"skill-{idx}",
                    mountPath=f"/skills/system/{idx}",
                    readOnly=True,
                    host=Host(path=str(skill_path)),
                )
            )
        return volumes

    def get_skill_sources(self) -> list[tuple[str, str]]:
        """Return the prioritized list of in-sandbox skill sources for DeepAgents.

        DeepAgents resolves skill collisions with 'last one wins' (later sources in the
        list override earlier ones). To enforce the precedence hierarchy:
        1. /workspace/skills (top priority: explicit session workspace skills)
        2. /workspace/.skills (session background/default skills)
        3. system[0] (highest priority system default, mounted at /skills/system/0)
        4. system[1] ...
        5. system[last] (lowest priority system default)

        The source list is ordered from lowest to highest priority:
        [
            system[last],
            ...,
            system[1],
            system[0],
            ("/workspace/.skills", "Session (.skills)"),
            ("/workspace/skills", "Session"),
        ]
        """
        system_sources: list[tuple[str, str]] = []
        for idx, skill_dir_str in enumerate(self.skill_directories):
            skill_path = resolve_skill_path(skill_dir_str)
            if skill_path is None:
                continue
            label = f"System #{idx}" if len(self.skill_directories) > 1 else "System"
            system_sources.append((f"/skills/system/{idx}", label))

        # Reverse system sources: system[last] lowest priority, system[0] highest among system
        sources: list[tuple[str, str]] = list(reversed(system_sources))

        # Append session workspace skills (dotted first, non-dotted last so non-dotted wins)
        sources.append((f"{self.settings.workdir}/.skills", "Session (.skills)"))
        sources.append((f"{self.settings.workdir}/skills", "Session"))

        # Append bundled platform skills (top-most priority, wins against all collisions)
        if BUNDLED_SKILLS_DIR.is_dir():
            sources.append(("/skills/bundled", "Bundled"))

        return sources

    def build_connection_config(self) -> ConnectionConfigSync:
        """Build the OpenSandbox SDK connection configuration with runtime-managed auth."""
        api_key = get_or_create_sandbox_api_key(self.settings)
        return ConnectionConfigSync(
            domain=self.settings.domain,
            protocol=self.settings.protocol,
            api_key=api_key,
            use_server_proxy=self.settings.use_server_proxy,
        )

    def _ensure_sandbox(self) -> SandboxSync:
        """Create the remote OpenSandbox container if not already active."""
        if self._active_sandbox is None:
            connection_config = self.build_connection_config()
            workspace_volume = self.build_workspace_volume()
            artifact_volume = self.build_artifact_volume()
            notes_volume = self.build_notes_volume()
            bundled_volume = self.build_bundled_skill_volume()
            skill_volumes = self.build_skill_volumes()
            all_volumes = [
                workspace_volume,
                artifact_volume,
                *([notes_volume] if notes_volume is not None else []),
                *([bundled_volume] if bundled_volume is not None else []),
                *skill_volumes,
            ]
            logger.info(
                "Creating OpenSandbox (image=%s, domain=%s, mount=%s, skills=%d) for session %s",
                self.settings.image,
                self.settings.domain,
                self.settings.workdir,
                len(skill_volumes) + (1 if bundled_volume else 0),
                self.session_id,
            )
            self._active_sandbox = SandboxSync.create(
                self.settings.image,
                connection_config=connection_config,
                volumes=all_volumes,
                timeout=timedelta(seconds=self.settings.sandbox_timeout),
                metadata={
                    "seamus.agent_id": str(self.agent_id),
                    "seamus.session_id": str(self.session_id),
                },
            )
        return self._active_sandbox

    def destroy(self) -> None:
        """Terminate the remote sandbox container and release local HTTP resources."""
        if self._active_sandbox is not None:
            try:
                self._active_sandbox.destroy()
            except Exception:
                logger.exception("Failed to destroy OpenSandbox for session %s", self.session_id)
            finally:
                self._active_sandbox = None

    def close(self) -> None:
        """Close local HTTP resources without terminating the remote sandbox."""
        if self._active_sandbox is not None:
            try:
                self._active_sandbox.close()
            except Exception:
                logger.exception(
                    "Failed to close OpenSandbox transport for session %s", self.session_id
                )

    def __repr__(self) -> str:
        active_id: Any = self._active_sandbox.id if self._active_sandbox is not None else None
        return (
            f"SeamusOpenSandboxBackend(agent_id={self.agent_id!r}, "
            f"session_id={self.session_id!r}, workdir={self.settings.workdir!r}, "
            f"sandbox_id={active_id!r})"
        )
