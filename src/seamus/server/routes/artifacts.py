"""Routes for inspecting, rendering, and clicking A2UI artifacts."""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from seamus.domain.artifacts import ArtifactInfo, ClickResult
from seamus.domain.resolution import EntityNotFoundError, resolve_session
from seamus.harness.artifacts import ArtifactResolver
from seamus.harness.runner import SessionBusyError, get_runner_registry
from seamus.harness.store import get_harness_store
from seamus.persistence.workspace import get_workspace_manager

router = APIRouter(
    prefix="/agent/{agent_identifier}/session/{session_identifier}/artifact",
    tags=["artifacts"],
)
logger = logging.getLogger(__name__)


class ArtifactClickRequest(BaseModel):
    """Payload for clicking an artifact button."""

    button_id: str = Field(description="ID of the clicked button")
    event: str | None = Field(default=None, description="Action event name")
    timestamp: str | None = Field(default=None, description="ISO timestamp with TZ")
    context: dict[str, Any] = Field(
        default_factory=dict,
        description="Static context payload from button action event",
    )
    data: dict[str, Any] = Field(
        default_factory=dict,
        description="Snapshot of input widgets on the artifact",
    )
    comments: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Review comments attached to the action",
    )


class ArtifactSubmitRequest(BaseModel):
    """Payload for submitting data into an active artifact surface (transitional)."""

    data: dict[str, Any] = Field(
        default_factory=dict, description="Filled values/answers from artifact submission"
    )


@router.get("", response_model=list[ArtifactInfo])
async def list_session_artifacts(
    agent_identifier: str,
    session_identifier: str,
) -> list[ArtifactInfo]:
    """List all A2UI artifacts associated with this session."""
    store = get_harness_store()
    try:
        agent = store.resolve_agent(agent_identifier)
        session = resolve_session(agent, session_identifier)
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    ws_mgr = get_workspace_manager()
    artifacts_dir = ws_mgr.get_session_artifacts_dir(session.agent_id, session.id)
    resolver = ArtifactResolver(artifacts_dir)
    return resolver.list_artifacts()


@router.get("/{kind}/{name}", response_model=ArtifactInfo)
async def get_artifact(
    agent_identifier: str,
    session_identifier: str,
    kind: str,
    name: str,
) -> ArtifactInfo:
    """Retrieve full details, manifest, components, and data for an artifact."""
    store = get_harness_store()
    try:
        agent = store.resolve_agent(agent_identifier)
        session = resolve_session(agent, session_identifier)
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    ws_mgr = get_workspace_manager()
    artifacts_dir = ws_mgr.get_session_artifacts_dir(session.agent_id, session.id)
    resolver = ArtifactResolver(artifacts_dir)

    target_dir = artifacts_dir / kind / name
    if not target_dir.is_dir():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifact '{kind}/{name}' was not found.",
        )

    try:
        return resolver.load_artifact(kind, name)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/{family}/{uuid}/click", response_model=ClickResult)
async def click_artifact(
    agent_identifier: str,
    session_identifier: str,
    family: str,
    uuid: str,
    payload: ArtifactClickRequest,
) -> ClickResult:
    """Dispatch a button click event on an artifact instance."""
    store = get_harness_store()
    try:
        agent = store.resolve_agent(agent_identifier)
        session = resolve_session(agent, session_identifier)
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    registry = get_runner_registry()
    runner = registry.get_runner(session, agent=agent)

    try:
        return await runner.dispatch_artifact_click(
            family=family,
            uuid=uuid,
            button_id=payload.button_id,
            context=payload.context,
            event=payload.event,
            timestamp=payload.timestamp,
            data=payload.data,
            comments=payload.comments,
        )
    except SessionBusyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to dispatch artifact click for %s/%s", family, uuid)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Artifact click failed: {exc}",
        ) from exc


@router.post("/{uuid}/click", response_model=ClickResult)
async def click_artifact_by_uuid(
    agent_identifier: str,
    session_identifier: str,
    uuid: str,
    payload: ArtifactClickRequest,
) -> ClickResult:
    """Dispatch a button click event resolving artifact family automatically by UUID."""
    store = get_harness_store()
    try:
        agent = store.resolve_agent(agent_identifier)
        session = resolve_session(agent, session_identifier)
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    ws_mgr = get_workspace_manager()
    artifacts_dir = ws_mgr.get_session_artifacts_dir(session.agent_id, session.id)
    resolver = ArtifactResolver(artifacts_dir)
    matched = resolver.resolve_artifact(uuid)
    if matched is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifact '{uuid}' was not found.",
        )

    registry = get_runner_registry()
    runner = registry.get_runner(session, agent=agent)

    try:
        return await runner.dispatch_artifact_click(
            family=matched.family,
            uuid=uuid,
            button_id=payload.button_id,
            context=payload.context,
            event=payload.event,
            timestamp=payload.timestamp,
            data=payload.data,
            comments=payload.comments,
        )
    except SessionBusyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to dispatch artifact click for %s/%s", matched.family, uuid)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Artifact click failed: {exc}",
        ) from exc


@router.post("/{kind}/{name}/submit", status_code=status.HTTP_202_ACCEPTED)
async def submit_artifact(
    agent_identifier: str,
    session_identifier: str,
    kind: str,
    name: str,
    payload: ArtifactSubmitRequest,
) -> dict[str, str]:
    """Submit filled artifact data (transitional bridge to click dispatch)."""
    store = get_harness_store()
    try:
        agent = store.resolve_agent(agent_identifier)
        session = resolve_session(agent, session_identifier)
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    registry = get_runner_registry()
    runner = registry.get_runner(session, agent=agent)

    try:
        call_id = await runner.dispatch_artifact_submission(kind, name, payload.data)
    except SessionBusyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to dispatch artifact submission for %s/%s", kind, name)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Artifact submission failed: {exc}",
        ) from exc

    return {
        "status": "accepted",
        "artifact_id": name,
        "kind": kind,
        "session_id": str(session.id),
        "tool_call_id": call_id,
    }
