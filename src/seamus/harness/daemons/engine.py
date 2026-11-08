"""One-shot LLM invocation engine for non-agentic background daemons."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from langchain_core.messages import HumanMessage
from pydantic import SecretStr

from seamus.config.models import InferenceConfig, InferenceFormat
from seamus.harness.daemons.parser import parse_loose_slug

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


async def invoke_daemon(
    provider: InferenceConfig,
    model: str,
    instructions: str,
    input_payload: str,
    occupied_slugs: set[str] | None = None,
    api_key_override: str | None = None,
) -> str | None:
    """Execute a one-shot plain-prefill daemon prompt against the specified provider and model.

    Format:
    Instructions:
    {instructions}

    Input:
    {input_payload}

    Output:
    """
    import os

    from seamus.harness.runner import ReasoningChatOpenAI, _ensure_ollama_model

    api_key = api_key_override or provider.api_key or ""
    base_url = provider.base_url or "https://openrouter.ai/api/v1"

    # If provider contains symbolic vault secret references, resolve them in-memory
    if ("${" in api_key or "${" in base_url) and not api_key_override:
        try:
            from seamus.vault.interpolator import resolve_secrets

            resolved = await resolve_secrets(provider)
            api_key = resolved.api_key or ""
            base_url = resolved.base_url or base_url
        except Exception:
            logger.debug("Failed in-place secret resolution in invoke_daemon", exc_info=True)

    if provider.format == InferenceFormat.OLLAMA or "11434" in base_url:
        try:
            base_url = _ensure_ollama_model(base_url, model)
        except Exception:
            logger.exception("Failed to probe/ensure Ollama model for daemon: %s", model)
            return None
        if not api_key:
            api_key = "ollama"
        if not base_url.rstrip("/").endswith("/v1"):
            base_url = f"{base_url.rstrip('/')}/v1"
    else:
        # Fall back to environment variable if api_key is missing or symbolic
        if not api_key or "${" in api_key:
            env_key = (
                os.getenv("OPENROUTER_API_KEY", "").strip()
                or os.getenv("OPEN_ROUTER_API_KEY", "").strip()
            )
            if env_key:
                api_key = env_key
            else:
                logger.warning(
                    "Daemon invocation skipped for model %s: missing API key for %s",
                    model,
                    base_url,
                )
                return None

    prompt_text = (
        f"Instructions:\n{instructions.strip()}\n\nInput:\n{input_payload.strip()}\n\nOutput:\n"
    )

    try:
        llm = ReasoningChatOpenAI(
            model=model,
            api_key=SecretStr(api_key),
            base_url=base_url,
            temperature=0.0,
        )
        response = await llm.ainvoke([HumanMessage(content=prompt_text)])
        raw_output = response.content
        if isinstance(raw_output, list):
            raw_output = " ".join(str(item) for item in raw_output)

        slug = parse_loose_slug(str(raw_output), occupied_slugs=occupied_slugs)
        logger.info(
            "Daemon invoked with model %s; raw output: %r; parsed slug: %r",
            model,
            raw_output,
            slug,
        )
        return slug
    except Exception:
        logger.exception("Daemon invocation failed with model %s", model)
        return None
