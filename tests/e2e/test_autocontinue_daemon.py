"""End-to-end tests for the autocontinue daemon.

Tests that session failures trigger the autocontinue daemon via steerable simulation,
verifying both the exact input payload passed into the daemon and the resulting harness
behavior for boolean retry and halt decisions across multi-turn lineage.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest

from seamus.config.models import (
    AgentConfig,
    DaemonAutocontinueConfig,
    DaemonNamingConfig,
    DaemonsConfig,
    InferenceConfig,
    InferenceFormat,
    SteerableConfig,
    SteerableEmptyQueueStrategy,
)
from seamus.harness.runner import get_runner_registry
from seamus.harness.steerable import (
    SteerableError,
    SteerableResponse,
    SteerableToolCall,
    agent_instance_id,
    daemon_instance_id,
    get_steerable_registry,
)


async def _drain(runner: Any, *, timeout: float = 30.0) -> None:
    """Wait for a runner's active task to finish."""
    task = runner._active_task
    if task is not None and not task.done():
        await asyncio.wait_for(asyncio.shield(task), timeout=timeout)


def _make_autocontinue_session(
    store: Any,
    name: str,
) -> dict[str, Any]:
    """Create a session with steerable agent provider and steerable autocontinue daemon."""
    config = AgentConfig(
        inference=InferenceConfig(
            format=InferenceFormat.STEERABLE,
            base_url="https://openrouter.ai/api/v1",
            steerable=SteerableConfig(
                empty_queue_strategy=SteerableEmptyQueueStrategy.WAIT,
                wait_timeout=5.0,
            ),
        ),
        model_name="steerable-model",
        mode="chat",
        daemons=DaemonsConfig(
            naming=DaemonNamingConfig(enabled=False),
            autocontinue=DaemonAutocontinueConfig(
                enabled=True,
                model="steerable-autocontinue",
                provider=InferenceConfig(
                    format=InferenceFormat.STEERABLE,
                    base_url="https://openrouter.ai/api/v1",
                    steerable=SteerableConfig(
                        empty_queue_strategy=SteerableEmptyQueueStrategy.WAIT,
                        wait_timeout=5.0,
                    ),
                ),
            ),
        ),
    )
    agent = store.create_agent(config=config, name=name)
    session = next(iter(agent.sessions.values()))
    thread = session.get_open_thread()
    return {
        "agent": agent,
        "session": session,
        "thread": thread,
        "agent_id": str(agent.id),
        "session_id": str(session.id),
        "thread_id": str(thread.id) if thread else None,
    }


@pytest.mark.asyncio
async def test_autocontinue_steerable_retry_confirms_input_and_branches(
    client: httpx.AsyncClient,
    steerable_store: Any,
    resolve_session: Any,
) -> None:
    """When a session fails and autocontinue responds 'yes', daemon input is verified."""
    ctx = _make_autocontinue_session(steerable_store, "autocontinue-retry-agent")
    session = resolve_session(ctx["session_id"])
    agent = ctx["agent"]

    # Configure session 1 agent model to fail immediately on empty queue
    reg = get_steerable_registry()
    inst_agent = reg.get_or_create(agent_instance_id(session.id), role="agent")
    inst_agent.strategy = SteerableEmptyQueueStrategy.ERROR

    # Script the autocontinue daemon response to 'yes'
    daemon_id = daemon_instance_id(session.id, daemon="autocontinue")
    inst_daemon = reg.get_or_create(daemon_id, role="daemon")
    inst_daemon.push(SteerableResponse(text="yes"))

    # Post message to trigger unhandled provider failure
    await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "Please do something that fails."},
    )

    runner = get_runner_registry().get_runner(session)
    await _drain(runner)

    # 1. Verify exact input passed into the autocontinue daemon
    assert inst_daemon.last_invocation is not None
    prompt_text = inst_daemon.last_invocation[0].content
    assert isinstance(prompt_text, str)
    assert "Instructions:" in prompt_text
    assert "Retry History & Execution Span:" in prompt_text
    assert "Session lineage depth: 0" in prompt_text
    assert "Prior parent session: none" in prompt_text
    assert "Total errors in current thread: 1" in prompt_text
    assert "Error Type: SteerableQueueEmptyError" in prompt_text
    assert "Please do something that fails." in prompt_text

    # 2. Verify root session failed
    assert session.status.value == "FAILED"

    # 3. Verify a new child session was created under the agent
    assert len(agent.sessions) == 2
    child_session = [s for s in agent.sessions.values() if s.id != session.id][0]
    assert child_session.provenance is not None
    assert child_session.provenance.parent_session_id == session.id
    assert child_session.provenance.branch_position == "after"


@pytest.mark.asyncio
async def test_autocontinue_multi_turn_bubbles_and_second_failure(
    client: httpx.AsyncClient,
    steerable_store: Any,
    resolve_session: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Multi-turn test:

    I. Session 1 runs and encounters an exception.
    II. Daemon decides to retry ('true'). Daemon input for Session 1 is verified.
    III. Session 2 is branched; multiple bubbles succeed (reasoning, tool call, text).
    IV. A second exception hits Session 2; daemon is called again.
    V. Daemon input for Session 2 is verified (lineage depth, parent session, bubbles).
    VI. Daemon decides 'no' ('false'); harness halts without further branching.
    """
    import seamus.harness.web_search as web_search_module

    class StubDDGS:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def text(self, query: str, max_results: int = 5) -> list[dict[str, str]]:
            return [
                {
                    "title": "Deployment guide",
                    "href": "https://example.invalid/deploy",
                    "body": "Deployment instructions.",
                }
            ]

    monkeypatch.setattr(web_search_module, "DDGS", StubDDGS)

    ctx = _make_autocontinue_session(steerable_store, "autocontinue-multi-agent")
    session_1 = resolve_session(ctx["session_id"])
    agent = ctx["agent"]

    reg = get_steerable_registry()
    inst_agent_1 = reg.get_or_create(agent_instance_id(session_1.id), role="agent")
    inst_agent_1.strategy = SteerableEmptyQueueStrategy.ERROR

    # I. Script daemon on session 1 to return 'true'
    daemon_id_1 = daemon_instance_id(session_1.id, daemon="autocontinue")
    inst_daemon_1 = reg.get_or_create(daemon_id_1, role="daemon")
    inst_daemon_1.push(SteerableResponse(text="true"))

    # Post initial user input on session 1 (empty agent queue -> SteerableQueueEmptyError)
    await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "First task: deploy application."},
    )

    runner_1 = get_runner_registry().get_runner(session_1)
    await _drain(runner_1)

    # Verify session 1 failed
    assert session_1.status.value == "FAILED"

    # II. Verify daemon input on session 1
    assert inst_daemon_1.last_invocation is not None
    prompt_1 = inst_daemon_1.last_invocation[0].content
    assert isinstance(prompt_1, str)
    assert "Session lineage depth: 0" in prompt_1
    assert "Prior parent session: none" in prompt_1
    assert "Total errors in current thread: 1" in prompt_1
    assert "Error Type: SteerableQueueEmptyError" in prompt_1
    assert "First task: deploy application." in prompt_1

    # Verify session 2 was branched
    assert len(agent.sessions) == 2
    session_2 = [s for s in agent.sessions.values() if s.id != session_1.id][0]
    assert session_2.provenance is not None
    assert session_2.provenance.parent_session_id == session_1.id

    # III. Script session 2: 2-3 bubbles succeed
    agent_id_2 = agent_instance_id(session_2.id)
    daemon_id_2 = daemon_instance_id(session_2.id, daemon="autocontinue")
    inst_agent_2 = reg.get_or_create(agent_id_2, role="agent")
    inst_daemon_2 = reg.get_or_create(daemon_id_2, role="daemon")

    # Script daemon 2 to reply 'no' when the second failure hits
    inst_daemon_2.push(SteerableResponse(text="no"))

    # Script agent 2 responses:
    # Bubble 1: reasoning span
    # Bubble 2: tool call to web_search (succeeds and produces a tool result bubble)
    # Bubble 3: assistant text message
    inst_agent_2.push(
        SteerableResponse(
            reasoning="Analyzing the deployment requirements carefully.",
            tool_calls=[
                SteerableToolCall(
                    name="web_search",
                    args={"query": "deploy instructions"},
                )
            ],
        )
    )
    inst_agent_2.push(
        SteerableResponse(
            text="Deployment docs retrieved. Ready for subsequent pipeline step.",
        )
    )

    runner_2 = get_runner_registry().get_runner(session_2)
    await _drain(runner_2)

    # Verify that session 2 successfully executed the bubbles
    thread_2 = session_2.get_open_thread()
    assert thread_2 is not None
    event_types = [
        getattr(e, "type", None) or (e.get("type") if isinstance(e, dict) else "")
        for e in thread_2.events
    ]
    assert any("REASONING" in str(et) for et in event_types), "Reasoning bubble expected"
    assert any("TOOL_CALL" in str(et) for et in event_types), "Tool call bubble expected"
    assert any("TEXT_MESSAGE" in str(et) for et in event_types), "Text bubble expected"

    # IV. Trigger a second exception on session 2
    # Switch agent 2 strategy to ERROR so the next message triggers failure
    inst_agent_2.strategy = SteerableEmptyQueueStrategy.ERROR
    await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{session_2.id}/input",
        json={"message": "Second task: execute integration tests."},
    )
    await _drain(runner_2)

    # Session 2 has now failed
    assert session_2.status.value == "FAILED"

    # V. Verify all details of the second daemon invocation on session 2
    assert inst_daemon_2.last_invocation is not None
    prompt_2 = inst_daemon_2.last_invocation[0].content
    assert isinstance(prompt_2, str)
    assert "Session lineage depth: 1" in prompt_2
    assert f"Prior parent session: {session_1.id}" in prompt_2
    assert "Total errors in current thread: 1" in prompt_2
    assert "Error Type: SteerableQueueEmptyError" in prompt_2
    assert "First task: deploy application." in prompt_2
    assert "Deployment docs retrieved. Ready for subsequent pipeline step." in prompt_2
    assert "Second task: execute integration tests." in prompt_2

    # VI. Verify daemon response 'no' halted recovery (no session 3 created)
    assert len(agent.sessions) == 2


@pytest.mark.asyncio
async def test_autocontinue_with_simulated_network_timeout_fixture(
    client: httpx.AsyncClient,
    steerable_store: Any,
    resolve_session: Any,
) -> None:
    """When a steerable model emits an APITimeoutError fixture, autocontinue retries."""
    ctx = _make_autocontinue_session(steerable_store, "autocontinue-timeout-agent")
    session = resolve_session(ctx["session_id"])
    agent = ctx["agent"]

    reg = get_steerable_registry()
    inst_agent = reg.get_or_create(agent_instance_id(session.id), role="agent")
    inst_agent.push(SteerableResponse.for_error("timeout"))

    daemon_id = daemon_instance_id(session.id, daemon="autocontinue")
    inst_daemon = reg.get_or_create(daemon_id, role="daemon")
    inst_daemon.push(SteerableResponse(text="yes"))

    await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "Query external API with timeout."},
    )

    runner = get_runner_registry().get_runner(session)
    await _drain(runner)

    # 1. Daemon receives the APITimeoutError payload
    assert inst_daemon.last_invocation is not None
    prompt = inst_daemon.last_invocation[0].content
    assert isinstance(prompt, str)
    assert "Error Type: APITimeoutError" in prompt
    assert "Request timed out while waiting for response." in prompt

    # 2. Root session failed
    assert session.status.value == "FAILED"

    # 3. Child session created via branching
    assert len(agent.sessions) == 2
    child = [s for s in agent.sessions.values() if s.id != session.id][0]
    assert child.provenance is not None
    assert child.provenance.parent_session_id == session.id


@pytest.mark.asyncio
async def test_autocontinue_with_simulated_out_of_cash_quota_fixture(
    client: httpx.AsyncClient,
    steerable_store: Any,
    resolve_session: Any,
) -> None:
    """When a steerable model emits an out-of-cash fixture, autocontinue halts without retry."""
    ctx = _make_autocontinue_session(steerable_store, "autocontinue-quota-agent")
    session = resolve_session(ctx["session_id"])
    agent = ctx["agent"]

    reg = get_steerable_registry()
    inst_agent = reg.get_or_create(agent_instance_id(session.id), role="agent")
    inst_agent.push(SteerableResponse.for_error("out_of_cash"))

    daemon_id = daemon_instance_id(session.id, daemon="autocontinue")
    inst_daemon = reg.get_or_create(daemon_id, role="daemon")
    inst_daemon.push(SteerableResponse(text="no"))

    await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "Generate complex response."},
    )

    runner = get_runner_registry().get_runner(session)
    await _drain(runner)

    # 1. Daemon receives RateLimitError with quota message
    assert inst_daemon.last_invocation is not None
    prompt = inst_daemon.last_invocation[0].content
    assert isinstance(prompt, str)
    assert "Error Type: RateLimitError" in prompt
    assert "You exceeded your current quota" in prompt

    # 2. Root session failed
    assert session.status.value == "FAILED"

    # 3. No child session created because daemon halted retry
    assert len(agent.sessions) == 1


@pytest.mark.asyncio
async def test_autocontinue_with_reasoning_before_timeout_branches_after_reasoning(
    client: httpx.AsyncClient,
    steerable_store: Any,
    resolve_session: Any,
) -> None:
    """Mid-stream reasoning is preserved before the error and used as branch point."""
    ctx = _make_autocontinue_session(steerable_store, "autocontinue-midstream-agent")
    session = resolve_session(ctx["session_id"])
    agent = ctx["agent"]

    reg = get_steerable_registry()
    inst_agent = reg.get_or_create(agent_instance_id(session.id), role="agent")
    inst_agent.push(
        SteerableResponse.for_error(
            "timeout",
            reasoning="Planning database migration steps carefully...",
        )
    )

    daemon_id = daemon_instance_id(session.id, daemon="autocontinue")
    inst_daemon = reg.get_or_create(daemon_id, role="daemon")
    inst_daemon.push(SteerableResponse(text="yes"))

    await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "Perform database migration."},
    )

    runner = get_runner_registry().get_runner(session)
    await _drain(runner)

    # 1. Verify reasoning bubble exists in root thread events
    thread = session.get_open_thread()
    assert thread is not None
    events = thread.events
    assert any("REASONING" in str(getattr(e, "type", "") or "") for e in events)

    # 2. Verify child session was branched after the reasoning bubble
    assert len(agent.sessions) == 2
    child = [s for s in agent.sessions.values() if s.id != session.id][0]
    assert child.provenance is not None
    assert child.provenance.parent_session_id == session.id
    assert child.provenance.item_type == "bot_thinking"
    assert child.provenance.branch_position == "after"


@pytest.mark.asyncio
async def test_autocontinue_matrix_transient_rate_limit_retry(
    client: httpx.AsyncClient,
    steerable_store: Any,
    resolve_session: Any,
) -> None:
    """Transient rate limit (429) triggers autocontinue retry and child session finishes."""
    ctx = _make_autocontinue_session(steerable_store, "matrix-rate-limit-agent")
    session = resolve_session(ctx["session_id"])
    agent = ctx["agent"]

    reg = get_steerable_registry()
    inst_agent = reg.get_or_create(agent_instance_id(session.id), role="agent")
    inst_agent.push(SteerableResponse.for_error("rate_limit"))

    daemon_id = daemon_instance_id(session.id, daemon="autocontinue")
    inst_daemon = reg.get_or_create(daemon_id, role="daemon")
    inst_daemon.push(SteerableResponse(text="yes, retry please"))

    await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "Perform high throughput calculation."},
    )

    runner = get_runner_registry().get_runner(session)
    await _drain(runner)

    # 1. Root session failed and daemon received RateLimitError payload
    assert session.status.value == "FAILED"
    assert inst_daemon.last_invocation is not None
    prompt = inst_daemon.last_invocation[0].content
    assert "Error Type: RateLimitError" in prompt
    assert "Rate limit reached for requests" in prompt

    # 2. Child session was branched and is resuming
    assert len(agent.sessions) == 2
    child = [s for s in agent.sessions.values() if s.id != session.id][0]
    assert child.provenance is not None
    assert child.provenance.parent_session_id == session.id

    # 3. Supply successful response to child session model and drain
    child_agent = reg.get_or_create(agent_instance_id(child.id), role="agent")
    child_agent.push(SteerableResponse(text="Calculation finished successfully after backoff."))

    runner_child = get_runner_registry().get_runner(child)
    await _drain(runner_child)

    # 4. Child session completed turn
    assert child.status.value == "ACTIVE"
    child_thread = child.get_open_thread()
    assert child_thread is not None
    assert child_thread.status.value == "AWAITING_USER"


@pytest.mark.asyncio
async def test_autocontinue_matrix_transient_server_error_retry(
    client: httpx.AsyncClient,
    steerable_store: Any,
    resolve_session: Any,
) -> None:
    """Transient server 500 error triggers autocontinue retry with numeric truthy response."""
    ctx = _make_autocontinue_session(steerable_store, "matrix-500-error-agent")
    session = resolve_session(ctx["session_id"])
    agent = ctx["agent"]

    reg = get_steerable_registry()
    inst_agent = reg.get_or_create(agent_instance_id(session.id), role="agent")
    inst_agent.push(SteerableResponse.for_error("server_error"))

    daemon_id = daemon_instance_id(session.id, daemon="autocontinue")
    inst_daemon = reg.get_or_create(daemon_id, role="daemon")
    inst_daemon.push(SteerableResponse(text="1"))  # Numeric truthy response

    await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "Process backend task."},
    )

    runner = get_runner_registry().get_runner(session)
    await _drain(runner)

    assert session.status.value == "FAILED"
    assert inst_daemon.last_invocation is not None
    prompt = inst_daemon.last_invocation[0].content
    assert "Error Type: InternalServerError" in prompt

    # Child branched
    assert len(agent.sessions) == 2
    child = [s for s in agent.sessions.values() if s.id != session.id][0]
    assert child.provenance is not None
    assert child.provenance.parent_session_id == session.id


@pytest.mark.asyncio
async def test_autocontinue_matrix_permanent_auth_failure_ignore(
    client: httpx.AsyncClient,
    steerable_store: Any,
    resolve_session: Any,
) -> None:
    """Permanent authentication failure (401) is evaluated as no-retry and halts."""
    ctx = _make_autocontinue_session(steerable_store, "matrix-auth-agent")
    session = resolve_session(ctx["session_id"])
    agent = ctx["agent"]

    reg = get_steerable_registry()
    inst_agent = reg.get_or_create(agent_instance_id(session.id), role="agent")
    inst_agent.push(SteerableResponse.for_error("auth_failure"))

    daemon_id = daemon_instance_id(session.id, daemon="autocontinue")
    inst_daemon = reg.get_or_create(daemon_id, role="daemon")
    inst_daemon.push(SteerableResponse(text="no"))

    await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "Execute privileged operation."},
    )

    runner = get_runner_registry().get_runner(session)
    await _drain(runner)

    assert session.status.value == "FAILED"
    assert inst_daemon.last_invocation is not None
    prompt = inst_daemon.last_invocation[0].content
    assert "Error Type: AuthenticationError" in prompt
    assert "Incorrect API key provided" in prompt

    # No child session created
    assert len(agent.sessions) == 1


@pytest.mark.asyncio
async def test_autocontinue_matrix_unexpected_exception_ignore(
    client: httpx.AsyncClient,
    steerable_store: Any,
    resolve_session: Any,
) -> None:
    """Custom unrecoverable exception (e.g. ZeroDivisionError) halts on daemon stop decision."""
    ctx = _make_autocontinue_session(steerable_store, "matrix-zero-div-agent")
    session = resolve_session(ctx["session_id"])
    agent = ctx["agent"]

    reg = get_steerable_registry()
    inst_agent = reg.get_or_create(agent_instance_id(session.id), role="agent")
    inst_agent.push(
        SteerableResponse(
            error=SteerableError(
                error_type="ZeroDivisionError",
                message="division by zero in metric aggregation",
            )
        )
    )

    daemon_id = daemon_instance_id(session.id, daemon="autocontinue")
    inst_daemon = reg.get_or_create(daemon_id, role="daemon")
    inst_daemon.push(SteerableResponse(text="stop"))

    await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "Compute metrics average."},
    )

    runner = get_runner_registry().get_runner(session)
    await _drain(runner)

    assert session.status.value == "FAILED"
    assert inst_daemon.last_invocation is not None
    prompt = inst_daemon.last_invocation[0].content
    assert "Error Type: ZeroDivisionError" in prompt
    assert "division by zero in metric aggregation" in prompt

    # No child session created
    assert len(agent.sessions) == 1


@pytest.mark.asyncio
async def test_autocontinue_matrix_unrecognized_response_defaults_to_halt(
    client: httpx.AsyncClient,
    steerable_store: Any,
    resolve_session: Any,
) -> None:
    """When the daemon produces ambiguous or unrecognized output, it safely defaults to halt."""
    ctx = _make_autocontinue_session(steerable_store, "matrix-gibberish-agent")
    session = resolve_session(ctx["session_id"])
    agent = ctx["agent"]

    reg = get_steerable_registry()
    inst_agent = reg.get_or_create(agent_instance_id(session.id), role="agent")
    inst_agent.push(SteerableResponse.for_error("timeout"))

    daemon_id = daemon_instance_id(session.id, daemon="autocontinue")
    inst_daemon = reg.get_or_create(daemon_id, role="daemon")
    inst_daemon.push(
        SteerableResponse(text="I am not sure whether to proceed or abort, consult human.")
    )

    await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "Wait for slow service."},
    )

    runner = get_runner_registry().get_runner(session)
    await _drain(runner)

    # Defaults to false / no retry
    assert session.status.value == "FAILED"
    assert len(agent.sessions) == 1


@pytest.mark.asyncio
async def test_autocontinue_matrix_daemon_craps_out_with_simulated_error(
    client: httpx.AsyncClient,
    steerable_store: Any,
    resolve_session: Any,
) -> None:
    """When the autocontinue daemon itself encounters a model error, runner handles it safely."""
    ctx = _make_autocontinue_session(steerable_store, "matrix-daemon-crapout-agent")
    session = resolve_session(ctx["session_id"])
    agent = ctx["agent"]

    reg = get_steerable_registry()
    inst_agent = reg.get_or_create(agent_instance_id(session.id), role="agent")
    inst_agent.push(SteerableResponse.for_error("timeout"))

    # Autocontinue daemon's own steerable model emits an InternalServerError
    daemon_id = daemon_instance_id(session.id, daemon="autocontinue")
    inst_daemon = reg.get_or_create(daemon_id, role="daemon")
    inst_daemon.push(SteerableResponse.for_error("server_error"))

    await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "Trigger failure where daemon also fails."},
    )

    runner = get_runner_registry().get_runner(session)
    # Drain must finish without throwing unhandled exceptions
    await _drain(runner)

    # Root session failed cleanly
    assert session.status.value == "FAILED"
    # No branching occurred
    assert len(agent.sessions) == 1


@pytest.mark.asyncio
async def test_autocontinue_matrix_daemon_craps_out_empty_queue(
    client: httpx.AsyncClient,
    steerable_store: Any,
    resolve_session: Any,
) -> None:
    """When the daemon queue is empty under ERROR strategy, session remains failed."""
    ctx = _make_autocontinue_session(steerable_store, "matrix-daemon-empty-agent")
    session = resolve_session(ctx["session_id"])
    agent = ctx["agent"]

    reg = get_steerable_registry()
    inst_agent = reg.get_or_create(agent_instance_id(session.id), role="agent")
    inst_agent.push(SteerableResponse.for_error("timeout"))

    # Autocontinue daemon's queue is configured to fail on empty queue
    daemon_id = daemon_instance_id(session.id, daemon="autocontinue")
    inst_daemon = reg.get_or_create(daemon_id, role="daemon")
    inst_daemon.strategy = SteerableEmptyQueueStrategy.ERROR

    await client.post(
        f"/api/v-alpha/agent/{ctx['agent_id']}/session/{ctx['session_id']}/input",
        json={"message": "Trigger failure where daemon has empty queue."},
    )

    runner = get_runner_registry().get_runner(session)
    await _drain(runner)

    # Root session failed cleanly without unhandled server crash
    assert session.status.value == "FAILED"
    assert len(agent.sessions) == 1
