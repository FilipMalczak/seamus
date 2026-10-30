"""Logfire telemetry configuration, FastAPI instrumentation, and span management."""

import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Literal

import logfire
from dotenv import find_dotenv, load_dotenv
from fastapi import FastAPI
from logfire._internal.scrubbing import ScrubMatch


def _scrub_callback(match: ScrubMatch) -> Any:
    """Preserve 'session' domain attributes while redacting secrets and credentials."""
    if match.pattern_match.group(0).lower() == "session":
        # Retain domain concept of 'session' and session IDs in Seamus
        return match.value
    # Fall back to default redaction
    return None


_TELEMETRY_INITIALIZED = False
_EFFECTIVE_SEND_TO_LOGFIRE: bool | Literal["if-token-present"] | None = None


def _parse_send_to_logfire(
    send_to_logfire: bool | Literal["if-token-present"] | None,
) -> bool | Literal["if-token-present"]:
    """Resolve send_to_logfire setting from parameter or LOGFIRE_SEND_TO_LOGFIRE env var."""
    if send_to_logfire is not None:
        return send_to_logfire

    env_val = os.getenv("LOGFIRE_SEND_TO_LOGFIRE")
    if env_val is None:
        return "if-token-present"

    cleaned = env_val.strip().lower()
    if cleaned in ("false", "0", "off", "no", "never"):
        return False
    if cleaned in ("true", "1", "on", "yes", "always"):
        return True
    if cleaned == "if-token-present":
        return "if-token-present"

    return "if-token-present"


def is_logfire_enabled() -> bool:
    """Return whether Logfire is configured to send telemetry.

    Considers LOGFIRE_SEND_TO_LOGFIRE and LOGFIRE_TOKEN presence.
    """
    global _EFFECTIVE_SEND_TO_LOGFIRE
    send_setting = (
        _EFFECTIVE_SEND_TO_LOGFIRE
        if _EFFECTIVE_SEND_TO_LOGFIRE is not None
        else _parse_send_to_logfire(None)
    )

    if send_setting is False:
        return False
    if send_setting is True:
        return True

    # 'if-token-present'
    env_token = os.getenv("LOGFIRE_TOKEN")
    if env_token and env_token.strip():
        return True

    cfg_token = getattr(logfire.DEFAULT_LOGFIRE_INSTANCE.config, "token", None)
    return bool(cfg_token)


def get_logfire_service_name() -> str:
    """Return the configured Logfire service name (default 'seamus')."""
    return os.getenv("LOGFIRE_SERVICE_NAME", "seamus")


def setup_telemetry(
    service_name: str | None = None,
    send_to_logfire: bool | Literal["if-token-present"] | None = None,
    force_reconfigure: bool = False,
    env_file: Path | str | None = None,
) -> None:
    """Configure Logfire and OpenTelemetry environment for Seamus, loading from .env if present."""
    global _TELEMETRY_INITIALIZED, _EFFECTIVE_SEND_TO_LOGFIRE

    # Load environment variables from .env file
    if env_file is not None:
        load_dotenv(dotenv_path=Path(env_file), override=False)
    else:
        dotenv_path = find_dotenv(usecwd=True)
        if dotenv_path:
            load_dotenv(dotenv_path=dotenv_path, override=False)
        else:
            load_dotenv(override=False)

    # Ensure LangChain and LangGraph emit OpenTelemetry traces natively
    os.environ.setdefault("LANGSMITH_OTEL_ENABLED", "true")
    os.environ.setdefault("LANGSMITH_OTEL_ONLY", "true")
    os.environ.setdefault("LANGSMITH_TRACING", "true")

    effective_send = _parse_send_to_logfire(send_to_logfire)
    _EFFECTIVE_SEND_TO_LOGFIRE = effective_send

    if _TELEMETRY_INITIALIZED and not force_reconfigure:
        return

    effective_service_name = service_name or get_logfire_service_name()

    logfire.configure(
        service_name=effective_service_name,
        send_to_logfire=effective_send,
        scrubbing=logfire.ScrubbingOptions(callback=_scrub_callback),
    )
    _TELEMETRY_INITIALIZED = True


def instrument_fastapi(
    app: FastAPI,
    excluded_urls: str | Iterable[str] | None = r".*/health.*",
) -> None:
    """Instrument FastAPI application with Logfire request tracing, excluding health probes."""
    logfire.instrument_fastapi(app, excluded_urls=excluded_urls)
