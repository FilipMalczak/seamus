"""OpenBao secrets vault integration for symbolic secret references and interpolation."""

from seamus.vault.client import (
    VaultClient,
    get_default_vault_client,
    reset_default_vault_client,
)
from seamus.vault.interpolator import (
    collect_secret_references,
    explode_secret_references,
    explode_secret_string,
    resolve_secret_string,
    resolve_secret_string_sync,
    resolve_secret_string_with_versions,
    resolve_secret_string_with_versions_sync,
    resolve_secrets,
    resolve_secrets_sync,
    resolve_secrets_with_versions,
    resolve_secrets_with_versions_sync,
    strip_secret_versions,
    strip_secret_versions_from_string,
    validate_secret_expressions,
)
from seamus.vault.models import (
    ResolvedSecretField,
    SecretNotFoundError,
    SecretReference,
    SecretSyntaxError,
    VaultConnectionError,
    VaultError,
    VaultSettings,
)
from seamus.vault.parser import (
    find_secret_references,
    has_secret_references,
    parse_secret_reference,
)

__all__ = [
    "ResolvedSecretField",
    "SecretNotFoundError",
    "SecretReference",
    "SecretSyntaxError",
    "VaultClient",
    "VaultConnectionError",
    "VaultError",
    "VaultSettings",
    "collect_secret_references",
    "explode_secret_references",
    "explode_secret_string",
    "find_secret_references",
    "get_default_vault_client",
    "has_secret_references",
    "parse_secret_reference",
    "reset_default_vault_client",
    "resolve_secret_string",
    "resolve_secret_string_sync",
    "resolve_secret_string_with_versions",
    "resolve_secret_string_with_versions_sync",
    "resolve_secrets",
    "resolve_secrets_sync",
    "resolve_secrets_with_versions",
    "resolve_secrets_with_versions_sync",
    "strip_secret_versions",
    "strip_secret_versions_from_string",
    "validate_secret_expressions",
]
