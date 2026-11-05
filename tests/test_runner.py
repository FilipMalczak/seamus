"""Unit tests for SessionAgentRunner, EventBroadcaster, and status lifecycle."""

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

import pytest
from ag_ui.core.events import (
    EventType,
    ReasoningEndEvent,
    ReasoningMessageContentEvent,
    ReasoningMessageEndEvent,
    ReasoningMessageStartEvent,
    ReasoningStartEvent,
    RunFinishedEvent,
    RunStartedEvent,
    TextMessageChunkEvent,
    ToolCallArgsEvent,
    ToolCallEndEvent,
    ToolCallResultEvent,
    ToolCallStartEvent,
)
from ag_ui.core.types import RunAgentInput, TextInputContent, UserMessage
from ag_ui_langgraph.utils import resolve_reasoning_content
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from pydantic import SecretStr

from seamus.config.models import (
    AgentConfig,
    InferenceConfig,
    SkillsImplementation,
    TodoImplementation,
)
from seamus.domain.entities import Agent, AgentStatus
from seamus.harness.runner import (
    EventBroadcaster,
    ReasoningChatOpenAI,
    RunnerRegistry,
    SeamusLangGraphAgent,
    SessionAgentRunner,
    SessionBusyError,
)


class FakeAgent:
    """Mock agent simulating LangGraphAgent for deterministic offline execution."""

    def __init__(self, delay: float = 0.01) -> None:
        self.delay = delay

    def clone(self) -> "FakeAgent":
        return self

    async def run(self, input_data: RunAgentInput) -> AsyncGenerator[Any, None]:
        yield RunStartedEvent(
            type=EventType.RUN_STARTED,
            thread_id=input_data.thread_id,
            run_id=input_data.run_id,
        )
        await asyncio.sleep(self.delay)
        yield ToolCallStartEvent(
            type=EventType.TOOL_CALL_START,
            tool_call_id="call-1",
            tool_call_name="search",
        )
        await asyncio.sleep(self.delay)
        yield TextMessageChunkEvent(
            type=EventType.TEXT_MESSAGE_CHUNK,
            message_id="msg-1",
            delta="Hello world",
        )
        await asyncio.sleep(self.delay)
        yield RunFinishedEvent(
            type=EventType.RUN_FINISHED,
            thread_id=input_data.thread_id,
            run_id=input_data.run_id,
        )


@pytest.mark.asyncio
async def test_event_broadcaster() -> None:
    broadcaster = EventBroadcaster()
    queue = broadcaster.subscribe()

    await broadcaster.broadcast({"msg": "hello"})
    received = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert received == {"msg": "hello"}

    broadcaster.unsubscribe(queue)
    assert len(broadcaster._subscribers) == 0


@pytest.mark.asyncio
async def test_session_agent_runner_execution_and_status() -> None:
    config = AgentConfig(
        inference=InferenceConfig(api_key="mock-key"),
        model_name="mock-model",
        todo_implementation=TodoImplementation.DEEPAGENTS,
    )
    agent = Agent(config=config, name="agent")
    session = agent.create_session(name="session")

    fake_agent = FakeAgent(delay=0.02)
    runner = SessionAgentRunner(session=session, agent=fake_agent)

    assert runner.is_awaiting_user() is True

    # Dispatch input
    await runner.dispatch_user_input("Hello, agent")

    # While active, another dispatch should raise SessionBusyError
    with pytest.raises(SessionBusyError):
        await runner.dispatch_user_input("Wait, I have another question!")

    # Wait for background task to finish
    if runner._active_task is not None:
        await runner._active_task

    open_thread = session.get_open_thread()
    assert open_thread.status == AgentStatus.AWAITING_USER
    # 3 user message events (START, CONTENT, END) + 4 agent execution events
    assert len(open_thread.events) == 7
    assert open_thread.events[0].type == EventType.TEXT_MESSAGE_START
    assert getattr(open_thread.events[0], "role", None) == "user"
    assert open_thread.events[1].type == EventType.TEXT_MESSAGE_CONTENT
    assert getattr(open_thread.events[1], "delta", None) == "Hello, agent"
    assert open_thread.events[2].type == EventType.TEXT_MESSAGE_END
    assert runner.is_awaiting_user() is True


def test_reasoning_chat_openai_extracts_reasoning_fields() -> None:
    llm = ReasoningChatOpenAI(
        model="openai/gpt-oss-20b",
        api_key=SecretStr("mock-key"),
        base_url="https://openrouter.ai/api/v1",
    )

    # 1. OpenRouter standard 'reasoning' field in streaming delta
    chunk_openrouter = {
        "id": "chatcmpl-1",
        "choices": [
            {
                "index": 0,
                "delta": {"role": "assistant", "content": "", "reasoning": "Analyzing user query"},
            }
        ],
    }
    gen_chunk_1 = llm._convert_chunk_to_generation_chunk(chunk_openrouter, AIMessageChunk, None)
    assert gen_chunk_1 is not None
    assert gen_chunk_1.message.additional_kwargs.get("reasoning_content") == "Analyzing user query"
    resolved_1 = resolve_reasoning_content(gen_chunk_1.message)
    assert resolved_1 is not None
    assert resolved_1["text"] == "Analyzing user query"

    # 2. DeepSeek/vLLM 'reasoning_content' field in streaming delta
    chunk_deepseek = {
        "id": "chatcmpl-2",
        "choices": [
            {
                "index": 0,
                "delta": {"role": "assistant", "content": "", "reasoning_content": "Step by step"},
            }
        ],
    }
    gen_chunk_2 = llm._convert_chunk_to_generation_chunk(chunk_deepseek, AIMessageChunk, None)
    assert gen_chunk_2 is not None
    assert gen_chunk_2.message.additional_kwargs.get("reasoning_content") == "Step by step"

    # 3. 'reasoning_details' array fallback in streaming delta
    chunk_details = {
        "id": "chatcmpl-3",
        "choices": [
            {
                "index": 0,
                "delta": {
                    "role": "assistant",
                    "content": "",
                    "reasoning_details": [
                        {"type": "reasoning.text", "text": "Part A "},
                        {"type": "reasoning.summary", "summary": "Part B"},
                    ],
                },
            }
        ],
    }
    gen_chunk_3 = llm._convert_chunk_to_generation_chunk(chunk_details, AIMessageChunk, None)
    assert gen_chunk_3 is not None
    assert gen_chunk_3.message.additional_kwargs.get("reasoning_content") == "Part A Part B"

    # 4. Non-streaming response extraction
    response_dict = {
        "id": "chatcmpl-4",
        "model": "openai/gpt-oss-20b",
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {
                    "role": "assistant",
                    "content": "Final answer",
                    "reasoning": "Thought before answering",
                },
            }
        ],
    }
    chat_result = llm._create_chat_result(response_dict)
    assert len(chat_result.generations) == 1
    msg = chat_result.generations[0].message
    assert msg.content == "Final answer"
    assert msg.additional_kwargs.get("reasoning_content") == "Thought before answering"


@pytest.mark.asyncio
async def test_runner_reasoning_events_and_replay() -> None:
    class ReasoningFakeAgent:
        def clone(self) -> "ReasoningFakeAgent":
            return self

        async def run(self, input_data: RunAgentInput) -> AsyncGenerator[Any, None]:
            yield RunStartedEvent(
                type=EventType.RUN_STARTED,
                thread_id=input_data.thread_id,
                run_id=input_data.run_id,
            )
            yield ReasoningStartEvent(
                type=EventType.REASONING_START,
                message_id="reas-1",
            )
            yield ReasoningMessageStartEvent(
                type=EventType.REASONING_MESSAGE_START,
                message_id="reas-1",
                role="reasoning",
            )
            yield ReasoningMessageContentEvent(
                type=EventType.REASONING_MESSAGE_CONTENT,
                message_id="reas-1",
                delta="Thinking deeply...",
            )
            yield ReasoningMessageEndEvent(
                type=EventType.REASONING_MESSAGE_END,
                message_id="reas-1",
            )
            yield ReasoningEndEvent(
                type=EventType.REASONING_END,
                message_id="reas-1",
            )
            yield TextMessageChunkEvent(
                type=EventType.TEXT_MESSAGE_CHUNK,
                message_id="msg-1",
                delta="Final answer",
            )
            yield RunFinishedEvent(
                type=EventType.RUN_FINISHED,
                thread_id=input_data.thread_id,
                run_id=input_data.run_id,
            )

    config = AgentConfig(
        inference=InferenceConfig(api_key="mock-key"),
        model_name="mock-model",
        todo_implementation=TodoImplementation.DEEPAGENTS,
    )
    agent = Agent(config=config, name="agent")
    session = agent.create_session(name="session")
    runner = SessionAgentRunner(session=session, agent=ReasoningFakeAgent())

    await runner.dispatch_user_input("Explain this")
    if runner._active_task is not None:
        await runner._active_task

    open_thread = session.get_open_thread()
    assert open_thread.status == AgentStatus.AWAITING_USER

    frames = [frame async for frame in runner.stream_thread_events(open_thread, follow=False)]
    joined = "".join(frames)
    assert "REASONING_START" in joined
    assert "REASONING_MESSAGE_CONTENT" in joined
    assert "Thinking deeply..." in joined
    assert "REASONING_END" in joined


def test_seamus_langgraph_agent_preserves_checkpoint_messages() -> None:
    agent = SeamusLangGraphAgent.__new__(SeamusLangGraphAgent)
    u1 = HumanMessage(id="u1", content="hey there")
    a1 = AIMessage(id="a1", content="Hey! How can I help?")
    u2 = HumanMessage(id="u2", content="what can you help me with>")

    state = {"messages": [u1, a1], "tools": []}
    input_data = RunAgentInput(
        thread_id="t1",
        run_id="r2",
        messages=[
            UserMessage(
                id="u2",
                role="user",
                content=[TextInputContent(text="what can you help me with>")],
            )
        ],
    )

    merged = agent.langgraph_default_merge_state(state, [u2], input_data)
    merged_msgs = merged["messages"]
    assert [m.id for m in merged_msgs] == ["u1", "a1", "u2"]


def test_tool_call_lifecycle_status_transitions() -> None:
    config = AgentConfig(
        inference=InferenceConfig(api_key="mock-key"),
        model_name="mock-model",
        todo_implementation=TodoImplementation.DEEPAGENTS,
    )
    agent = Agent(config=config, name="agent")
    session = agent.create_session(name="session")
    runner = SessionAgentRunner(session=session, agent=FakeAgent())
    thread = session.get_open_thread()

    runner._update_status_from_event(
        thread,
        RunStartedEvent(type=EventType.RUN_STARTED, thread_id="t", run_id="r"),
    )
    assert session.get_open_thread().status == AgentStatus.AWAITING_LLM

    runner._update_status_from_event(
        thread,
        ToolCallStartEvent(
            type=EventType.TOOL_CALL_START, tool_call_id="call-1", tool_call_name="execute"
        ),
    )
    assert session.get_open_thread().status == AgentStatus.EXECUTING_TOOL

    runner._update_status_from_event(
        thread,
        ToolCallArgsEvent(
            type=EventType.TOOL_CALL_ARGS, tool_call_id="call-1", delta='{"cmd": "ls"}'
        ),
    )
    assert session.get_open_thread().status == AgentStatus.EXECUTING_TOOL

    runner._update_status_from_event(
        thread, ToolCallEndEvent(type=EventType.TOOL_CALL_END, tool_call_id="call-1")
    )
    assert session.get_open_thread().status == AgentStatus.EXECUTING_TOOL

    runner._update_status_from_event(
        thread,
        ToolCallResultEvent(
            type=EventType.TOOL_CALL_RESULT,
            tool_call_id="call-1",
            message_id="m1",
            content="file.txt",
        ),
    )
    assert session.get_open_thread().status == AgentStatus.AWAITING_LLM

    runner._update_status_from_event(
        thread,
        RunFinishedEvent(type=EventType.RUN_FINISHED, thread_id="t", run_id="r"),
    )
    assert session.get_open_thread().status == AgentStatus.AWAITING_USER


def test_session_agent_runner_includes_todo_middleware(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that _build_deep_agent passes TodoListMiddleware in correct order."""
    from unittest.mock import MagicMock

    from langchain.agents.middleware import TodoListMiddleware

    from seamus.harness.prompt import DynamicSystemPromptMiddleware
    from seamus.persistence import GitWorkspaceManager

    mock_mgr = MagicMock(spec=GitWorkspaceManager)
    monkeypatch.setattr("seamus.harness.runner.get_workspace_manager", lambda: mock_mgr)

    config = AgentConfig(
        inference=InferenceConfig(api_key="mock-key"),
        model_name="mock-model",
        todo_implementation=TodoImplementation.DEEPAGENTS,
    )
    agent = Agent(config=config, name="agent")
    session = agent.create_session(name="session")

    captured_kwargs: dict[str, Any] = {}

    def mock_create_deep_agent(**kwargs: Any) -> Any:
        captured_kwargs.update(kwargs)
        mock_graph = MagicMock()
        mock_graph.nodes = {}
        return mock_graph

    monkeypatch.setattr("seamus.harness.runner.create_deep_agent", mock_create_deep_agent)

    runner = SessionAgentRunner(session=session, agent_entity=agent)
    assert runner is not None
    middleware = captured_kwargs.get("middleware", [])

    assert any(isinstance(m, DynamicSystemPromptMiddleware) for m in middleware)
    assert any(isinstance(m, TodoListMiddleware) for m in middleware)
    dynamic_idx = next(
        i for i, m in enumerate(middleware) if isinstance(m, DynamicSystemPromptMiddleware)
    )
    todo_idx = next(i for i, m in enumerate(middleware) if isinstance(m, TodoListMiddleware))
    assert dynamic_idx < todo_idx


def test_seamus_todo_middleware_resilient_inputs() -> None:
    """Verify that SeamusTodoListMiddleware normalizes varied LLM key names and statuses."""
    from seamus.harness.runner import ResilientWriteTodosInput, SeamusTodoListMiddleware

    mw = SeamusTodoListMiddleware()
    assert len(mw.tools) == 1
    tool = mw.tools[0]
    assert tool.name == "write_todos"

    # 1. Standard format
    std = ResilientWriteTodosInput.model_validate(
        {"todos": [{"content": "Clean codebase", "status": "in_progress"}]}
    )
    assert std.todos[0].content == "Clean codebase"
    assert std.todos[0].status == "in_progress"

    # 2. task + state variations (as observed in gpt-oss-20b runs)
    variant1 = ResilientWriteTodosInput.model_validate(
        {"todos": [{"task": "foo", "state": "in_progress"}, {"task": "bar", "state": "pending"}]}
    )
    assert variant1.todos[0].content == "foo"
    assert variant1.todos[0].status == "in_progress"
    assert variant1.todos[1].content == "bar"
    assert variant1.todos[1].status == "pending"

    # 3. name + status variations
    variant2 = ResilientWriteTodosInput.model_validate(
        {"todos": [{"name": "foo task", "status": "in_progress"}]}
    )
    assert variant2.todos[0].content == "foo task"
    assert variant2.todos[0].status == "in_progress"

    # 4. tasks alias + title + done status
    variant3 = ResilientWriteTodosInput.model_validate(
        {"tasks": [{"title": "Deploy system", "progress": "done"}]}
    )
    assert variant3.todos[0].content == "Deploy system"
    assert variant3.todos[0].status == "completed"

    # 5. Tool invocation in LangGraph ToolNode returns Command with matching tool_call_id
    from langchain_core.messages import AIMessage, HumanMessage
    from langgraph.graph import MessagesState, StateGraph
    from langgraph.prebuilt import ToolNode

    builder = StateGraph(MessagesState)
    builder.add_node("tools", ToolNode([tool]))
    builder.set_entry_point("tools")
    graph = builder.compile()

    ai_msg = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "write_todos",
                "args": {
                    "todos": [
                        {"task": "run tests", "state": "active"},
                        {"name": "commit", "state": "todo"},
                    ]
                },
                "id": "call_TEST_123",
            }
        ],
    )
    res = graph.invoke({"messages": [HumanMessage(content="hi"), ai_msg]})
    tool_msg = res["messages"][-1]
    assert tool_msg.tool_call_id == "call_TEST_123"
    assert "run tests" in tool_msg.content


@pytest.mark.asyncio
async def test_seamus_todo_middleware_async_invocation() -> None:
    """Verify that SeamusTodoListMiddleware tool can be invoked asynchronously in LangGraph."""
    from langchain_core.messages import AIMessage, HumanMessage
    from langgraph.graph import MessagesState, StateGraph
    from langgraph.prebuilt import ToolNode

    from seamus.harness.runner import SeamusTodoListMiddleware

    mw = SeamusTodoListMiddleware()
    tool = mw.tools[0]

    builder = StateGraph(MessagesState)
    builder.add_node("tools", ToolNode([tool]))
    builder.set_entry_point("tools")
    graph = builder.compile()

    ai_msg = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "write_todos",
                "args": {"todos": [{"task": "async test", "state": "completed"}]},
                "id": "call_ASYNC_123",
            }
        ],
    )
    res = await graph.ainvoke({"messages": [HumanMessage(content="hi"), ai_msg]})
    tool_msg = res["messages"][-1]
    assert tool_msg.tool_call_id == "call_ASYNC_123"
    assert "async test" in tool_msg.content


def test_session_agent_runner_todo_implementation_toggle() -> None:
    """Verify that runner graph includes or omits write_todos according to todo_implementation."""
    config_none = AgentConfig(
        inference=InferenceConfig(api_key="mock-key"),
        model_name="mock-model",
        todo_implementation=TodoImplementation.NONE,
    )
    agent = Agent(config=config_none, name="test-agent")
    session = agent.create_session(name="test-session")

    runner = SessionAgentRunner(session=session)
    graph = runner.agent.graph
    tools_node = graph.nodes.get("tools")
    bound = getattr(tools_node, "bound", None)
    tools_dict = (
        getattr(bound, "tools_by_name", None) or getattr(bound, "_tools_by_name", None) or {}
    )
    assert "write_todos" not in tools_dict

    # Reload with deepagents
    session.config.todo_implementation = TodoImplementation.DEEPAGENTS
    runner.reload_config()
    graph_reloaded = runner.agent.graph
    tools_node_reloaded = graph_reloaded.nodes.get("tools")
    bound_reloaded = getattr(tools_node_reloaded, "bound", None)
    tools_dict_reloaded = (
        getattr(bound_reloaded, "tools_by_name", None)
        or getattr(bound_reloaded, "_tools_by_name", None)
        or {}
    )
    assert "write_todos" in tools_dict_reloaded


def test_runner_registry_reload_session_runner() -> None:
    """Verify RunnerRegistry.reload_session_runner reconfigures active cached runner."""
    registry = RunnerRegistry()
    config = AgentConfig(
        inference=InferenceConfig(api_key="mock-key"),
        model_name="mock-model",
        todo_implementation=TodoImplementation.NONE,
    )
    agent = Agent(config=config, name="reg-agent")
    session = agent.create_session(name="reg-session")

    runner = registry.get_runner(session, agent)
    bound = getattr(runner.agent.graph.nodes.get("tools"), "bound", None)
    assert bound is not None
    tools_dict = bound.tools_by_name
    assert "write_todos" not in tools_dict

    # Update session config and call reload_session_runner
    session.config.todo_implementation = TodoImplementation.DEEPAGENTS
    registry.reload_session_runner(session)

    bound_updated = getattr(runner.agent.graph.nodes.get("tools"), "bound", None)
    assert bound_updated is not None
    tools_dict_updated = bound_updated.tools_by_name
    assert "write_todos" in tools_dict_updated


def test_session_agent_runner_skills_implementation_toggle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify _build_deep_agent passes skills only when skills_implementation is deepagents."""
    from unittest.mock import MagicMock

    captured_kwargs: list[dict[str, Any]] = []

    def mock_create_deep_agent(**kwargs: Any) -> Any:
        captured_kwargs.append(dict(kwargs))
        mock_graph = MagicMock()
        mock_graph.nodes = {}
        return mock_graph

    monkeypatch.setattr("seamus.harness.runner.create_deep_agent", mock_create_deep_agent)

    config = AgentConfig(
        inference=InferenceConfig(api_key="mock-key"),
        model_name="mock-model",
        skills_implementation=SkillsImplementation.DEEPAGENTS,
    )
    agent = Agent(config=config, name="skills-toggle-agent")
    session = agent.create_session(name="skills-toggle-session")

    runner = SessionAgentRunner(session=session, agent_entity=agent)
    assert len(captured_kwargs) == 1
    assert captured_kwargs[0]["skills"] is not None
    assert len(captured_kwargs[0]["skills"]) >= 2

    # Switch to NONE and reload
    session.config.skills_implementation = SkillsImplementation.NONE
    runner.reload_config()
    assert len(captured_kwargs) == 2
    assert captured_kwargs[1]["skills"] is None


@pytest.mark.asyncio
async def test_session_agent_runner_unhandled_error_includes_type_and_traceback() -> None:
    """Verify unhandled exceptions during execution emit RUN_ERROR with error_type and traceback."""

    class FailingFakeAgent:
        def clone(self) -> "FailingFakeAgent":
            return self

        async def run(self, input_data: RunAgentInput) -> AsyncGenerator[Any, None]:
            yield RunStartedEvent(
                type=EventType.RUN_STARTED,
                thread_id=input_data.thread_id,
                run_id=input_data.run_id,
            )
            msg = "Simulated upstream provider failure (402 Payment Required)"
            raise RuntimeError(msg)

    config = AgentConfig(
        inference=InferenceConfig(api_key="mock-key"),
        model_name="mock-model",
    )
    agent = Agent(config=config, name="fail-agent")
    session = agent.create_session(name="fail-session")
    runner = SessionAgentRunner(session=session, agent=FailingFakeAgent())
    sub_queue = runner.broadcaster.subscribe()

    await runner.dispatch_user_input("Trigger failure")
    if runner._active_task is not None:
        await runner._active_task

    open_thread = session.get_open_thread()
    assert open_thread.status == AgentStatus.ERROR

    # Verify RUN_ERROR was appended to thread.events for SSE replay
    error_events = [
        ev for ev in open_thread.events if isinstance(ev, dict) and ev.get("type") == "RUN_ERROR"
    ]
    assert len(error_events) == 1
    err_ev = error_events[0]
    assert err_ev["message"] == "Simulated upstream provider failure (402 Payment Required)"
    assert err_ev["error_type"] == "RuntimeError"
    assert "RuntimeError: Simulated upstream provider failure" in err_ev["traceback"]

    # Also verify live broadcast received the enriched event
    live_events: list[Any] = []
    while not sub_queue.empty():
        live_events.append(sub_queue.get_nowait())
    live_err = [ev for ev in live_events if isinstance(ev, dict) and ev.get("type") == "RUN_ERROR"]
    assert len(live_err) == 1
    assert live_err[0]["error_type"] == "RuntimeError"
    assert "traceback" in live_err[0]


def test_session_agent_runner_recursion_limit_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify recursion_limit is configured on built SeamusLangGraphAgent and cloneable."""
    from unittest.mock import MagicMock

    def mock_create_deep_agent(**kwargs: Any) -> Any:
        mock_graph = MagicMock()
        mock_graph.nodes = {}
        return mock_graph

    monkeypatch.setattr("seamus.harness.runner.create_deep_agent", mock_create_deep_agent)

    config = AgentConfig(
        inference=InferenceConfig(api_key="mock-key"),
        model_name="mock-model",
    )
    agent = Agent(config=config, name="agent-rec")
    session = agent.create_session(name="sess-rec")

    # 1. Default recursion limit (250)
    runner_default = SessionAgentRunner(session=session)
    assert runner_default.recursion_limit == 250
    assert runner_default.agent.config == {"recursion_limit": 250}
    cloned = runner_default.agent.clone()
    assert cloned.config == {"recursion_limit": 250}

    # 2. Explicit recursion limit override
    runner_custom = SessionAgentRunner(session=session, recursion_limit=500)
    assert runner_custom.recursion_limit == 500
    assert runner_custom.agent.config == {"recursion_limit": 500}

    # 3. Environment variable override
    monkeypatch.setenv("SEAMUS_RECURSION_LIMIT", "350")
    runner_env = SessionAgentRunner(session=session)
    assert runner_env.recursion_limit == 350
    assert runner_env.agent.config == {"recursion_limit": 350}

    # 4. Provided agent without recursion_limit receives configured limit
    from ag_ui_langgraph import LangGraphAgent

    mock_graph2 = MagicMock()
    mock_graph2.nodes = {}
    external_agent = LangGraphAgent(name="ext", graph=mock_graph2)
    assert external_agent.config == {}
    runner_provided = SessionAgentRunner(session=session, agent=external_agent, recursion_limit=420)
    assert runner_provided.agent.config == {"recursion_limit": 420}
