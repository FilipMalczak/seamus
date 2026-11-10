"""Routes for thread lifecycle, redirection, event streaming, and status inspection."""

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import RedirectResponse, StreamingResponse

from seamus.domain.resolution import EntityNotFoundError, resolve_session, resolve_thread
from seamus.harness.runner import get_runner_registry
from seamus.harness.store import SlugConflictError, get_harness_store
from seamus.server.schemas import (
    ThreadCreateRequest,
    ThreadResponse,
    ThreadStatusResponse,
    ThreadUpdateRequest,
)

router = APIRouter(
    prefix="/agent/{agent_identifier}/session/{session_identifier}/thread",
    tags=["threads"],
)


@router.post("", response_model=ThreadResponse, status_code=status.HTTP_201_CREATED)
async def create_thread(
    agent_identifier: str,
    session_identifier: str,
    payload: ThreadCreateRequest,
) -> ThreadResponse:
    """Create a new thread, closing all prior threads in the session."""
    store = get_harness_store()
    try:
        thread = store.create_thread(
            agent_identifier=agent_identifier,
            session_identifier=session_identifier,
            name=payload.name,
            retained_skills=payload.retained_skills,
        )
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except SlugConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return ThreadResponse(
        id=thread.id,
        name=thread.name,
        created_at=thread.created_at,
        last_touched_at=thread.last_touched_at,
        is_open=thread.is_open,
        status=thread.status,
        mode=thread.mode,
        phase=thread.phase,
        mode_label=thread.mode_label,
    )


@router.get("", status_code=status.HTTP_307_TEMPORARY_REDIRECT)
async def redirect_to_open_thread(
    agent_identifier: str,
    session_identifier: str,
) -> RedirectResponse:
    """Redirect to the active open thread for this session."""
    store = get_harness_store()
    try:
        agent = store.resolve_agent(agent_identifier)
        session = resolve_session(agent, session_identifier)
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    open_thread = session.get_open_thread()
    target_ident = open_thread.name if open_thread.name else str(open_thread.id)
    url = (
        f"/api/v-alpha/agent/{agent_identifier}/session/{session_identifier}/thread/{target_ident}"
    )
    return RedirectResponse(url=url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@router.get("/{thread_identifier}")
async def stream_thread(
    agent_identifier: str,
    session_identifier: str,
    thread_identifier: str,
    request: Request,
    follow: bool = True,
) -> StreamingResponse:
    """Stream thread messages over SSE (past events followed by live broadcasts)."""
    store = get_harness_store()
    try:
        agent = store.resolve_agent(agent_identifier)
        session = resolve_session(agent, session_identifier)
        thread = resolve_thread(session, thread_identifier)
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    registry = get_runner_registry()
    runner = registry.get_runner(session, agent=agent)
    accept_header = request.headers.get("accept")

    return StreamingResponse(
        runner.stream_thread_events(
            thread=thread,
            accept_header=accept_header,
            follow=follow,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{thread_identifier}/status", response_model=ThreadStatusResponse)
async def get_thread_status(
    agent_identifier: str,
    session_identifier: str,
    thread_identifier: str,
) -> ThreadStatusResponse:
    """Get the current execution status of a thread."""
    store = get_harness_store()
    try:
        agent = store.resolve_agent(agent_identifier)
        session = resolve_session(agent, session_identifier)
        thread = resolve_thread(session, thread_identifier)
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return ThreadStatusResponse(status=thread.status)


@router.post("/{thread_identifier}", response_model=ThreadResponse)
async def update_thread(
    agent_identifier: str,
    session_identifier: str,
    thread_identifier: str,
    payload: ThreadUpdateRequest,
) -> ThreadResponse:
    """Update a thread's name with the full updated object."""
    store = get_harness_store()
    try:
        thread = store.update_thread(
            agent_identifier=agent_identifier,
            session_identifier=session_identifier,
            thread_identifier=thread_identifier,
            name=payload.name,
        )
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except SlugConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return ThreadResponse(
        id=thread.id,
        name=thread.name,
        created_at=thread.created_at,
        last_touched_at=thread.last_touched_at,
        is_open=thread.is_open,
        status=thread.status,
        mode=thread.mode,
        phase=thread.phase,
        mode_label=thread.mode_label,
    )


@router.post("/{thread_identifier}/accept", response_model=ThreadResponse)
async def accept_thread(
    agent_identifier: str,
    session_identifier: str,
    thread_identifier: str,
) -> ThreadResponse:
    """Accept the active thread, merge its Sync PR, and spawn a new thread with a new Sync PR."""
    store = get_harness_store()
    try:
        new_thread = store.accept_thread(
            agent_identifier=agent_identifier,
            session_identifier=session_identifier,
            thread_identifier=thread_identifier,
        )
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return ThreadResponse(
        id=new_thread.id,
        name=new_thread.name,
        created_at=new_thread.created_at,
        last_touched_at=new_thread.last_touched_at,
        is_open=new_thread.is_open,
        status=new_thread.status,
        mode=new_thread.mode,
        phase=new_thread.phase,
        mode_label=new_thread.mode_label,
    )
