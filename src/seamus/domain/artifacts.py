"""Domain entities and value objects for A2UI renderable artifacts."""

from typing import Any, Literal

from pydantic import BaseModel, Field, computed_field, field_validator

SYNTHETIC_MESSAGE_INDICATOR = "<SYNTHETIC MESSAGE INDICATOR>"


class ArtifactCorruptedError(Exception):
    """Raised when an artifact directory is structurally invalid or violates INV-ART-003."""

    pass


class ManifestButton(BaseModel):
    """Button configuration declared in an artifact manifest."""

    id: str = Field(description="Unique button ID matching component ID in body.json")
    mode: Literal["set", "append"] = Field(
        description="Mode for recording click context in /interactions/<id>.json"
    )
    clicks: int | Literal["*"] = Field(
        default="*",
        description="Allowed clicks before becoming inactive; positive integer or '*'",
    )
    unblocking: bool = Field(
        default=False,
        description="Whether clicking this button unblocks the conversation",
    )
    closing: bool = Field(
        default=False,
        description="Whether clicking this button closes the artifact (implicitly unblocking)",
    )

    @field_validator("clicks")
    @classmethod
    def validate_positive_clicks(cls, v: int | str) -> int | str:
        if isinstance(v, int) and v < 1:
            msg = "Button clicks in manifest must be a positive integer (>= 1) or '*'"
            raise ValueError(msg)
        if isinstance(v, str) and v != "*":
            msg = "Button clicks must be an integer or '*'"
            raise ValueError(msg)
        return v


class ArtifactManifest(BaseModel):
    """Behavioral and presentation manifest for an artifact."""

    name: str = Field(default="Artifact", description="Display title of the artifact")
    exposition: Literal["tabbed", "embedded"] = Field(
        default="embedded",
        description="Whether the artifact is exposed as an embedded bubble or a tabbed panel",
    )
    blocking: bool = Field(
        default=False,
        description="Whether text input is blocked until an unblocking button is clicked",
    )
    commentable: bool = Field(
        default=False,
        description="Whether the UI enables inline text selection and review commenting",
    )
    buttons: list[ManifestButton] = Field(
        default_factory=list,
        description="Whitelisted buttons authorized for user interaction",
    )

    # Backward compatibility property for previous title field
    @property
    def title(self) -> str | None:
        return self.name


class ArtifactState(BaseModel):
    """Runtime state accumulated over button interactions and click counters."""

    dataModel: dict[str, Any] = Field(
        default_factory=dict,
        description="Accumulated data model from button click context payloads",
    )
    clicksLeft: dict[str, int | Literal["*"]] = Field(
        default_factory=dict,
        description="Remaining click quotas per button ID (<= 0 indicates inactive)",
    )


class ClickResult(BaseModel):
    """Payload returned by wait_for_click or dispatched upon a button click."""

    artifact_id: str = Field(description="UUID of the clicked artifact")
    button_id: str = Field(description="ID of the button that was clicked")
    context: dict[str, Any] = Field(
        default_factory=dict,
        description="Evaluated context payload from the button click event",
    )
    timestamp: float = Field(description="Timestamp of the interaction (file mtime)")


class ArtifactInfo(BaseModel):
    """Summary and hydrated state of an artifact instance."""

    family: str = Field(
        description="Artifact family (e.g. 'questionnaires', 'forms', 'plans', 'custom')"
    )
    uuid: str = Field(description="Artifact instance UUID")
    manifest: ArtifactManifest = Field(description="Artifact configuration manifest")
    body: list[dict[str, Any]] = Field(
        default_factory=list,
        description="A2UI basic catalog components sequence",
    )
    state: ArtifactState = Field(
        default_factory=ArtifactState,
        description="Current runtime state (dataModel and clicksLeft)",
    )
    is_closed: bool = Field(
        default=False,
        description="True if closed.marker exists at instance level",
    )
    title: str | None = Field(default=None, description="Display title for tabs or headers")

    # Backward compatibility properties for previous API shapes
    @computed_field  # type: ignore[prop-decorator]
    @property
    def kind(self) -> str:
        return self.family

    @computed_field  # type: ignore[prop-decorator]
    @property
    def name(self) -> str:
        return self.uuid

    @property
    def card(self) -> dict[str, Any]:
        """Transitional bridge for card field."""
        return {"components": self.body}

    @property
    def data(self) -> dict[str, Any] | None:
        """Transitional bridge for data field."""
        return self.state.dataModel if self.state.dataModel else None
