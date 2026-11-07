"""Parser for secret reference expressions like ${secret(path='/path', field='...')}."""

import re

from seamus.vault.models import SecretReference, SecretSyntaxError

# Pattern to locate ${secret(...)} blocks inside a string (with optional whitespace)
_SECRET_PATTERN = re.compile(
    r"\$\{\s*secret\((?P<content>.*?)\)\s*\}",
    re.DOTALL,
)

# Pattern to parse either a positional quoted string or a key=value argument
_FIRST_ARG_PATTERN = re.compile(
    r"^\s*(?:(?P<key>[a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*)?"
    r"(?:(?P<quote>['\"])(?P<str_val>[^'\"]*)(?P=quote)|(?P<num_val>\d+))"
    r"(?P<remainder>.*)$",
    re.DOTALL,
)

_KWARG_PATTERN = re.compile(
    r"\s*,\s*(?P<key>[a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*"
    r"(?:(?P<quote>['\"])(?P<str_val>[^'\"]*)(?P=quote)|(?P<num_val>\d+))\s*",
)


def parse_secret_reference(
    expression: str,
    *,
    allow_version: bool = True,
) -> SecretReference:
    """Parse a single secret reference expression string.

    Supports:
    - ${secret('/path/to/secret')}
    - ${secret(path='/path/to/secret')}
    - ${secret('/path/to/secret', field='value')}
    - ${secret(path='/path/to/secret', field='value')}
    - ${secret(path='/path/to/secret', field='value', version=2)} (when allow_version=True)

    Args:
        expression: Expression like "${secret(path='/path/to/key', field='value')}"
                    or the inner "secret(...)" call.
        allow_version: Whether the 'version' argument is permitted in this context.

    Returns:
        Parsed SecretReference.

    Raises:
        SecretSyntaxError: If the expression syntax is invalid or version is disallowed.
    """
    raw = expression.strip()
    match = _SECRET_PATTERN.fullmatch(raw)
    if match:
        inner = match.group("content").strip()
    elif raw.startswith("secret(") and raw.endswith(")"):
        inner = raw[len("secret(") : -1].strip()
    else:
        msg = f"Invalid secret reference format: {expression!r}"
        raise SecretSyntaxError(msg)

    if not inner:
        msg = f"Empty secret reference in expression: {expression!r}"
        raise SecretSyntaxError(msg)

    first_match = _FIRST_ARG_PATTERN.match(inner)
    if not first_match:
        msg = f"Missing or invalid secret arguments in expression: {expression!r}"
        raise SecretSyntaxError(msg)

    path: str | None = None
    field = "value"
    version: int | None = None
    seen_keys: set[str] = set()

    def _apply_arg(key: str | None, str_val: str | None, num_val: str | None) -> None:
        nonlocal path, field, version
        if key is None:
            if str_val is None or not str_val.strip():
                msg = f"Secret path must be a non-empty string in {expression!r}"
                raise SecretSyntaxError(msg)
            path = str_val
            seen_keys.add("path")
            return

        if key in seen_keys:
            msg = f"Duplicate argument {key!r} in secret reference {expression!r}"
            raise SecretSyntaxError(msg)
        seen_keys.add(key)

        if key == "path":
            if str_val is None or not str_val.strip():
                msg = f"Secret path must be a non-empty string in {expression!r}"
                raise SecretSyntaxError(msg)
            path = str_val
        elif key == "field":
            if str_val is None or not str_val.strip():
                msg = f"Field argument must be a non-empty string in {expression!r}"
                raise SecretSyntaxError(msg)
            field = str_val
        elif key == "version":
            if not allow_version:
                msg = (
                    f"The 'version' parameter is disallowed in user configurations "
                    f"(found in {expression!r}). Versions are managed automatically "
                    f"and recorded only in checkpoint commits."
                )
                raise SecretSyntaxError(msg)
            if num_val is None:
                msg = f"Version argument must be an integer in {expression!r}"
                raise SecretSyntaxError(msg)
            version = int(num_val)
            if version < 1:
                msg = f"Version argument must be a positive integer in {expression!r}"
                raise SecretSyntaxError(msg)
        else:
            msg = f"Unsupported argument {key!r} in secret reference {expression!r}"
            raise SecretSyntaxError(msg)

    _apply_arg(
        first_match.group("key"),
        first_match.group("str_val"),
        first_match.group("num_val"),
    )
    remainder = first_match.group("remainder").strip()

    if remainder:
        pos = 0
        while pos < len(remainder):
            kwarg_match = _KWARG_PATTERN.match(remainder, pos)
            if not kwarg_match:
                unparsed = remainder[pos:].strip()
                msg = f"Invalid argument syntax in secret reference: {unparsed!r} in {expression!r}"
                raise SecretSyntaxError(msg)

            _apply_arg(
                kwarg_match.group("key"),
                kwarg_match.group("str_val"),
                kwarg_match.group("num_val"),
            )
            pos = kwarg_match.end()

    if not path or not path.strip("/"):
        msg = f"Missing or empty secret path in expression: {expression!r}"
        raise SecretSyntaxError(msg)

    return SecretReference(
        path=path,
        field=field,
        version=version,
        raw_expression=raw,
    )


def find_secret_references(
    text: str,
    *,
    allow_version: bool = True,
) -> list[tuple[str, SecretReference]]:
    """Find all secret references in text with their full matched expression.

    Returns:
        List of (full_matched_expression, SecretReference) tuples.
    """
    results: list[tuple[str, SecretReference]] = []
    for match in _SECRET_PATTERN.finditer(text):
        full_expr = match.group(0)
        ref = parse_secret_reference(full_expr, allow_version=allow_version)
        results.append((full_expr, ref))
    return results


def has_secret_references(text: str) -> bool:
    """Return True if the text contains any secret reference expressions."""
    return bool(_SECRET_PATTERN.search(text))
