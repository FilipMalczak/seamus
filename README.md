# Seamus

A deep agent harness that I fully own and can customize.

## Prerequisites

- **Python**: 3.12+
- **uv**: Fast Python package and environment manager

## Quick Start

### 1. Environment Setup

Clone the repository and synchronize the environment:

```bash
uv sync
```

This creates a local `.venv` and installs all dependencies and development tools.

### 2. Running Quality Checks

Run all verification tools through `uv`:

```bash
# Run tests
uv run pytest

# Check code formatting & linting
uv run ruff check .
uv run ruff format --check .

# Type checking
uv run mypy
```

### 3. Formatting Code

To automatically format code:

```bash
uv run ruff format .
uv run ruff check --fix .
```

## Repository Structure

```
├── AGENTS.md        # Repository-wide guidelines, git workflows, and rules
├── README.md        # Project overview and setup instructions
├── pyproject.toml   # Project configuration, dependencies, and tool settings
├── uv.lock          # Locked dependencies for reproducible environments
├── decisions/       # Append-only architectural and project-direction decision records
├── knowledge/       # Durable implementation knowledge (vocabulary, requirements, etc.)
├── src/
│   └── seamus/      # Core package source code
└── tests/           # Automated test suite
```
