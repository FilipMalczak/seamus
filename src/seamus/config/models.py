"""Configuration models for inference and agent execution."""

from enum import StrEnum
from typing import Self

from pydantic import BaseModel, Field


class InferenceFormat(StrEnum):
    """Supported inference API format shapes."""

    OPENAI = "openai"


class TodoImplementation(StrEnum):
    """Supported task list / planning middleware implementations."""

    NONE = "none"
    DEEPAGENTS = "deepagents"


class SkillsImplementation(StrEnum):
    """Supported skills discovery and disclosure middleware implementations."""

    NONE = "none"
    DEEPAGENTS = "deepagents"


class OperationalMode(StrEnum):
    """Supported operational modes."""

    CHAT = "chat"
    PLAN = "plan"


class InferenceConfig(BaseModel):
    """Inference API connection and credentials configuration."""

    format: InferenceFormat = InferenceFormat.OPENAI
    base_url: str = "https://openrouter.ai/api/v1"
    api_key: str | None = None

    def is_complete(self) -> bool:
        """Return True if all required inference fields are present and non-empty."""
        return bool(
            self.format
            and self.base_url
            and self.base_url.strip()
            and self.api_key
            and self.api_key.strip()
        )


class AgentConfig(BaseModel):
    """Full configuration for an agent or session instance."""

    inference: InferenceConfig = Field(default_factory=InferenceConfig)
    model_name: str = "openai/gpt-oss-120b"
    mode: str = OperationalMode.PLAN.value
    system_prompt: str | None = None
    todo_implementation: TodoImplementation = TodoImplementation.DEEPAGENTS
    skills_implementation: SkillsImplementation = SkillsImplementation.DEEPAGENTS

    def is_complete(self) -> bool:
        """Return True if this configuration is complete enough to initialize an agent."""
        return self.inference.is_complete() and bool(self.model_name and self.model_name.strip())

    def validate_complete(self) -> None:
        """Validate that configuration is complete, raising ValueError if fields are missing."""
        if not self.is_complete():
            missing: list[str] = []
            if not self.model_name or not self.model_name.strip():
                missing.append("model_name")
            if not self.inference.base_url or not self.inference.base_url.strip():
                missing.append("inference.base_url")
            if not self.inference.api_key or not self.inference.api_key.strip():
                missing.append("inference.api_key")
            msg = f"Agent configuration is incomplete. Missing or empty: {', '.join(missing)}"
            raise ValueError(msg)

    def copy_with_overrides(
        self,
        overrides: "AgentConfig | None" = None,
    ) -> Self:
        """Return a new AgentConfig derived from this instance with optional overrides merged."""
        if overrides is None:
            return self.model_copy(deep=True)

        merged_inference = self.inference.model_copy(
            update={
                k: v
                for k, v in overrides.inference.model_dump().items()
                if v is not None or k in overrides.inference.model_fields_set
            }
        )
        return self.model_copy(
            update={
                "inference": merged_inference,
                "model_name": (
                    overrides.model_name
                    if "model_name" in overrides.model_fields_set
                    else self.model_name
                ),
                "mode": (overrides.mode if "mode" in overrides.model_fields_set else self.mode),
                "system_prompt": (
                    overrides.system_prompt
                    if "system_prompt" in overrides.model_fields_set
                    else self.system_prompt
                ),
                "todo_implementation": (
                    overrides.todo_implementation
                    if "todo_implementation" in overrides.model_fields_set
                    else self.todo_implementation
                ),
                "skills_implementation": (
                    overrides.skills_implementation
                    if "skills_implementation" in overrides.model_fields_set
                    else self.skills_implementation
                ),
            },
            deep=True,
        )
