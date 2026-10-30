"""Unit tests for SessionAgentRunner, EventBroadcaster, and status lifecycle."""

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

import pytest
from ag_ui.core.events import (
    EventType,
    RunFinishedEvent,
    RunStartedEvent,
    TextMessageChunkEvent,
    ToolCallStartEvent,
)
from ag_ui.core.types import RunAgentInput

from seamus.config.models import AgentConfig, InferenceConfig
from seamus.domain.entities import Agent, AgentStatus
from seamus.harness.runner import (
    EventBroadcaster,
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
