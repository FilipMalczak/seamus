"""Shared fixtures for the end-to-end test suite.

The fixtures here wire a *real* Seamus stack (config store, harness store,
Git-backed workspace manager, DeepAgent runner, FastAPI routes) with two
deterministic substitutions:

* the ``steerable`` inference provider replaces the live LLM with a scripted
  response queue, so no network call or inference randomness is involved;
* the OpenSandbox backend is replaced with an in-process host-filesystem stub,
  so file writes, mount policies and exit codes are observable without a live
  container.

Everything else — event streaming, checkpointing, branch slicing, Sync PR
lifecycle — runs the production code paths.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import pytest_asyncio

from seamus.config.models import (
    AgentConfig,
    DaemonNamingConfig,
    DaemonsConfig,
    InferenceConfig,
    InferenceFormat,
    SteerableConfig,
    SteerableEmptyQueueStrategy,
)
from seamus.config.settings import (
    SystemSettings,
    SystemSettingsStore,
    reset_system_settings_store,
)
from seamus.config.template import ConfigTemplateStore, reset_config_template_store
from seamus.harness.runner import (
    SessionAgentRunner,
    get_runner_registry,
    reset_runner_registry,
)
from seamus.harness.steerable import (
    SteerableResponse,
    SteerableToolCall,
    agent_instance_id,
    daemon_instance_id,
    get_steerable_registry,
    reset_steerable_registry,
)
from seamus.harness.store import HarnessStore, reset_harness_store
from seamus.persistence.workspace import get_workspace_manager, reset_workspace_manager
from seamus.server.app import create_app
from tests.e2e.stub_sandbox import StubSandboxBackend, StubSandboxSettings


@pytest.fixture(autouse=True)
def reset_globals() -> Iterator[None]:
    """Reset every process-wide singleton between tests."""
    reset_config_template_store(None)
    reset_system_settings_store(None)
    reset_harness_store(None)
    reset_runner_registry()
    reset_steerable_registry()
    reset_workspace_manager(None)
    yield
    reset_config_template_store(None)
    reset_system_settings_store(None)
    reset_harness_store(None)
    reset_runner_registry()
    reset_steerable_registry()
    reset_workspace_manager(None)


@pytest.fixture
def steerable_template() -> AgentConfig:
    """Return a config template that uses the scripted inference provider."""
    return AgentConfig(
        inference=InferenceConfig(
            format=InferenceFormat.STEERABLE,
            base_url="https://openrouter.ai/api/v1",
            steerable=SteerableConfig(
                empty_queue_strategy=SteerableEmptyQueueStrategy.WAIT,
                wait_timeout=10.0,
            ),
        ),
        model_name="steerable-model",
    )


@pytest.fixture
def steerable_store(steerable_template: AgentConfig) -> HarnessStore:
    """Install a harness store seeded with the steerable config template."""
    template_store = ConfigTemplateStore(initial_template=steerable_template)
    reset_config_template_store(template_store)
    reset_system_settings_store(SystemSettingsStore(initial_settings=SystemSettings()))
    store = HarnessStore()
    reset_harness_store(store)
    return store


@pytest.fixture
def stub_sandbox(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[StubSandboxBackend]]:
    """Replace the OpenSandbox backend with the in-process stub.

    Yields the list of stub backends created so far, so tests can inspect the
    mount flags of the sandbox that served a session.
    """
    created: list[StubSandboxBackend] = []
    original = StubSandboxBackend

    def factory(**kwargs: Any) -> StubSandboxBackend:
        kwargs.setdefault("settings", StubSandboxSettings())
        backend = original(**kwargs)
        created.append(backend)
        return backend

    import seamus.harness.runner as runner_module

    monkeypatch.setattr(runner_module, "SeamusOpenSandboxBackend", factory)
    yield created


@pytest_asyncio.fixture
async def client(
    steerable_store: HarnessStore, stub_sandbox: list[StubSandboxBackend]
) -> AsyncIterator[httpx.AsyncClient]:
    """Provide an async HTTP client bound to the Seamus ASGI app."""
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


@pytest.fixture
def queue_agent_turn() -> Any:
    """Return a helper that queues a scripted response for a session's agent model."""

    def _queue(
        session_id: str,
        *,
        text: str | None = None,
        reasoning: str | None = None,
        tool_calls: list[SteerableToolCall] | None = None,
        role: str = "agent",
    ) -> None:
        instance_id = (
            agent_instance_id(session_id) if role == "agent" else daemon_instance_id(session_id)
        )
        instance = get_steerable_registry().get_or_create(instance_id, role)
        instance.push(
            SteerableResponse(
                text=text,
                reasoning=reasoning,
                tool_calls=list(tool_calls or []),
            )
        )

    return _queue


@pytest.fixture
def make_session(steerable_store: HarnessStore) -> Any:
    """Return a helper creating an agent, a session and their identifiers."""

    def _make(
        name: str = "e2e-agent",
        *,
        mode: str = "plan",
        phase: str | None = None,
        naming_daemon: bool = False,
    ) -> dict[str, Any]:
        config = AgentConfig(
            inference=InferenceConfig(
                format=InferenceFormat.STEERABLE,
                base_url="https://openrouter.ai/api/v1",
                steerable=SteerableConfig(wait_timeout=10.0),
            ),
            model_name="steerable-model",
            mode=mode,
            daemons=DaemonsConfig(
                naming=DaemonNamingConfig(
                    enabled=naming_daemon,
                    model="steerable-model" if naming_daemon else None,
                )
            ),
        )
        agent = steerable_store.create_agent(config=config, name=name)

        session = steerable_store.create_session(agent_identifier=str(agent.id))

        thread = session.get_open_thread()
        if phase is not None and thread is not None:
            thread.mode = mode
            thread.phase = phase
        return {
            "agent": agent,
            "session": session,
            "thread": thread,
            "agent_id": str(agent.id),
            "session_id": str(session.id),
            "thread_id": str(thread.id) if thread else None,
        }

    return _make


@pytest.fixture
def resolve_session(steerable_store: HarnessStore) -> Any:
    """Return a helper resolving a session entity by its identifier."""

    def _resolve(session_id: str) -> Any:
        for agent in steerable_store.list_agents():
            for session in agent.sessions.values():
                if str(session.id) == str(session_id):
                    return session
        raise LookupError(f"Session {session_id} not found")

    return _resolve


@pytest.fixture
def session_dir(steerable_store: HarnessStore) -> Any:
    """Return a helper resolving a session's on-disk workspace directories."""

    def _dirs(session: Any) -> dict[str, Path]:
        ws_mgr = get_workspace_manager()
        return {
            "workspace": ws_mgr.get_session_workspace_path(session.agent_id, session.id),
            "data": ws_mgr.get_session_data_dir(session.agent_id, session.id),
            "artifacts": ws_mgr.get_session_artifacts_dir(session.agent_id, session.id),
            "notes": ws_mgr.get_session_notes_dir(session.agent_id, session.id),
        }

    return _dirs


@pytest_asyncio.fixture
async def running_runner(steerable_store: HarnessStore) -> Any:
    """Return a helper that runs a session to quiescence and returns its runner."""

    async def _run(session: Any, *, timeout: float = 30.0) -> SessionAgentRunner:
        agent = steerable_store.resolve_agent(str(session.agent_id))
        runner = get_runner_registry().get_runner(session, agent=agent)
        task = runner._active_task
        if task is not None:
            await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
        return runner

    return _run


@pytest.fixture
def gitea_enabled() -> None:
    """Skip a test when Gitea-backed persistence is unavailable.

    The end-to-end suite runs against an ephemeral Gitea container when Docker
    is available (see ``tests/conftest.py``). When it is not, persistence is
    disabled and the Git-backed behaviours under test cannot be exercised.
    """
    from seamus.persistence.config import get_persistence_settings

    if not get_persistence_settings().enabled:
        pytest.skip("Gitea-backed persistence is disabled for this test run")


@pytest.fixture
def cleanup_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure background daemons do not inherit an API key from the host."""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPEN_ROUTER_API_KEY", raising=False)
    os.environ.setdefault("SEAMUS_TEST_IN_MEMORY", "")
