"""FastAPI application factory for the Seamus harness server."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from seamus.server.routes import api_router
from seamus.telemetry import instrument_fastapi, setup_telemetry

REPO_ROOT = Path(__file__).resolve().parents[3]
UI_DIST_DIR = REPO_ROOT / "ui" / "dist"


def create_app(dist_dir: Path | None = None) -> FastAPI:
    """Create, configure, and return the FastAPI application instance."""
    setup_telemetry()

    app = FastAPI(
        title="Seamus Agent Harness Server",
        description=(
            "FastAPI harness service managing DeepAgent agents, sessions, and AG-UI event streaming"
        ),
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    instrument_fastapi(app)

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

    # Mount static assets and index route if built UI distribution exists
    target_dist = dist_dir if dist_dir is not None else UI_DIST_DIR
    assets_dir = target_dist / "assets"
    index_file = target_dist / "index.html"

    if index_file.exists() and assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

        @app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
        async def serve_ui_root() -> FileResponse:
            """Serve the React web UI single-page application entrypoint."""
            return FileResponse(index_file)

    return app
