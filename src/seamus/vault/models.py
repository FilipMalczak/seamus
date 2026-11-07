"""Data models and exceptions for the secrets vault subsystem."""

from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field


class VaultError(Exception):
    """Base exception for secrets vault operations."""


class SecretNotFoundError(VaultError):
    """Raised when a secret path or field cannot be found in the vault."""


class SecretSyntaxError(VaultError):
    """Raised when a secret reference expression has invalid syntax."""


class VaultConnectionError(VaultError):
    """Raised when communication with the vault fails."""


@dataclass(frozen=True)
class SecretReference:
    """Represents a parsed secret reference expression."""

    path: str
    field: str = "value"
    version: int | None = None
    raw_expression: str = ""

    @property
    def normalized_path(self) -> str:
        """Return canonical leading-slash path (e.g. '/api-key/inference/openrouter')."""
        clean = self.path.strip().strip("/")
        return f"/{clean}" if clean else "/"

    def to_exploded_expression(self, resolved_version: int) -> str:
        """Format canonical exploded secret expression with explicit path, field, and version."""
        return (
            f"${{secret(path='{self.normalized_path}', "
            f"field='{self.field}', "
            f"version={resolved_version})}}"
        )

    def to_unversioned_expression(self) -> str:
        """Format secret expression without version parameter."""
        if self.field == "value":
            return f"${{secret('{self.normalized_path}')}}"
        return f"${{secret(path='{self.normalized_path}', field='{self.field}')}}"


@dataclass(frozen=True)
class ResolvedSecretField:
    """Represents a resolved secret string value and its OpenBao version."""

    value: str
    version: int


class VaultSettings(BaseModel):
    """Settings for connecting to the OpenBao vault."""

    base_url: str = Field(
        default="http://localhost:8200",
        description="Internal URL of the OpenBao server.",
    )
    external_url: str = Field(
        default="http://localhost:8200",
        description="Browser-accessible URL of the OpenBao server.",
    )
    token: str | None = Field(
        default=None,
        description="Static authentication token for OpenBao.",
    )
    token_file: Path | None = Field(
        default=None,
        description="Path to a file containing the OpenBao token.",
    )
    mount: str = Field(
        default="secret",
        description="KV v2 secrets engine mount point.",
    )

    @property
    def login_url(self) -> str:
        """Return the browser URL for OpenBao token login page."""
        return f"{self.external_url.rstrip('/')}/ui/vault/auth?with=token"

    def resolve_token(self) -> str | None:
        """Resolve authentication token from explicit token or token file."""
        if self.token and self.token.strip():
            return self.token.strip()
        if self.token_file and self.token_file.is_file():
            try:
                content = self.token_file.read_text(encoding="utf-8").strip()
                if content:
                    return content
            except OSError:
                return None
        return None

    @classmethod
    def from_env(cls) -> "VaultSettings":
        """Load VaultSettings from environment variables."""
        import os

        base_url = os.environ.get("OPENBAO_URL", "http://localhost:8200")
        external_url = os.environ.get("OPENBAO_EXTERNAL_URL", "http://localhost:8200")
        token = os.environ.get("OPENBAO_TOKEN")
        token_file_env = os.environ.get("OPENBAO_TOKEN_FILE")
        token_file = Path(token_file_env) if token_file_env else None
        mount = os.environ.get("OPENBAO_MOUNT", "secret")

        if not token and not token_file:
            default_file = Path("/var/run/seamus-openbao/root_token")
            if default_file.is_file():
                token_file = default_file

        return cls(
            base_url=base_url,
            external_url=external_url,
            token=token,
            token_file=token_file,
            mount=mount,
        )
