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
    ToolCallStartEvent,
)
from ag_ui.core.types import RunAgentInput, TextInputContent, UserMessage
from ag_ui_langgraph.utils import resolve_reasoning_content
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from pydantic import SecretStr

from seamus.config.models import AgentConfig, InferenceConfig
from seamus.domain.entities import Agent, AgentStatus
from seamus.harness.runner import (
    EventBroadcaster,
    ReasoningChatOpenAI,
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
