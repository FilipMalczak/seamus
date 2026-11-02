# Seamus

A deep agent harness that I fully own and can customize.

## Prerequisites

- **Operating System**: Linux (primary and required; macOS and Windows compatibility is tracked as technical debt).
- **Python**: 3.12+
- **uv**: Fast Python package and environment manager
- **Node.js**: v20+ and npm (for frontend development)
- **Docker & Docker Compose**: Required for containerized multi-service deployment (PostgreSQL, Gitea, OpenSandbox, backend, and frontend) and for the 1-click launch script (`./run.sh`).

---

## Running Seamus

Seamus comprises a full agent execution and management stack:
- **FastAPI Backend**: DeepAgent runtime, AG-UI event streaming (`/api/v-alpha/`), Git-backed workspace persistence, and OpenSandbox execution manager.
- **React Frontend**: Single-page UI with tree navigation (agents, sessions, threads), interactive markdown rendering, collapsible reasoning/tool traces, and configuration modals.
- **OpenSandbox**: Isolated Linux container environment for sandboxed command and filesystem operations.
- **Gitea & PostgreSQL**: Version-controlled Git repository service maintaining commit logs, branches, and audit histories for all agents and sessions.

### Option 1: 1-Click Launch Script (`./run.sh`)

Ensure the entire application stack is running and open it in your default browser:

```bash
# Ensure services are up and open browser
./run.sh

# Rebuild and restart application containers while preserving data
./run.sh --restart
# or: ./run.sh -r

# Full clean start: wipe all containers, volumes, and workspace storage
./run.sh --clean
# or: ./run.sh -c

# Show usage and available flags
./run.sh --help
# or: ./run.sh -h
```

#### Script Flags & Behavior

- **Default (`./run.sh`)**:
  - Checks whether the UI (`http://localhost:3000`), backend health endpoint (`http://localhost:8000/health`), and Gitea health endpoint (`http://localhost:3001/api/v1/version`) are all running and responsive.
  - **Already running**: No-op container rebuild; immediately opens `http://localhost:3000` in your default browser.
  - **Not running or degraded**: Starts all stack services (`postgres`, `gitea`, `gitea-init`, `opensandbox`, `backend`, `frontend`) in background detached mode with image rebuilding via `docker compose up -d --build`.
  - Polls health checks until all services are healthy (up to a 60-second timeout).
  - Ensures the default Gitea administrator user (`seamus`) exists.
  - Opens `http://localhost:3000` in the system default browser (supporting Linux `xdg-open` / `sensible-browser`, macOS `open`, and Windows/WSL `powershell.exe` / `cmd.exe`).

- **Restart (`-r`, `--restart`)**:
  - Rebuilds and recreates only the application containers for which Seamus owns the Docker image (`backend`, `frontend`, `opensandbox`) via `docker compose up -d --build opensandbox backend frontend`.
  - Updates application code changes immediately while preserving all persistent data volumes and infrastructure services (`gitea`, `postgres`).
  - Waits for service health checks and opens the UI in your browser.

- **Clean (`-c`, `--clean`)**:
  - Performs a complete reset to a fresh state.
  - Tears down all running containers and removes anonymous and named persistent Docker volumes via `docker compose down -v --remove-orphans`.
  - Deletes all local filesystem clone directories (`${SEAMUS_WORKSPACE_DIR:-.seamus/workspaces}`) and runtime auth state (`.seamus/opensandbox`).
  - Rebuilds and launches all services from scratch (`docker compose up -d --build`).
  - Waits for health checks, provisions the default Gitea admin user, and opens the UI in your browser.

- **Help (`-h`, `--help`)**:
  - Prints command usage instructions and option descriptions, then exits immediately.

### Option 2: Multi-Service Docker Compose

Run all services in containers:

```bash
# Build and start all services in the foreground
docker compose up --build

# Or run in the background (detached)
docker compose up -d --build

# Stop running services
docker compose down

# Stop running services and remove persistent data volumes
docker compose down -v
```

**Service Endpoints:**
- **Frontend (UI)**: [http://localhost:3000](http://localhost:3000)
- **Backend API & Swagger Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Backend Health Check**: [http://localhost:8000/health](http://localhost:8000/health)
- **Gitea Web Interface & Git Server**: [http://localhost:3001](http://localhost:3001) (default admin: `seamus` / `seamus-password-123`)
- **OpenSandbox**: Internal port `8080` (managed by the backend via shared auth key)
- **PostgreSQL**: Internal port `5432` (database backing Gitea)

### Option 3: Local Development (Side-by-Side)

When developing the backend or frontend locally without containerizing them:

1. **Start backing infrastructure (PostgreSQL, Gitea, OpenSandbox):**
   ```bash
   docker compose up -d postgres gitea gitea-init opensandbox
   ```

2. **Configure environment variables:**
   ```bash
   cp .env.template .env
   # Edit .env with your OPENROUTER_API_KEY, LOGFIRE_TOKEN, etc.
   ```

3. **Terminal 1 — Backend Server:**
   ```bash
   # Synchronize Python virtual environment
   uv sync

   # Run FastAPI backend with live reload
   uv run uvicorn seamus.server.app:create_app --factory --reload --host 127.0.0.1 --port 8000
   ```

4. **Terminal 2 — React Frontend:**
   ```bash
   cd ui
   npm install
   npm run dev
   ```

   The Vite dev server will start at [http://localhost:3000](http://localhost:3000) and automatically proxy all `/api` and `/health` requests to `http://127.0.0.1:8000`.

### Option 4: Unified Production Serving (Single Process)

The backend server is configured to serve the compiled React SPA directly at root `/`:

```bash
# 1. Compile React production bundle
cd ui && npm install && npm run build && cd ..

# 2. Run backend (serves both API and UI static assets)
uv run uvicorn seamus.server.app:create_app --factory --host 0.0.0.0 --port 8000
```

Navigate to [http://localhost:8000](http://localhost:8000) to view the application.

---

## Code Quality & Verification

Run all verification tools through `uv` and `npm`:

```bash
# Backend test suite
uv run pytest

# Python linting and code formatting checks
uv run ruff check .
uv run ruff format --check .

# Python strict static type checking
uv run mypy

# Frontend TypeScript check and production build
cd ui && npm run build && cd ..
```

To automatically format Python code:

```bash
uv run ruff format .
uv run ruff check --fix .
```

---

## Repository Structure

```
├── AGENTS.md            # Repository guidelines, git workflows, and development rules
├── README.md            # Setup, execution, and architecture guide
├── LICENSE              # MIT License
├── Dockerfile           # Backend container build specification
├── docker-compose.yml   # Multi-service container orchestration (frontend, backend, opensandbox, gitea, postgres)
├── run.sh               # One-click health check, launch, and browser opening script
├── pyproject.toml       # Python dependencies, Ruff, Mypy, and Pytest configuration
├── uv.lock              # Deterministic Python lockfile
├── .env.template        # Environment configuration template
├── decisions/           # Architectural and project-direction decision records (ADRs)
├── knowledge/           # Durable implementation knowledge (abstractions, architecture, etc.)
├── opensandbox/         # OpenSandbox container configuration and Dockerfile
├── src/
│   └── seamus/          # Python backend package
│       ├── config/      # Singleton ConfigTemplate and AgentConfig models
│       ├── domain/      # Entities (Agent, Session, Thread, Status) and slug resolution
│       ├── harness/     # DeepAgent runner, checkpointer, and event broadcaster
│       ├── persistence/ # Git persistence provider, Gitea API client, and workspace manager
│       ├── server/      # FastAPI application, REST endpoints (/api/v-alpha/), and schemas
│       └── spike/       # Experimental prototypes and spikes
├── tests/               # Python test suite
└── ui/                  # React 19 + TypeScript + Vite frontend
    ├── Dockerfile       # Frontend container build specification (Nginx)
    ├── nginx.conf       # Reverse-proxy configuration for SPA and SSE buffering
    ├── package.json     # Node.js dependencies (lucide-react, react-markdown)
    ├── src/
    │   ├── api/         # Typed API client and SSE stream reader
    │   ├── components/  # Sidebar (tree navigation), ChatArea, MarkdownRenderer, ConfigModal, etc.
    │   └── hooks/       # useAgentsTree and useThreadStream hooks
    └── vite.config.ts   # Vite dev server and proxy configuration
```

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
