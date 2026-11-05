"""Routes for inspecting and submitting Microsoft Adaptive Card renderable artifacts."""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from seamus.domain.artifacts import ArtifactInfo
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


class ArtifactSubmitRequest(BaseModel):
    """Payload for submitting data into an active artifact surface."""

    data: dict[str, Any] = Field(
        default_factory=dict, description="Filled values/answers from artifact submission"
    )


@router.get("", response_model=list[ArtifactInfo])
async def list_session_artifacts(
    agent_identifier: str,
    session_identifier: str,
) -> list[ArtifactInfo]:
    """List all Adaptive Card artifacts associated with this session."""
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


@router.post("/{kind}/{name}/submit", status_code=status.HTTP_202_ACCEPTED)
async def submit_artifact(
    agent_identifier: str,
    session_identifier: str,
    kind: str,
    name: str,
    payload: ArtifactSubmitRequest,
) -> dict[str, str]:
    """Submit filled artifact data, close artifact, and resume agent with synthetic tool call."""
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
