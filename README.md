# Seamus

A deep agent harness that I fully own and can customize.

## Prerequisites

- **Python**: 3.12+
- **uv**: Fast Python package and environment manager
- **Node.js**: v20+ and npm (for frontend development)
- **Docker & Docker Compose**: (optional, for containerized multi-service deployment)

---

## Running Seamus (UI & Backend)

Seamus consists of a Python FastAPI backend (DeepAgent runtime & AG-UI streaming under `/api/v-alpha/`) and a React single-page frontend.

### Option 1: 1-Click Launch Script (`./run.sh`)

Ensure the entire application stack is up and open it in your browser:

```bash
./run.sh
```

- If services are already running on `http://localhost:3000` $\to$ **no-op** (opens browser immediately).
- If services are stopped $\to$ spins up both `backend` and `frontend` via Docker Compose, waits for health checks, and opens the default browser.

### Option 2: Multi-Service Docker Compose

Run both services in containers with live reverse-proxying:

```bash
# Build and start in foreground
docker compose up --build

# Or run in background
docker compose up -d --build

# Stop services
docker compose down
```

- **Frontend (UI)**: [http://localhost:3000](http://localhost:3000)
- **Backend API & Swagger Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Health Check**: [http://localhost:8000/health](http://localhost:8000/health)

### Option 3: Local Development (Side-by-Side)

Run backend with auto-reload and frontend with Vite hot module replacement (HMR):

**Terminal 1 — Backend Server:**
```bash
# Synchronize Python virtual environment
uv sync

# Run FastAPI backend with live reload
uv run uvicorn seamus.server.app:create_app --factory --reload --host 127.0.0.1 --port 8000
```

**Terminal 2 — React Frontend:**
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

# Python linting and code formatting
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
├── Dockerfile           # Backend container build specification
├── docker-compose.yml   # Multi-service container orchestration (frontend + backend)
├── run.sh               # One-click health check, launch, and browser opening script
├── pyproject.toml       # Python dependencies, Ruff, Mypy, and Pytest configuration
├── uv.lock              # Deterministic Python lockfile
├── decisions/           # Architectural and project-direction decision records (ADRs)
├── knowledge/           # Durable implementation knowledge (abstractions, architecture, etc.)
├── src/
│   └── seamus/          # Python backend package
│       ├── config/      # Singleton ConfigTemplate and AgentConfig models
│       ├── domain/      # Entities (Agent, Session, Thread, Status) and slug resolution
│       ├── harness/     # DeepAgent runner, in-memory checkpointer, and event broadcaster
│       └── server/      # FastAPI application, REST endpoints (/api/v-alpha/), and schemas
├── tests/               # Python test suite
└── ui/                  # React 19 + TypeScript + Vite frontend
    ├── Dockerfile       # Frontend container build specification (Nginx)
    ├── nginx.conf       # Reverse-proxy configuration for SPA and SSE buffering
    ├── package.json     # Node.js dependencies (lucide-react, react-markdown)
    ├── src/
    │   ├── api/         # Typed API client and SSE stream reader
    │   ├── components/  # Sidebar (tree navigation), ChatArea, ConfigModal, etc.
    │   └── hooks/       # useAgentsTree and useThreadStream hooks
    └── vite.config.ts   # Vite dev server and proxy configuration
```
