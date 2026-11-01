"""Routes for agent lifecycle operations."""

from fastapi import APIRouter, HTTPException, status

from seamus.config.template import get_config_template_store
from seamus.domain.entities import Agent
from seamus.domain.resolution import EntityNotFoundError
from seamus.harness.store import SlugConflictError, get_harness_store
from seamus.server.schemas import (
    AgentCreateRequest,
    AgentDetailResponse,
    AgentSummaryResponse,
    AgentUpdateRequest,
    SessionSummaryResponse,
)

router = APIRouter(tags=["agents"])


def _to_agent_detail(agent: Agent) -> AgentDetailResponse:
    sessions = [
        SessionSummaryResponse(
            id=s.id,
            agent_id=s.agent_id,
            name=s.name,
            created_at=s.created_at,
            last_touched_at=s.last_touched_at,
            config=s.config,
            status=s.status,
            provenance=s.provenance,
            lineage=s.lineage,
        )
        for s in sorted(agent.sessions.values(), key=lambda s: s.created_at)
    ]
    return AgentDetailResponse(
        id=agent.id,
        name=agent.name,
        created_at=agent.created_at,
        last_touched_at=agent.last_touched_at,
        config=agent.config,
        sessions=sessions,
    )


@router.get("/agents", response_model=list[AgentSummaryResponse])
@router.get("/agent", response_model=list[AgentSummaryResponse])
async def list_agents() -> list[AgentSummaryResponse]:
    """List all registered agents."""
    store = get_harness_store()
    return [
        AgentSummaryResponse(
            id=a.id,
            name=a.name,
            created_at=a.created_at,
            last_touched_at=a.last_touched_at,
            config=a.config,
        )
        for a in store.list_agents()
    ]


@router.post(
    "/agents",
    response_model=AgentSummaryResponse,
    status_code=status.HTTP_201_CREATED,
)
@router.post(
    "/agent",
    response_model=AgentSummaryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_agent(payload: AgentCreateRequest) -> AgentSummaryResponse:
    """Create a new agent by deriving from the template and applying overrides."""
    template_store = get_config_template_store()
    agent_config = template_store.derive_agent_config(payload.config)

    store = get_harness_store()
    try:
        agent = store.create_agent(config=agent_config, name=payload.name)
    except SlugConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return AgentSummaryResponse(
        id=agent.id,
        name=agent.name,
        created_at=agent.created_at,
        last_touched_at=agent.last_touched_at,
        config=agent.config,
    )


@router.get("/agent/{agent_identifier}", response_model=AgentDetailResponse)
async def get_agent(agent_identifier: str) -> AgentDetailResponse:
    """Get detailed agent representation including all sessions."""
    store = get_harness_store()
    try:
        agent = store.resolve_agent(agent_identifier)
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return _to_agent_detail(agent)


@router.post("/agent/{agent_identifier}", response_model=AgentDetailResponse)
async def update_agent(
    agent_identifier: str,
    payload: AgentUpdateRequest,
) -> AgentDetailResponse:
    """Update agent name and configuration with full updated object."""
    store = get_harness_store()
    try:
        agent = store.update_agent(
            identifier=agent_identifier,
            config=payload.config,
            name=payload.name,
        )
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except SlugConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return _to_agent_detail(agent)
