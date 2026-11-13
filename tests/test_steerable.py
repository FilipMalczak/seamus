"""Tests for the steerable (scripted) model provider and its Inspector API."""

import asyncio
from typing import Any

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import HumanMessage

from seamus.config.models import (
    AgentConfig,
    InferenceConfig,
    InferenceFormat,
    SteerableConfig,
    SteerableEmptyQueueStrategy,
)
from seamus.config.template import ConfigTemplateStore, reset_config_template_store
from seamus.harness.steerable import (
    SteerableChatModel,
    SteerableInstance,
    SteerableQueueEmptyError,
    SteerableResponse,
    SteerableToolCall,
    agent_instance_id,
    build_steerable_model,
    daemon_instance_id,
    get_steerable_registry,
    reset_steerable_registry,
)
from seamus.harness.store import HarnessStore, reset_harness_store
from seamus.server.app import create_app


@pytest.fixture(autouse=True)
def reset_globals() -> None:
    """Ensure clean isolation between tests."""
    template = AgentConfig(
        inference=InferenceConfig(
            format=InferenceFormat.STEERABLE,
            base_url="https://openrouter.ai/api/v1",
            steerable=SteerableConfig(),
        ),
        model_name="steerable-model",
    )
    reset_config_template_store(ConfigTemplateStore(initial_template=template))
    reset_harness_store(HarnessStore())
    reset_steerable_registry()


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    return TestClient(app)


def _instance(instance_id: str = "test:instance", role: str = "agent") -> Any:
    registry = get_steerable_registry()
    return registry.get_or_create(instance_id, role)


def test_steerable_config_requires_no_api_key() -> None:
    """Steerable inference is complete without credentials."""
    config = InferenceConfig(format=InferenceFormat.STEERABLE)
    assert config.requires_api_key() is False
    assert config.is_complete() is True

    agent_config = AgentConfig(inference=config, model_name="steerable-model")
    agent_config.validate_complete()


def test_default_empty_queue_strategy_is_wait() -> None:
    """The steerable provider waits for a scripted response by default."""
    instance = SteerableInstance(instance_id="x", role="agent")
    assert SteerableConfig().empty_queue_strategy is SteerableEmptyQueueStrategy.WAIT
    assert instance.strategy is SteerableEmptyQueueStrategy.WAIT


def test_queue_consumed_in_order() -> None:
    """Queued responses are returned in FIFO order."""
    instance = _instance()
    instance.push(SteerableResponse(text="first"))
    instance.push(SteerableResponse(text="second"))

    model = SteerableChatModel(instance_id=instance.instance_id)
    assert model.invoke([HumanMessage(content="go")]).content == "first"
    assert model.invoke([HumanMessage(content="go")]).content == "second"


def test_response_carries_text_reasoning_and_tool_calls() -> None:
    """A scripted response surfaces text, reasoning, and tool calls."""
    instance = _instance()
    instance.push(
        SteerableResponse(
            text="Listing files",
            reasoning="The user wants a listing",
            tool_calls=[SteerableToolCall(name="ls", args={"path": "/workspace"})],
        )
    )

    model = SteerableChatModel(instance_id=instance.instance_id)
    message = model.invoke([HumanMessage(content="go")])

    assert message.content == "Listing files"
    assert message.additional_kwargs["reasoning_content"] == "The user wants a listing"
    assert len(message.tool_calls) == 1
    call = message.tool_calls[0]
    assert call["name"] == "ls"
    assert call["args"] == {"path": "/workspace"}


def test_response_carries_multiple_tool_calls() -> None:
    """A single scripted response may request several tool calls."""
    instance = _instance()
    instance.push(
        SteerableResponse(
            text="Running two tools",
            tool_calls=[
                SteerableToolCall(name="ls", args={"path": "/workspace"}),
                SteerableToolCall(name="read_file", args={"path": "/workspace/a.txt"}),
            ],
        )
    )

    model = SteerableChatModel(instance_id=instance.instance_id)
    message = model.invoke([HumanMessage(content="go")])

    assert len(message.tool_calls) == 2
    assert [call["name"] for call in message.tool_calls] == ["ls", "read_file"]
    assert message.tool_calls[0]["args"] == {"path": "/workspace"}
    assert message.tool_calls[1]["args"] == {"path": "/workspace/a.txt"}


def test_stream_emits_reasoning_text_and_tool_call_chunks() -> None:
    """Streaming emits distinct reasoning, text, and tool-call chunks."""
    instance = _instance()
    instance.push(
        SteerableResponse(
            text="Working",
            reasoning="Thinking",
            tool_calls=[SteerableToolCall(name="ls", args={"path": "/"})],
        )
    )

    model = SteerableChatModel(instance_id=instance.instance_id)
    chunks = list(model.stream([HumanMessage(content="go")]))

    reasoning_chunks = [c for c in chunks if c.additional_kwargs.get("reasoning_content")]
    text_chunks = [c for c in chunks if c.content]
    tool_chunks = [c for c in chunks if c.tool_call_chunks]

    assert len(reasoning_chunks) == 1
    assert reasoning_chunks[0].additional_kwargs["reasoning_content"] == "Thinking"
    assert len(text_chunks) == 1
    assert text_chunks[0].content == "Working"
    # Tool calls stream as a name chunk followed by an arguments chunk.
    assert len(tool_chunks) == 2
    assert tool_chunks[0].tool_call_chunks[0]["name"] == "ls"
    assert tool_chunks[1].tool_call_chunks[0]["args"] == '{"path": "/"}'


@pytest.mark.asyncio
async def test_empty_queue_error_strategy() -> None:
    """The error strategy raises when the queue is empty."""
    instance = _instance()
    instance.strategy = SteerableEmptyQueueStrategy.ERROR

    model = SteerableChatModel(instance_id=instance.instance_id)
    with pytest.raises(SteerableQueueEmptyError):
        await model.ainvoke([HumanMessage(content="go")])


@pytest.mark.asyncio
async def test_empty_queue_repeat_strategy() -> None:
    """The repeat strategy returns the configured default response."""
    instance = _instance()
    instance.strategy = SteerableEmptyQueueStrategy.REPEAT
    instance.default_response = "nothing scripted"

    model = SteerableChatModel(instance_id=instance.instance_id)
    message = await model.ainvoke([HumanMessage(content="go")])
    assert message.content == "nothing scripted"


@pytest.mark.asyncio
async def test_empty_queue_wait_strategy_blocks_until_pushed() -> None:
    """The wait strategy blocks until a response is pushed from elsewhere."""
    instance = _instance()
    instance.strategy = SteerableEmptyQueueStrategy.WAIT
    instance.wait_timeout = 5.0

    model = SteerableChatModel(instance_id=instance.instance_id)

    async def push_later() -> None:
        await asyncio.sleep(0.1)
        instance.push(SteerableResponse(text="pushed later"))

    task = asyncio.create_task(push_later())
    message = await model.ainvoke([HumanMessage(content="go")])
    await task

    assert message.content == "pushed later"


@pytest.mark.asyncio
async def test_empty_queue_wait_strategy_times_out() -> None:
    """The wait strategy raises after its timeout elapses."""
    instance = _instance()
    instance.strategy = SteerableEmptyQueueStrategy.WAIT
    instance.wait_timeout = 0.2

    model = SteerableChatModel(instance_id=instance.instance_id)
    with pytest.raises(SteerableQueueEmptyError):
        await model.ainvoke([HumanMessage(content="go")])


def test_registry_isolates_agent_and_daemon_instances() -> None:
    """Agent and daemon instances keep separate queues."""
    registry = get_steerable_registry()
    agent = registry.get_or_create(agent_instance_id("s1"), "agent")
    daemon = registry.get_or_create(daemon_instance_id("s1"), "daemon")

    agent.push(SteerableResponse(text="agent response"))

    assert agent.pending_count == 1
    assert daemon.pending_count == 0
    assert [i.instance_id for i in registry.list_for_session("s1")] == [
        agent_instance_id("s1"),
        daemon_instance_id("s1"),
    ]
    assert registry.list_for_session("other") == []


def test_registry_get_or_create_is_idempotent() -> None:
    """Registering the same id twice keeps the original instance."""
    registry = get_steerable_registry()
    first = registry.get_or_create("s1:agent", "agent")
    first.push(SteerableResponse(text="kept"))
    second = registry.get_or_create("s1:agent", "agent")

    assert first is second
    assert second.pending_count == 1


def test_bind_tools_records_known_tools() -> None:
    """Binding tools records their names on the instance."""
    from langchain_core.tools import StructuredTool

    tool = StructuredTool.from_function(
        name="my_tool",
        description="does something",
        func=lambda: "ok",
    )
    model = build_steerable_model("bind:instance", "agent")
    model.bind_tools([tool])

    assert model.instance.known_tools == ["my_tool"]


def test_instance_ids_are_session_scoped() -> None:
    """Instance ids are stable and session scoped."""
    assert agent_instance_id("abc") == "session:abc:agent"
    assert daemon_instance_id("abc") == "session:abc:daemon:naming"
    assert daemon_instance_id("abc", "summary") == "session:abc:daemon:summary"


@pytest.mark.asyncio
async def test_steerable_model_drives_a_real_agent_loop() -> None:
    """A steerable model drives a DeepAgent: tool call, tool result, then final text."""
    from deepagents import create_deep_agent
    from deepagents.backends import StateBackend

    model = build_steerable_model("e2e:agent", "agent")
    model.instance.push(
        SteerableResponse(
            reasoning="I should list the workspace",
            tool_calls=[SteerableToolCall(name="ls", args={"path": "/workspace"})],
        )
    )
    model.instance.push(SteerableResponse(text="The workspace is empty."))

    agent = create_deep_agent(model=model, backend=StateBackend(), tools=[])
    result = await agent.ainvoke({"messages": [{"role": "user", "content": "list files"}]})

    messages = result["messages"]
    assert [type(m).__name__ for m in messages] == [
        "HumanMessage",
        "AIMessage",
        "ToolMessage",
        "AIMessage",
    ]

    tool_call = messages[1].tool_calls[0]
    assert tool_call["name"] == "ls"
    assert tool_call["args"] == {"path": "/workspace"}
    assert messages[1].additional_kwargs["reasoning_content"] == "I should list the workspace"
    assert messages[3].content == "The workspace is empty."


@pytest.mark.asyncio
async def test_steerable_daemon_invocation() -> None:
    """A daemon can be driven by a steerable provider."""
    from seamus.harness.daemons.engine import invoke_daemon

    provider = InferenceConfig(
        format=InferenceFormat.STEERABLE,
        steerable=SteerableConfig(empty_queue_strategy=SteerableEmptyQueueStrategy.ERROR),
    )
    instance = get_steerable_registry().get_or_create(daemon_instance_id("s1"), "daemon")
    instance.push(SteerableResponse(text="scripted-thread-slug"))

    slug = await invoke_daemon(
        provider=provider,
        model="steerable-model",
        instructions="Name the thread.",
        input_payload="some conversation",
        steerable_instance_id=daemon_instance_id("s1"),
    )

    assert slug == "scripted-thread-slug"


def _create_session(client: TestClient) -> tuple[str, str]:
    create_res = client.post("/api/v-alpha/agents", json={"name": "steerable-agent"})
    assert create_res.status_code == 201
    agent_id = create_res.json()["id"]
    agent_detail = client.get(f"/api/v-alpha/agent/{agent_id}").json()
    session_id = agent_detail["sessions"][0]["id"]
    return agent_id, session_id


def test_steerable_api_roundtrip(client: TestClient) -> None:
    """The steerable API lists, appends, replaces, and clears queued responses."""
    agent_id, session_id = _create_session(client)
    base = f"/api/v-alpha/agent/{agent_id}/session/{session_id}/steerable"

    instance_id = agent_instance_id(session_id)
    get_steerable_registry().get_or_create(instance_id, "agent")

    # 1. List
    list_res = client.get(base)
    assert list_res.status_code == 200
    listed = {entry["instance_id"]: entry for entry in list_res.json()}
    assert instance_id in listed
    assert listed[instance_id]["role"] == "agent"
    assert listed[instance_id]["strategy"] == "wait"
    assert listed[instance_id]["pending_count"] == 0

    # 2. Append
    append_res = client.post(
        f"{base}/{instance_id}/responses",
        json={"responses": [{"text": "hello"}, {"text": "world"}]},
    )
    assert append_res.status_code == 200
    appended = append_res.json()
    assert appended["pending_count"] == 2
    assert appended["responses"][0]["text"] == "hello"

    # 3. Replace
    replace_res = client.put(
        f"{base}/{instance_id}/responses",
        json={"responses": [{"text": "only one", "reasoning": "because"}]},
    )
    assert replace_res.status_code == 200
    replaced = replace_res.json()
    assert replaced["pending_count"] == 1
    assert replaced["responses"][0]["text"] == "only one"
    assert replaced["responses"][0]["reasoning"] == "because"

    # 3b. Append a response carrying several tool calls at once.
    multi_res = client.post(
        f"{base}/{instance_id}/responses",
        json={
            "responses": [
                {
                    "text": "two tools",
                    "tool_calls": [
                        {"name": "ls", "args": {"path": "/"}},
                        {"name": "read_file", "args": {"path": "/a.txt"}},
                    ],
                }
            ]
        },
    )
    assert multi_res.status_code == 200
    multi_data = multi_res.json()
    assert multi_data["pending_count"] == 2
    assert len(multi_data["responses"][1]["tool_calls"]) == 2
    assert multi_data["responses"][1]["tool_calls"][1]["name"] == "read_file"

    # 4. Strategy
    strategy_res = client.patch(
        f"{base}/{instance_id}/strategy",
        json={"strategy": "repeat", "default_response": "fallback"},
    )
    assert strategy_res.status_code == 200
    strategy_data = strategy_res.json()
    assert strategy_data["strategy"] == "repeat"
    assert strategy_data["default_response"] == "fallback"

    # 5. Clear (expressed as a replacement with an empty list; the API has no
    # DELETE routes per INV-007)
    clear_res = client.put(f"{base}/{instance_id}/responses", json={"responses": []})
    assert clear_res.status_code == 200
    assert clear_res.json()["pending_count"] == 0


def test_steerable_api_unknown_instance_returns_404(client: TestClient) -> None:
    """Addressing an unknown steerable instance returns 404."""
    agent_id, session_id = _create_session(client)
    res = client.post(
        f"/api/v-alpha/agent/{agent_id}/session/{session_id}/steerable/nope/responses",
        json={"responses": [{"text": "hello"}]},
    )
    assert res.status_code == 404


def test_inspect_report_lists_steerable_instances(client: TestClient) -> None:
    """The inspector report exposes the session's steerable instances."""
    agent_id, session_id = _create_session(client)
    instance_id = agent_instance_id(session_id)
    instance = get_steerable_registry().get_or_create(instance_id, "agent")
    instance.push(SteerableResponse(text="queued"))

    res = client.get(f"/api/v-alpha/agent/{agent_id}/session/{session_id}/inspect")
    assert res.status_code == 200
    data = res.json()
    assert "steerable_models" in data

    # The agent model and the naming daemon get separate inspector entries.
    entries = {entry["instance_id"]: entry for entry in data["steerable_models"]}
    assert instance_id in entries
    assert daemon_instance_id(session_id) in entries

    agent_entry = entries[instance_id]
    assert agent_entry["role"] == "agent"
    assert agent_entry["pending_count"] == 1
    assert agent_entry["responses"][0]["text"] == "queued"

    daemon_entry = entries[daemon_instance_id(session_id)]
    assert daemon_entry["role"] == "daemon"
    assert daemon_entry["pending_count"] == 0
