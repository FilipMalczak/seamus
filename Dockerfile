FROM python:3.12-slim

# Install git for repository tracking and persistence
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Install project dependencies
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy application source code
COPY src ./src
COPY README.md ./
RUN uv sync --frozen --no-dev

# Expose server port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=5s --timeout=3s --retries=5 --start-period=5s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Run FastAPI backend with Uvicorn
CMD ["uv", "run", "uvicorn", "seamus.server.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]

