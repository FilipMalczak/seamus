"""Recursive resolver, validator, and checkpoint exploder for secret reference expressions."""

from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel

from seamus.vault.client import VaultClient, get_default_vault_client
from seamus.vault.models import SecretReference
from seamus.vault.parser import find_secret_references


def collect_secret_references(
    obj: Any,
    *,
    allow_version: bool = True,
) -> list[SecretReference]:
    """Recursively collect SecretReference occurrences across strings, collections, and models."""
    refs: list[SecretReference] = []

    if isinstance(obj, str):
        for _, ref in find_secret_references(obj, allow_version=allow_version):
            refs.append(ref)
        return refs

    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str):
                refs.extend(collect_secret_references(k, allow_version=allow_version))
            refs.extend(collect_secret_references(v, allow_version=allow_version))
        return refs

    if isinstance(obj, (list, tuple, set)):
        for item in obj:
            refs.extend(collect_secret_references(item, allow_version=allow_version))
        return refs

    if isinstance(obj, BaseModel):
        for field_name in type(obj).model_fields:
            val = getattr(obj, field_name)
            refs.extend(collect_secret_references(val, allow_version=allow_version))
        return refs

    return refs


def validate_secret_expressions(
    obj: Any,
    *,
    allow_version: bool = False,
) -> None:
    """Validate syntax of all ${secret(...)} expressions in obj.

    Raises:
        SecretSyntaxError: If any secret reference has invalid syntax or disallowed version.
    """
    collect_secret_references(obj, allow_version=allow_version)


async def resolve_secret_string_with_versions(
    text: str,
    client: VaultClient | None = None,
) -> tuple[str, dict[tuple[str, str], int]]:
    """Resolve all ${secret(...)} references inside a string and return used version map."""
    matches = find_secret_references(text, allow_version=True)
    if not matches:
        return text, {}

    resolved_text = text
    versions: dict[tuple[str, str], int] = {}
    vault_client = client or get_default_vault_client()
    for full_expr, ref in matches:
        res = await vault_client.get_secret_field_with_version(
            path=ref.path,
            field=ref.field,
            version=ref.version,
        )
        resolved_text = resolved_text.replace(full_expr, res.value, 1)
        versions[(ref.normalized_path, ref.field)] = res.version

    return resolved_text, versions


async def resolve_secret_string(text: str, client: VaultClient | None = None) -> str:
    """Resolve all ${secret(...)} references inside a string."""
    resolved, _ = await resolve_secret_string_with_versions(text, client=client)
    return resolved


async def resolve_secrets_with_versions[T](
    obj: T,
    client: VaultClient | None = None,
) -> tuple[T, dict[tuple[str, str], int]]:
    """Recursively resolve secret references and return (resolved_obj, version_map).

    version_map maps (normalized_path, field) -> resolved_version.
    """
    vault_client = client or get_default_vault_client()
    versions: dict[tuple[str, str], int] = {}

    if isinstance(obj, str):
        res_str, str_vers = await resolve_secret_string_with_versions(obj, vault_client)
        return res_str, str_vers  # type: ignore[return-value]

    if isinstance(obj, dict):
        resolved_dict: dict[Any, Any] = {}
        for k, v in obj.items():
            if isinstance(k, str):
                resolved_k, k_vers = await resolve_secrets_with_versions(k, vault_client)
                versions.update(k_vers)
            else:
                resolved_k = k
            resolved_v, v_vers = await resolve_secrets_with_versions(v, vault_client)
            versions.update(v_vers)
            resolved_dict[resolved_k] = resolved_v
        return resolved_dict, versions  # type: ignore[return-value]

    if isinstance(obj, list):
        resolved_list: list[Any] = []
        for item in obj:
            res_item, item_vers = await resolve_secrets_with_versions(item, vault_client)
            versions.update(item_vers)
            resolved_list.append(res_item)
        return resolved_list, versions  # type: ignore[return-value]

    if isinstance(obj, tuple):
        resolved_tuple_items: list[Any] = []
        for item in obj:
            res_item, item_vers = await resolve_secrets_with_versions(item, vault_client)
            versions.update(item_vers)
            resolved_tuple_items.append(res_item)
        return tuple(resolved_tuple_items), versions  # type: ignore[return-value]

    if isinstance(obj, set):
        resolved_set: set[Any] = set()
        for item in obj:
            res_item, item_vers = await resolve_secrets_with_versions(item, vault_client)
            versions.update(item_vers)
            resolved_set.add(res_item)
        return resolved_set, versions  # type: ignore[return-value]

    if isinstance(obj, BaseModel):
        resolved_fields: dict[str, Any] = {}
        for field_name in type(obj).model_fields:
            val = getattr(obj, field_name)
            res_val, f_vers = await resolve_secrets_with_versions(val, vault_client)
            versions.update(f_vers)
            resolved_fields[field_name] = res_val
        return type(obj).model_validate(resolved_fields), versions

    return obj, versions


async def resolve_secrets[T](obj: T, client: VaultClient | None = None) -> T:
    """Recursively resolve secret references in strings, dicts, lists, and Pydantic models."""
    resolved, _ = await resolve_secrets_with_versions(obj, client=client)
    return resolved


def resolve_secret_string_with_versions_sync(
    text: str,
    client: VaultClient | None = None,
) -> tuple[str, dict[tuple[str, str], int]]:
    """Synchronously resolve all ${secret(...)} references in a string and return version map."""
    matches = find_secret_references(text, allow_version=True)
    if not matches:
        return text, {}

    resolved_text = text
    versions: dict[tuple[str, str], int] = {}
    vault_client = client or get_default_vault_client()
    for full_expr, ref in matches:
        res = vault_client.get_secret_field_with_version_sync(
            path=ref.path,
            field=ref.field,
            version=ref.version,
        )
        resolved_text = resolved_text.replace(full_expr, res.value, 1)
        versions[(ref.normalized_path, ref.field)] = res.version

    return resolved_text, versions


def resolve_secret_string_sync(text: str, client: VaultClient | None = None) -> str:
    """Synchronously resolve all ${secret(...)} references inside a string."""
    resolved, _ = resolve_secret_string_with_versions_sync(text, client=client)
    return resolved


def resolve_secrets_with_versions_sync[T](
    obj: T,
    client: VaultClient | None = None,
) -> tuple[T, dict[tuple[str, str], int]]:
    """Synchronously resolve secret references and return (resolved_obj, version_map)."""
    vault_client = client or get_default_vault_client()
    versions: dict[tuple[str, str], int] = {}

    if isinstance(obj, str):
        res_str, str_vers = resolve_secret_string_with_versions_sync(obj, vault_client)
        return res_str, str_vers  # type: ignore[return-value]

    if isinstance(obj, dict):
        resolved_dict: dict[Any, Any] = {}
        for k, v in obj.items():
            if isinstance(k, str):
                resolved_k, k_vers = resolve_secrets_with_versions_sync(k, vault_client)
                versions.update(k_vers)
            else:
                resolved_k = k
            resolved_v, v_vers = resolve_secrets_with_versions_sync(v, vault_client)
            versions.update(v_vers)
            resolved_dict[resolved_k] = resolved_v
        return resolved_dict, versions  # type: ignore[return-value]

    if isinstance(obj, list):
        resolved_list: list[Any] = []
        for item in obj:
            res_item, item_vers = resolve_secrets_with_versions_sync(item, vault_client)
            versions.update(item_vers)
            resolved_list.append(res_item)
        return resolved_list, versions  # type: ignore[return-value]

    if isinstance(obj, tuple):
        resolved_tuple_items: list[Any] = []
        for item in obj:
            res_item, item_vers = resolve_secrets_with_versions_sync(item, vault_client)
            versions.update(item_vers)
            resolved_tuple_items.append(res_item)
        return tuple(resolved_tuple_items), versions  # type: ignore[return-value]

    if isinstance(obj, set):
        resolved_set: set[Any] = set()
        for item in obj:
            res_item, item_vers = resolve_secrets_with_versions_sync(item, vault_client)
            versions.update(item_vers)
            resolved_set.add(res_item)
        return resolved_set, versions  # type: ignore[return-value]

    if isinstance(obj, BaseModel):
        resolved_fields: dict[str, Any] = {}
        for field_name in type(obj).model_fields:
            val = getattr(obj, field_name)
            res_val, f_vers = resolve_secrets_with_versions_sync(val, vault_client)
            versions.update(f_vers)
            resolved_fields[field_name] = res_val
        return type(obj).model_validate(resolved_fields), versions

    return obj, versions


def resolve_secrets_sync[T](obj: T, client: VaultClient | None = None) -> T:
    """Synchronously recursively resolve secret references in data structures and models."""
    resolved, _ = resolve_secrets_with_versions_sync(obj, client=client)
    return resolved


def explode_secret_string(
    text: str,
    version_map: Mapping[Any, int],
    default_version: int = 1,
) -> str:
    """Rewrite ${secret(...)} expressions in text into canonical exploded form with version.

    Produces: ${secret(path='...', field='...', version=N)}
    """
    matches = find_secret_references(text, allow_version=True)
    if not matches:
        return text

    result = text
    for full_expr, ref in matches:
        norm = ref.normalized_path
        clean = norm.lstrip("/")
        ver = (
            version_map.get((norm, ref.field))
            or version_map.get((clean, ref.field))
            or version_map.get((ref.path, ref.field))
            or version_map.get(f"{norm}:{ref.field}")
            or version_map.get(f"{clean}:{ref.field}")
            or ref.version
            or default_version
        )
        exploded = ref.to_exploded_expression(ver)
        result = result.replace(full_expr, exploded, 1)
    return result


def get_secret_versions_for_references_sync(
    refs: Sequence[SecretReference],
    version_map: Mapping[Any, int] | None = None,
    client: VaultClient | None = None,
) -> dict[tuple[str, str], int]:
    """Resolve or lookup secret versions for a sequence of SecretReferences."""
    result: dict[tuple[str, str], int] = {}
    if version_map:
        for k, v in version_map.items():
            if isinstance(k, tuple) and len(k) == 2:
                norm_path = f"/{str(k[0]).strip().lstrip('/')}"
                result[(norm_path, str(k[1]))] = int(v)
            elif isinstance(k, str) and ":" in k:
                p, f = k.split(":", 1)
                norm_path = f"/{p.strip().lstrip('/')}"
                result[(norm_path, f)] = int(v)

    vault_client = None
    for ref in refs:
        norm_key = (ref.normalized_path, ref.field)
        if norm_key in result:
            continue
        if ref.version is not None:
            result[norm_key] = ref.version
            continue
        if vault_client is None:
            vault_client = client or get_default_vault_client()
        try:
            meta = vault_client.get_secret_metadata_sync(ref.path)
            result[norm_key] = int(meta.get("current_version") or 1)
        except Exception:
            try:
                _, ver = vault_client.get_secret_with_version_sync(ref.path)
                result[norm_key] = ver
            except Exception:
                result[norm_key] = 1
    return result


def explode_secret_references[T](
    obj: T,
    version_map: Mapping[Any, int],
    default_version: int = 1,
) -> T:
    """Recursively rewrite ${secret(...)} references in obj into exploded versioned form.

    Note: When obj is a BaseModel, returns a dict via model_dump() with exploded strings,
    or if dict/list/str, returns the same type with exploded strings, suitable for
    checkpoint JSON serialization without triggering user-config version= disallowance.
    """
    if isinstance(obj, str):
        return explode_secret_string(obj, version_map, default_version=default_version)  # type: ignore[return-value]

    if isinstance(obj, dict):
        return {
            (
                explode_secret_references(k, version_map, default_version=default_version)
                if isinstance(k, str)
                else k
            ): explode_secret_references(v, version_map, default_version=default_version)
            for k, v in obj.items()
        }  # type: ignore[return-value]

    if isinstance(obj, list):
        return [
            explode_secret_references(item, version_map, default_version=default_version)
            for item in obj
        ]  # type: ignore[return-value]

    if isinstance(obj, tuple):
        return tuple(
            explode_secret_references(item, version_map, default_version=default_version)
            for item in obj
        )  # type: ignore[return-value]

    if isinstance(obj, BaseModel):
        dumped = obj.model_dump()
        exploded_dict = explode_secret_references(
            dumped,
            version_map,
            default_version=default_version,
        )
        return type(obj).model_construct(
            **{
                k: (
                    explode_secret_references(
                        getattr(obj, k),
                        version_map,
                        default_version=default_version,
                    )
                    if isinstance(getattr(obj, k), BaseModel)
                    else v
                )
                for k, v in exploded_dict.items()
            }
        )

    return obj


def strip_secret_versions_from_string(text: str) -> str:
    """Strip any 'version=...' argument from ${secret(...)} expressions in text."""
    matches = find_secret_references(text, allow_version=True)
    if not matches:
        return text

    result = text
    for full_expr, ref in matches:
        if ref.version is not None:
            result = result.replace(full_expr, ref.to_unversioned_expression(), 1)
    return result


def strip_secret_versions[T](obj: T) -> T:
    """Recursively strip 'version=...' from secret expressions in raw dicts/lists/strings."""
    if isinstance(obj, str):
        return strip_secret_versions_from_string(obj)  # type: ignore[return-value]

    if isinstance(obj, dict):
        return {
            (strip_secret_versions(k) if isinstance(k, str) else k): strip_secret_versions(v)
            for k, v in obj.items()
        }  # type: ignore[return-value]

    if isinstance(obj, list):
        return [strip_secret_versions(item) for item in obj]  # type: ignore[return-value]

    return obj
