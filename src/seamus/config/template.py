"""Singleton service-wide configuration template management."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

from dotenv import load_dotenv

from seamus.config.models import (
    AgentConfig,
    InferenceConfig,
    InferenceFormat,
    OperationalMode,
)

if TYPE_CHECKING:
    from seamus.persistence.workspace import GitWorkspaceManager

logger = logging.getLogger(__name__)


class ConfigTemplateStore:
    """Manages the service-wide singleton AgentConfig template persisted to Git."""

    def __init__(
        self,
        initial_template: AgentConfig | None = None,
        workspace_manager: GitWorkspaceManager | None = None,
    ) -> None:
        self._ws_mgr = workspace_manager
        if initial_template is not None:
            self._template = initial_template.model_copy(deep=True)
        else:
            self._template = self._load_initial_template()

    def _get_workspace_manager(self) -> GitWorkspaceManager:
        if self._ws_mgr is not None:
            return self._ws_mgr
        from seamus.persistence.workspace import get_workspace_manager

        return get_workspace_manager()

    def _load_initial_template(self) -> AgentConfig:
        """Attempt to load template from persistence; fall back to environment seed."""
        try:
            from seamus.vault.interpolator import strip_secret_versions

            ws_mgr = self._get_workspace_manager()
            data = ws_mgr.read_system_config_template()
            if data is not None:
                return AgentConfig.model_validate(strip_secret_versions(data))
            initial = self._load_from_environment()
            ws_mgr.commit_system_config_template(initial.model_dump())
            return initial
        except Exception:
            logger.debug(
                "Failed to read config template from workspace; using environment/defaults"
            )
            return self._load_from_environment()

    @staticmethod
    def _load_from_environment(env_file: Path | str | None = None) -> AgentConfig:
        """Load default configuration template from environment or .env file."""
        if env_file is not None:
            target = Path(env_file)
            if target.exists():
                load_dotenv(dotenv_path=target, override=False, interpolate=False)
        else:
            load_dotenv(override=False, interpolate=False)

        api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
        if not api_key:
            api_key = os.getenv("OPEN_ROUTER_API_KEY", "").strip()
        if api_key.startswith("$${"):
            api_key = api_key[1:]
        if not api_key:
            api_key = "${secret('/api-key/inference/openrouter')}"

        base_url = os.getenv("OPENROUTER_BASE_URL", "").strip() or "https://openrouter.ai/api/v1"
        model_name = (
            os.getenv("OPENROUTER_MODEL", "").strip()
            or os.getenv("MODEL_NAME", "").strip()
            or "openai/gpt-oss-120b"
        )
        mode = (
            os.getenv("DEFAULT_MODE", "").strip()
            or os.getenv("SEAMUS_MODE", "").strip()
            or OperationalMode.PLAN.value
        )
        overlap_str = os.getenv("SEAMUS_THREAD_MESSAGE_OVERLAP", "").strip()
        thread_message_overlap = int(overlap_str) if overlap_str.isdigit() else 5

        return AgentConfig(
            inference=InferenceConfig(
                format=InferenceFormat.OPENAI,
                base_url=base_url,
                api_key=api_key if api_key else None,
            ),
            model_name=model_name,
            mode=mode,
            thread_message_overlap=thread_message_overlap,
        )

    def get_template(self) -> AgentConfig:
        """Retrieve a copy of the current configuration template."""
        return self._template.model_copy(deep=True)

    def set_template(self, template: AgentConfig) -> AgentConfig:
        """Replace the current configuration template and persist to repository."""
        self._template = template.model_copy(deep=True)
        try:
            ws_mgr = self._get_workspace_manager()
            ws_mgr.commit_system_config_template(self._template.model_dump())
        except Exception:
            logger.exception("Failed to persist configuration template to repository")
        return self.get_template()

    def derive_agent_config(self, overrides: AgentConfig | None = None) -> AgentConfig:
        """Derive an agent configuration from the template, merging overrides."""
        return self._template.copy_with_overrides(overrides)


_GLOBAL_TEMPLATE_STORE: ConfigTemplateStore | None = None


def get_config_template_store() -> ConfigTemplateStore:
    """Return the global singleton instance of ConfigTemplateStore."""
    global _GLOBAL_TEMPLATE_STORE
    if _GLOBAL_TEMPLATE_STORE is None:
        _GLOBAL_TEMPLATE_STORE = ConfigTemplateStore()
    return _GLOBAL_TEMPLATE_STORE


def reset_config_template_store(
    store: ConfigTemplateStore | None = None,
) -> ConfigTemplateStore:
    """Reset the global singleton instance, optionally replacing it (useful in tests)."""
    global _GLOBAL_TEMPLATE_STORE
    _GLOBAL_TEMPLATE_STORE = store
    return get_config_template_store()
