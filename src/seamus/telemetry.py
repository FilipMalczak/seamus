"""Logfire telemetry configuration, FastAPI instrumentation, and span management."""

import os
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


def setup_telemetry(
    service_name: str | None = None,
    send_to_logfire: bool | Literal["if-token-present"] | None = None,
    force_reconfigure: bool = False,
    env_file: Path | str | None = None,
) -> None:
    """Configure Logfire and OpenTelemetry environment for Seamus, loading from .env if present."""
    global _TELEMETRY_INITIALIZED

    # Load environment variables from .env file
    if env_file is not None:
        load_dotenv(dotenv_path=Path(env_file), override=True)
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

    if _TELEMETRY_INITIALIZED and not force_reconfigure:
        return

    effective_service_name = service_name or os.getenv("LOGFIRE_SERVICE_NAME", "seamus")

    target_send: bool | Literal["if-token-present"] = (
        "if-token-present" if send_to_logfire is None else send_to_logfire
    )

    logfire.configure(
        service_name=effective_service_name,
        send_to_logfire=target_send,
        scrubbing=logfire.ScrubbingOptions(callback=_scrub_callback),
    )
    _TELEMETRY_INITIALIZED = True


def instrument_fastapi(app: FastAPI) -> None:
    """Instrument FastAPI application with Logfire request tracing."""
    logfire.instrument_fastapi(app)
