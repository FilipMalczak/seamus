"""Singleton service-wide configuration template management."""

import os
from pathlib import Path

from dotenv import load_dotenv

from seamus.config.models import AgentConfig, InferenceConfig, InferenceFormat


class ConfigTemplateStore:
    """Manages the service-wide singleton AgentConfig template."""

    def __init__(self, initial_template: AgentConfig | None = None) -> None:
        if initial_template is not None:
            self._template = initial_template.model_copy(deep=True)
        else:
            self._template = self._load_from_environment()

    @staticmethod
    def _load_from_environment(env_file: Path | str | None = None) -> AgentConfig:
        """Load default configuration template from environment or .env file."""
        if env_file is not None:
            target = Path(env_file)
            if target.exists():
                load_dotenv(dotenv_path=target, override=False)
        else:
            load_dotenv(override=False)

        api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
        if not api_key:
            api_key = os.getenv("OPEN_ROUTER_API_KEY", "").strip()

        base_url = os.getenv("OPENROUTER_BASE_URL", "").strip() or "https://openrouter.ai/api/v1"
        model_name = (
            os.getenv("OPENROUTER_MODEL", "").strip()
            or os.getenv("MODEL_NAME", "").strip()
            or "openai/gpt-oss-120b"
        )

        return AgentConfig(
            inference=InferenceConfig(
                format=InferenceFormat.OPENAI,
                base_url=base_url,
                api_key=api_key if api_key else None,
            ),
            model_name=model_name,
        )

    def get_template(self) -> AgentConfig:
        """Retrieve a copy of the current configuration template."""
        return self._template.model_copy(deep=True)

    def set_template(self, template: AgentConfig) -> AgentConfig:
        """Replace the current configuration template with a new full configuration object."""
        self._template = template.model_copy(deep=True)
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


def reset_config_template_store(store: ConfigTemplateStore | None = None) -> ConfigTemplateStore:
    """Reset the global singleton instance, optionally replacing it (useful in tests)."""
    global _GLOBAL_TEMPLATE_STORE
    _GLOBAL_TEMPLATE_STORE = store
    return get_config_template_store()

