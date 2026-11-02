"""Routes package for Seamus FastAPI application."""

from fastapi import APIRouter

from seamus.server.routes.agents import router as agents_router
from seamus.server.routes.config import router as config_router
from seamus.server.routes.sessions import router as sessions_router
from seamus.server.routes.settings import router as settings_router
from seamus.server.routes.system import router as system_router
from seamus.server.routes.threads import router as threads_router

api_router = APIRouter(prefix="/api/v-alpha")
api_router.include_router(config_router)
api_router.include_router(settings_router)
api_router.include_router(agents_router)
api_router.include_router(sessions_router)
api_router.include_router(threads_router)
api_router.include_router(system_router)

__all__ = ["api_router"]
