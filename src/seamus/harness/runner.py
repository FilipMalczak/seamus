"""Session agent execution runner, DeepAgent lifecycle, and AG-UI event broadcasting."""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from typing import Any
from uuid import uuid4

from ag_ui.core.events import (
    EventType,
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
)
from ag_ui.core.types import RunAgentInput, TextInputContent, UserMessage
from ag_ui.encoder import EventEncoder
from ag_ui_langgraph import LangGraphAgent
from deepagents import create_deep_agent
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from pydantic import SecretStr

from seamus.domain.entities import AgentStatus, Session, Thread

logger = logging.getLogger(__name__)


class SessionBusyError(RuntimeError):
    """Raised when an input is dispatched to a session while it is still running a task."""


class EventBroadcaster:
    """Pub-sub broadcaster distributing events to all active thread SSE subscribers."""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[Any]] = set()

    def subscribe(self) -> asyncio.Queue[Any]:
        """Register a new listener queue."""
        queue: asyncio.Queue[Any] = asyncio.Queue()
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[Any]) -> None:
        """Remove a listener queue."""
        self._subscribers.discard(queue)

    async def broadcast(self, event: Any) -> None:
        """Deliver an event to all registered subscriber queues."""
        for queue in list(self._subscribers):
            try:
                await queue.put(event)
            except Exception:
                logger.exception("Failed to deliver event to subscriber queue")


class SessionAgentRunner:
    """Manages the DeepAgent instance and execution loop for a single session."""

    def __init__(
        self,
        session: Session,
        agent: LangGraphAgent | None = None,
    ) -> None:
        self.session = session
        self.broadcaster = EventBroadcaster()
        self._lock = asyncio.Lock()
        self._active_task: asyncio.Task[None] | None = None

        if agent is not None:
            self._agent = agent
        else:
            self._agent = self._build_deep_agent()

    def _build_deep_agent(self) -> LangGraphAgent:
        """Instantiate the DeepAgent graph and wrap it in a LangGraphAgent."""
        self.session.config.validate_complete()
        api_key = self.session.config.inference.api_key or ""
        base_url = self.session.config.inference.base_url

        llm = ChatOpenAI(
            model=self.session.config.model_name,
            api_key=SecretStr(api_key),
            base_url=base_url,
        )

        checkpointer = MemorySaver()
        graph = create_deep_agent(
            model=llm,
            checkpointer=checkpointer,
        )

        return LangGraphAgent(
            name=f"session-agent-{self.session.id}",
            graph=graph,
            description=f"DeepAgent for session {self.session.id}",
        )

    def is_awaiting_user(self) -> bool:
        """Check if the session's active thread is currently awaiting user input."""
        thread = self.session.get_open_thread()
        return thread.status == AgentStatus.AWAITING_USER and (
            self._active_task is None or self._active_task.done()
        )

    async def dispatch_user_input(
        self,
        text: str,
        message_id: str | None = None,
    ) -> str:
        """Dispatch a user message to the active thread and start execution."""
        async with self._lock:
            thread = self.session.get_open_thread()
            if not self.is_awaiting_user():
                msg = (
                    f"Agent in session '{self.session.id}' is not in AWAITING_USER state "
                    f"(current status: {thread.status.value})."
                )
                raise SessionBusyError(msg)

            thread.status = AgentStatus.AWAITING_LLM
            thread.touch()
            self.session.touch()

            user_msg_id = message_id or uuid4().hex
            user_msg = UserMessage(
                id=user_msg_id,
                role="user",
                content=[TextInputContent(text=text)],
            )

            # Record user message as AG-UI events in thread history so they replay on reconnect
            user_start = TextMessageStartEvent(message_id=user_msg_id, role="user")
            user_content = TextMessageContentEvent(message_id=user_msg_id, delta=text)
            user_end = TextMessageEndEvent(message_id=user_msg_id)

            thread.append_event(user_start)
            thread.append_event(user_content)
            thread.append_event(user_end)
            await self.broadcaster.broadcast(user_start)
            await self.broadcaster.broadcast(user_content)
            await self.broadcaster.broadcast(user_end)

            # Start execution task in the background
            self._active_task = asyncio.create_task(
                self._run_loop(thread=thread, user_message=user_msg)
            )

            return user_msg_id

    async def _run_loop(self, thread: Thread, user_message: UserMessage) -> None:
        """Internal execution loop consuming LangGraphAgent run generator."""
        input_data = RunAgentInput(
            thread_id=thread.id.hex,
            run_id=uuid4().hex,
            messages=[user_message],
        )

        request_agent = self._agent.clone()
        try:
            async for event in request_agent.run(input_data):
                self._update_status_from_event(thread, event)
                thread.append_event(event)
                await self.broadcaster.broadcast(event)
        except Exception as exc:
            logger.exception("Error during session agent execution")
            thread.status = AgentStatus.ERROR
            thread.touch()
            await self.broadcaster.broadcast({"type": "RUN_ERROR", "message": str(exc)})
        finally:
            if thread.status != AgentStatus.ERROR:
                thread.status = AgentStatus.AWAITING_USER
            thread.touch()
            self.session.touch()

    def _update_status_from_event(self, thread: Thread, event: Any) -> None:
        """Update thread status based on AG-UI event type."""
        event_type = getattr(event, "type", None)
        if event_type == EventType.RUN_STARTED:
            thread.status = AgentStatus.AWAITING_LLM
        elif event_type in (
            EventType.TOOL_CALL_START,
            EventType.TOOL_CALL_ARGS,
            EventType.TOOL_CALL_CHUNK,
        ):
            thread.status = AgentStatus.EXECUTING_TOOL
        elif event_type in (
            EventType.TOOL_CALL_RESULT,
            EventType.TOOL_CALL_END,
            EventType.TEXT_MESSAGE_START,
            EventType.TEXT_MESSAGE_CHUNK,
            EventType.TEXT_MESSAGE_CONTENT,
            EventType.TEXT_MESSAGE_END,
        ):
            thread.status = AgentStatus.AWAITING_LLM
        elif event_type in (EventType.RUN_FINISHED,):
            thread.status = AgentStatus.AWAITING_USER
        elif event_type in (EventType.RUN_ERROR,):
            thread.status = AgentStatus.ERROR

    @staticmethod
    def _format_sse_event(encoder: EventEncoder, event: Any) -> str:
        """Format an event into an SSE data frame."""
        if hasattr(event, "model_dump_json"):
            return encoder.encode(event)
        if isinstance(event, dict):
            return f"data: {json.dumps(event)}\n\n"
        return f"data: {event}\n\n"

    async def stream_thread_events(
        self,
        thread: Thread,
        accept_header: str | None = None,
        follow: bool = True,
    ) -> AsyncGenerator[str, None]:
        """Stream past events from history, then stream live events if thread is open."""
        encoder = EventEncoder(accept=accept_header or "*/*")

        # 1. Replay past events
        for event in thread.events:
            yield self._format_sse_event(encoder, event)

        # If thread is closed or client requested replay only, finish stream immediately
        if not thread.is_open or not follow:
            return

        # 2. Subscribe and stream live events
        queue = self.broadcaster.subscribe()
        try:
            while thread.is_open:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=1.0)
                    yield self._format_sse_event(encoder, event)
                except TimeoutError:
                    # Keepalive ping or check if thread was closed
                    continue
        finally:
            self.broadcaster.unsubscribe(queue)


class RunnerRegistry:
    """Maintains active SessionAgentRunner instances keyed by session ID."""

    def __init__(self) -> None:
        self._runners: dict[str, SessionAgentRunner] = {}

    def get_runner(self, session: Session) -> SessionAgentRunner:
        """Get or create the SessionAgentRunner for a session."""
        session_key = str(session.id)
        if session_key not in self._runners:
            self._runners[session_key] = SessionAgentRunner(session=session)
        return self._runners[session_key]

    def set_runner(self, session_id: str, runner: SessionAgentRunner) -> None:
        """Register a specific runner instance (useful for testing with mock agents)."""
        self._runners[session_id] = runner


_GLOBAL_RUNNER_REGISTRY: RunnerRegistry | None = None


def get_runner_registry() -> RunnerRegistry:
    """Return the global runner registry."""
    global _GLOBAL_RUNNER_REGISTRY
    if _GLOBAL_RUNNER_REGISTRY is None:
        _GLOBAL_RUNNER_REGISTRY = RunnerRegistry()
    return _GLOBAL_RUNNER_REGISTRY


def reset_runner_registry(registry: RunnerRegistry | None = None) -> RunnerRegistry:
    """Reset the global runner registry (useful in tests)."""
    global _GLOBAL_RUNNER_REGISTRY
    _GLOBAL_RUNNER_REGISTRY = registry
    return get_runner_registry()
