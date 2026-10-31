"""Routes for session lifecycle and user input dispatch."""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status

from seamus.domain.resolution import EntityNotFoundError, resolve_session
from seamus.harness.inspector import AgentInspectReport, build_agent_inspect_report
from seamus.harness.runner import SessionBusyError, get_runner_registry
from seamus.harness.store import SlugConflictError, get_harness_store
from seamus.server.schemas import (
    SessionCreateRequest,
    SessionDetailResponse,
    SessionUpdateRequest,
    ThreadResponse,
    UserInputRequest,
)

router = APIRouter(prefix="/agent/{agent_identifier}/session", tags=["sessions"])
logger = logging.getLogger(__name__)


def _to_session_detail(session: Any) -> SessionDetailResponse:
    threads = [
        ThreadResponse(
            id=t.id,
            name=t.name,
            created_at=t.created_at,
            last_touched_at=t.last_touched_at,
            is_open=t.is_open,
            status=t.status,
        )
        for t in sorted(session.threads.values(), key=lambda t: t.created_at)
    ]
    return SessionDetailResponse(
        id=session.id,
        agent_id=session.agent_id,
        name=session.name,
        created_at=session.created_at,
        last_touched_at=session.last_touched_at,
        config=session.config,
        threads=threads,
    )


@router.post("", response_model=SessionDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    agent_identifier: str,
    payload: SessionCreateRequest,
) -> SessionDetailResponse:
    """Create a new session under an agent with an initial open thread."""
    store = get_harness_store()
    try:
        session = store.create_session(
            agent_identifier=agent_identifier,
            config=payload.config,
            name=payload.name,
        )
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except SlugConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return _to_session_detail(session)


@router.get("/{session_identifier}", response_model=SessionDetailResponse)
async def get_session(
    agent_identifier: str,
    session_identifier: str,
) -> SessionDetailResponse:
    """Get session details and list its threads."""
    store = get_harness_store()
    try:
        agent = store.resolve_agent(agent_identifier)
        session = resolve_session(agent, session_identifier)
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return _to_session_detail(session)


@router.post("/{session_identifier}", response_model=SessionDetailResponse)
async def update_session(
    agent_identifier: str,
    session_identifier: str,
    payload: SessionUpdateRequest,
) -> SessionDetailResponse:
    """Update session name and configuration with full updated object."""
    store = get_harness_store()
    try:
        session = store.update_session(
            agent_identifier=agent_identifier,
            session_identifier=session_identifier,
            config=payload.config,
            name=payload.name,
        )
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except SlugConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return _to_session_detail(session)


@router.post(
    "/{session_identifier}/input",
    status_code=status.HTTP_202_ACCEPTED,
)
async def post_user_input(
    agent_identifier: str,
    session_identifier: str,
    payload: UserInputRequest,
) -> dict[str, str]:
    """Post user message input to the session's active thread."""
    store = get_harness_store()
    try:
        agent = store.resolve_agent(agent_identifier)
        session = resolve_session(agent, session_identifier)
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    try:
        text = payload.get_text()
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    registry = get_runner_registry()
    runner = registry.get_runner(session, agent=agent)

    try:
        user_msg_id = await runner.dispatch_user_input(text, message_id=payload.message_id)
    except SessionBusyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    open_thread = session.get_open_thread()
    return {
        "status": "accepted",
        "thread_id": str(open_thread.id),
        "session_id": str(session.id),
        "message_id": user_msg_id,
    }


@router.get(
    "/{session_identifier}/inspect",
    response_model=AgentInspectReport,
)
async def inspect_session_agent(
    agent_identifier: str,
    session_identifier: str,
    thread_id: str | None = Query(None, description="Optional thread identifier to inspect"),
) -> AgentInspectReport:
    """Return an agent inspection report reflecting state as of the latest inference run."""
    try:
        return build_agent_inspect_report(
            agent_identifier=agent_identifier,
            session_identifier=session_identifier,
            thread_identifier=thread_id,
        )
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to build agent inspect report")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate inspect report: {exc}",
        ) from exc
