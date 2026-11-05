"""Domain entities and value objects for renderable artifacts."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ExpositionMode(StrEnum):
    """How the artifact surface is exposed to the user."""

    EMBEDDED = "embedded"
    TABBED = "tabbed"


class CadenceMode(StrEnum):
    """How the artifact affects conversational cadence."""

    BLOCKING = "blocking"
    NONBLOCKING = "nonblocking"


class ArtifactManifest(BaseModel):
    """Behavioral and presentation manifest for an artifact."""

    exposition: ExpositionMode = ExpositionMode.EMBEDDED
    cadence: CadenceMode = CadenceMode.BLOCKING
    title: str | None = None


class ArtifactInfo(BaseModel):
    """Summary and hydrated state of an artifact instance."""

    kind: str = Field(description="Artifact family/class (e.g. 'questionnaires', 'forms', 'plans')")
    name: str = Field(description="Artifact instance identifier (e.g. UUID)")
    title: str | None = Field(default=None, description="Display title for tabbed artifacts")
    manifest: ArtifactManifest
    is_closed: bool = Field(description="True if closed.json is present at instance level")
    card: dict[str, Any] = Field(description="Microsoft Adaptive Card JSON specification")
    data: dict[str, Any] | None = Field(
        default=None, description="User submitted values or state data if present"
    )
