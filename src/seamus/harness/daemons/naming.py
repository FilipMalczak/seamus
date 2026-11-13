"""Naming daemons for automated thread and session slug generation."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from seamus.harness.daemons.engine import invoke_daemon
from seamus.harness.daemons.formatter import format_thread_history
from seamus.harness.steerable import daemon_instance_id
from seamus.persistence.workspace import get_workspace_manager

if TYPE_CHECKING:
    from seamus.domain.entities import Thread
    from seamus.harness.runner import SessionAgentRunner

logger = logging.getLogger(__name__)

THREAD_NAMING_INSTRUCTIONS = (
    "You are an expert conversation naming daemon.\n"
    "Analyze the provided user and assistant messages (including created artifacts and actions) "
    "for this conversation thread and generate a concise, human-readable, URL-safe slug that "
    "captures the thread's core topic or goal.\n\n"
    "Requirements:\n"
    "- Slug format: lowercase alphanumeric characters and single hyphens only "
    "(^[a-z0-9]+(-[a-z0-9]+)*$).\n"
    "- Length: 2 to 5 words (maximum 40 characters).\n"
    "- Specificity: Be descriptive and concrete (e.g., 'fix-docker-networking', "
    "'token-redirect-bug', 'database-backend-selection').\n"
    "- Avoid generic names like 'chat', 'session', 'test', 'untitled', 'conversation'.\n"
    "- Slugs to avoid: Do NOT reuse any slug listed in Occupied Slugs.\n"
    "- Output: Print ONLY the raw slug string. "
    "Do NOT add markdown, quotes, explanations, or punctuation."
)

SESSION_NAMING_INSTRUCTIONS = (
    "You are an expert project workspace naming daemon.\n"
    "Analyze the slugs and summaries of all conversation threads within this session and generate "
    "a concise, human-readable, URL-safe slug that captures the overarching project, feature, "
    "or objective of the entire session.\n\n"
    "Requirements:\n"
    "- Slug format: lowercase alphanumeric characters and single hyphens only "
    "(^[a-z0-9]+(-[a-z0-9]+)*$).\n"
    "- Length: 2 to 5 words (maximum 40 characters).\n"
    "- Specificity: Synthesize the broader goal across all threads "
    "(e.g., 'sandbox-docker-isolation', 'vault-secrets-integration').\n"
    "- Avoid generic names like 'work', 'project', 'agent', 'development'.\n"
    "- Slugs to avoid: Do NOT reuse any slug listed in Occupied Session Slugs.\n"
    "- Output: Print ONLY the raw slug string. "
    "Do NOT add markdown, quotes, explanations, or punctuation."
)


def is_stepback_trigger(count: int) -> bool:
    """Return True if count matches the doubling stepback sequence 2^k - 1 (1, 3, 7, 15, ...)."""
    return count > 0 and ((count + 1) & count) == 0


def _resolve_daemon_api_key(runner: SessionAgentRunner) -> str | None:
    """Extract resolved active API key from the runner's LLM if available and not symbolic."""
    from seamus.harness.steerable import SteerableChatModel

    if isinstance(runner._llm, SteerableChatModel):
        return None
    if runner._llm and runner._llm.openai_api_key:
        from pydantic import SecretStr

        key = (
            runner._llm.openai_api_key.get_secret_value()
            if isinstance(runner._llm.openai_api_key, SecretStr)
            else str(runner._llm.openai_api_key or "")
        )
        if key and "${" not in key:
            return key
    return None


async def execute_thread_naming(runner: SessionAgentRunner, thread: Thread) -> str | None:
    """Execute thread naming daemon and update thread.daemon_name if enabled and triggered."""
    naming_cfg = runner.session.config.daemons.naming
    if not naming_cfg.enabled or not naming_cfg.model:
        return None

    provider = naming_cfg.provider or runner.session.config.inference
    model = naming_cfg.model

    occupied: set[str] = {
        t.name for t in runner.session.threads.values() if t.id != thread.id and t.name
    }
    history_text = format_thread_history(thread.events)

    occupied_str = "\n".join(f"- {s}" for s in sorted(occupied)) if occupied else "(none)"
    input_payload = f"Occupied Slugs:\n{occupied_str}\n\nMessages:\n{history_text}"

    active_key = _resolve_daemon_api_key(runner)
    slug = await invoke_daemon(
        provider=provider,
        model=model,
        instructions=THREAD_NAMING_INSTRUCTIONS,
        input_payload=input_payload,
        occupied_slugs=occupied,
        api_key_override=active_key if naming_cfg.provider is None else None,
        steerable_instance_id=daemon_instance_id(runner.session.id),
    )
    if not slug:
        return None

    thread.daemon_name = slug
    thread.touch()
    runner.session.touch()

    # If session has only 1 thread, session slug mirrors thread slug (sans conflicts)
    if len(runner.session.threads) == 1:
        agent_entity = runner._resolve_agent_entity()
        occupied_sessions: set[str] = (
            {s.name for s in agent_entity.sessions.values() if s.id != runner.session.id and s.name}
            if agent_entity is not None
            else set()
        )
        if slug not in occupied_sessions:
            runner.session.daemon_name = slug
        else:
            counter = 2
            while f"{slug}-{counter}" in occupied_sessions:
                counter += 1
            runner.session.daemon_name = f"{slug}-{counter}"

    try:
        ws_mgr = get_workspace_manager()
        ws_mgr.commit_session_config(runner.session, secret_versions=runner._loaded_secret_versions)
    except Exception:
        logger.exception("Failed to commit session config after thread naming")

    event = {
        "type": "THREAD_NAMED",
        "thread_id": str(thread.id),
        "thread_name": thread.name,
        "daemon_name": thread.daemon_name,
        "session_id": str(runner.session.id),
        "session_name": runner.session.name,
    }
    await runner.broadcaster.broadcast(event)
    return slug


async def execute_session_naming(runner: SessionAgentRunner) -> str | None:
    """Execute session naming daemon and update session.daemon_name if enabled and triggered."""
    naming_cfg = runner.session.config.daemons.naming
    if not naming_cfg.enabled or not naming_cfg.model:
        return None

    provider = naming_cfg.provider or runner.session.config.inference
    model = naming_cfg.model

    agent_entity = runner._resolve_agent_entity()
    occupied: set[str] = (
        {s.name for s in agent_entity.sessions.values() if s.id != runner.session.id and s.name}
        if agent_entity is not None
        else set()
    )

    thread_slugs = [t.name or str(t.id) for t in runner.session.threads.values()]
    occupied_str = "\n".join(f"- {s}" for s in sorted(occupied)) if occupied else "(none)"
    threads_str = "\n".join(f"- {s}" for s in thread_slugs) if thread_slugs else "(none)"
    input_payload = f"Occupied Session Slugs:\n{occupied_str}\n\nThreads in Session:\n{threads_str}"

    active_key = _resolve_daemon_api_key(runner)
    slug = await invoke_daemon(
        provider=provider,
        model=model,
        instructions=SESSION_NAMING_INSTRUCTIONS,
        input_payload=input_payload,
        occupied_slugs=occupied,
        api_key_override=active_key if naming_cfg.provider is None else None,
        steerable_instance_id=daemon_instance_id(runner.session.id),
    )
    if not slug:
        return None

    runner.session.daemon_name = slug
    runner.session.touch()

    try:
        ws_mgr = get_workspace_manager()
        ws_mgr.commit_session_config(runner.session, secret_versions=runner._loaded_secret_versions)
    except Exception:
        logger.exception("Failed to commit session config after session naming")

    event = {
        "type": "SESSION_NAMED",
        "session_id": str(runner.session.id),
        "session_name": runner.session.name,
        "daemon_name": runner.session.daemon_name,
    }
    await runner.broadcaster.broadcast(event)
    return slug
