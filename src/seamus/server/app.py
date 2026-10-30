"""FastAPI application factory for the Seamus harness server."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from seamus.server.routes import api_router


def create_app() -> FastAPI:
    """Create, configure, and return the FastAPI application instance."""
    app = FastAPI(
        title="Seamus Agent Harness Server",
        description=(
            "FastAPI harness service managing DeepAgent agents, sessions, and AG-UI event streaming"
        ),
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # Enable permissive CORS for web UI clients
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount API routes under /api/v-alpha/
    app.include_router(api_router)

    @app.get("/health", tags=["system"])
    async def health_check() -> dict[str, str]:
        """System health probe endpoint."""
        return {"status": "ok", "service": "seamus"}

    return app
