"""Unit tests for the symbolic secret expression parser and models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from seamus.config.models import AgentConfig, InferenceConfig
from seamus.vault.interpolator import (
    explode_secret_references,
    strip_secret_versions,
)
from seamus.vault.models import SecretSyntaxError
from seamus.vault.parser import (
    find_secret_references,
    has_secret_references,
    parse_secret_reference,
)


def test_parse_positional_path_default_field() -> None:
    ref = parse_secret_reference("${secret('/api-key/inference/openrouter')}")
    assert ref.path == "/api-key/inference/openrouter"
    assert ref.normalized_path == "/api-key/inference/openrouter"
    assert ref.field == "value"
    assert ref.version is None
    assert ref.to_unversioned_expression() == "${secret('/api-key/inference/openrouter')}"


def test_parse_keyword_path_and_explicit_field() -> None:
    ref = parse_secret_reference("${secret(path='/api-key/inference/openrouter', field='value')}")
    assert ref.path == "/api-key/inference/openrouter"
    assert ref.field == "value"
    assert ref.version is None
    assert (
        ref.to_exploded_expression(3)
        == "${secret(path='/api-key/inference/openrouter', field='value', version=3)}"
    )


def test_parse_positional_path_and_custom_field() -> None:
    ref = parse_secret_reference("${secret('/git/creds', field='token')}")
    assert ref.path == "/git/creds"
    assert ref.field == "token"
    assert ref.to_unversioned_expression() == "${secret(path='/git/creds', field='token')}"
    assert ref.to_exploded_expression(1) == "${secret(path='/git/creds', field='token', version=1)}"


def test_parse_disallows_version_by_default() -> None:
    with pytest.raises(SecretSyntaxError, match="disallowed in user configurations"):
        parse_secret_reference(
            "${secret(path='/api-key/inference/openrouter', field='value', version=2)}",
            allow_version=False,
        )


def test_parse_allows_version_when_enabled() -> None:
    ref = parse_secret_reference(
        "${secret(path='/api-key/inference/openrouter', field='value', version=2)}",
        allow_version=True,
    )
    assert ref.path == "/api-key/inference/openrouter"
    assert ref.field == "value"
    assert ref.version == 2


def test_parse_invalid_syntax_errors() -> None:
    with pytest.raises(SecretSyntaxError, match="Missing or empty secret path"):
        parse_secret_reference("${secret(field='value')}")

    with pytest.raises(SecretSyntaxError, match="Duplicate argument 'path'"):
        parse_secret_reference("${secret('/foo', path='/bar')}")

    with pytest.raises(SecretSyntaxError, match="Unsupported argument"):
        parse_secret_reference("${secret('/foo', bogus='x')}")

    with pytest.raises(SecretSyntaxError, match="positive integer"):
        parse_secret_reference("${secret('/foo', version=0)}", allow_version=True)

    with pytest.raises(SecretSyntaxError, match="Missing or empty secret path"):
        parse_secret_reference("${secret('/')}")


def test_find_and_has_secret_references() -> None:
    text = "Key A: ${secret('/a')} and Key B: ${secret(path='/b/c', field='api_key')}"
    assert has_secret_references(text) is True
    matches = find_secret_references(text)
    assert len(matches) == 2
    assert matches[0][1].path == "/a"
    assert matches[0][1].field == "value"
    assert matches[1][1].path == "/b/c"
    assert matches[1][1].field == "api_key"
    assert has_secret_references("plain-string-without-secrets") is False


def test_explode_and_strip_secret_references() -> None:
    from typing import Any

    cfg: dict[str, Any] = {
        "inference": {
            "api_key": "${secret('/api-key/inference/openrouter')}",
            "base_url": "https://openrouter.ai/api/v1",
        },
        "system_prompt": "Token is ${secret(path='git/pat', field='token')}",
    }
    versions = {
        ("/api-key/inference/openrouter", "value"): 4,
        ("/git/pat", "token"): 2,
    }
    exploded = explode_secret_references(cfg, versions)
    assert (
        exploded["inference"]["api_key"]
        == "${secret(path='/api-key/inference/openrouter', field='value', version=4)}"
    )
    assert (
        exploded["system_prompt"] == "Token is ${secret(path='/git/pat', field='token', version=2)}"
    )

    stripped = strip_secret_versions(exploded)
    assert stripped["inference"]["api_key"] == "${secret('/api-key/inference/openrouter')}"
    assert stripped["system_prompt"] == "Token is ${secret(path='/git/pat', field='token')}"


def test_config_models_reject_version_parameter() -> None:
    # Valid unversioned expressions pass validation
    cfg = AgentConfig(
        inference=InferenceConfig(
            api_key="${secret('/api-key/inference/openrouter')}",
        ),
        model_name="openai/gpt-oss-120b",
    )
    assert cfg.inference.api_key == "${secret('/api-key/inference/openrouter')}"

    # Versioned expression in InferenceConfig is rejected
    with pytest.raises(ValidationError, match="disallowed in user configurations"):
        InferenceConfig(
            api_key="${secret(path='/api-key/inference/openrouter', field='value', version=1)}"
        )

    # Versioned expression in AgentConfig.system_prompt is rejected
    with pytest.raises(ValidationError, match="disallowed in user configurations"):
        AgentConfig(system_prompt="Prompt ${secret(path='/foo', field='value', version=1)}")
