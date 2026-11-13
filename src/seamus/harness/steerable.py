"""Steerable (scripted) chat model provider for deterministic local testing.

The steerable provider replaces a live LLM with a queue of scripted assistant
responses. Each queued entry may carry assistant text, reasoning content, and
tool calls, which lets a developer drive a session deterministically from the
Agent Inspector without incurring inference costs.

Instances are addressed by stable ids (``session:{session_id}:agent``,
``session:{session_id}:daemon:naming``) so the Inspector can address the agent
model and the daemon model separately.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from collections.abc import AsyncIterator, Iterator, Sequence
from typing import Any
from uuid import uuid4

from langchain_core.callbacks.manager import (
    AsyncCallbackManagerForLLMRun,
    CallbackManagerForLLMRun,
)
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field, PrivateAttr

from seamus.config.models import SteerableConfig, SteerableEmptyQueueStrategy

logger = logging.getLogger(__name__)

DEFAULT_STEERABLE_MODEL_NAME = "steerable"

REASONING_KWARG = "reasoning_content"


class SteerableToolCall(BaseModel):
    """A single scripted tool call."""

    name: str
    args: dict[str, Any] = Field(default_factory=dict)


class SteerableResponse(BaseModel):
    """One scripted assistant turn: optional text, reasoning, and tool calls."""

    text: str | None = None
    reasoning: str | None = None
    tool_calls: list[SteerableToolCall] = Field(default_factory=list)


class SteerableQueueEmptyError(RuntimeError):
    """Raised when a steerable model is asked to respond with an empty queue."""


class SteerableInstance(BaseModel):
    """Runtime state of a single steerable model instance."""

    instance_id: str
    role: str
    strategy: SteerableEmptyQueueStrategy = SteerableEmptyQueueStrategy.ERROR
    default_response: str = "No scripted response available."
    wait_timeout: float = 300.0
    responses: list[SteerableResponse] = Field(default_factory=list)
    known_tools: list[str] = Field(default_factory=list)

    _condition: threading.Condition = PrivateAttr(default_factory=threading.Condition)

    @property
    def pending_count(self) -> int:
        """Return the number of queued responses awaiting consumption."""
        return len(self.responses)

    def push(self, response: SteerableResponse) -> None:
        """Append a scripted response to the queue and wake up any waiter."""
        with self._condition:
            self.responses.append(response)
            self._condition.notify_all()

    def replace(self, responses: Sequence[SteerableResponse]) -> None:
        """Replace the whole queue with the given responses."""
        with self._condition:
            self.responses = list(responses)
            self._condition.notify_all()

    def pop(self) -> SteerableResponse | None:
        """Pop the next queued response without blocking."""
        with self._condition:
            if not self.responses:
                return None
            return self.responses.pop(0)

    def wait_for_response(self, timeout: float) -> SteerableResponse | None:
        """Block until a response is queued or the timeout elapses."""
        with self._condition:
            if not self.responses:
                self._condition.wait(timeout=timeout)
            if not self.responses:
                return None
            return self.responses.pop(0)

    async def wait_for_response_async(self, timeout: float) -> SteerableResponse | None:
        """Await a queued response without blocking the event loop thread."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while True:
            response = self.pop()
            if response is not None:
                return response
            remaining = deadline - loop.time()
            if remaining <= 0:
                return None
            await asyncio.sleep(min(0.05, remaining))


class SteerableModelRegistry:
    """Process-wide registry of steerable model instances keyed by instance id."""

    def __init__(self) -> None:
        self._instances: dict[str, SteerableInstance] = {}

    def register(self, instance: SteerableInstance) -> SteerableInstance:
        """Register (or replace) an instance and return it."""
        self._instances[instance.instance_id] = instance
        return instance

    def get(self, instance_id: str) -> SteerableInstance | None:
        """Return the instance registered under the given id, if any."""
        return self._instances.get(instance_id)

    def get_or_create(
        self,
        instance_id: str,
        role: str,
        config: SteerableConfig | None = None,
    ) -> SteerableInstance:
        """Return the registered instance, creating it when absent."""
        existing = self._instances.get(instance_id)
        if existing is not None:
            return existing
        cfg = config or SteerableConfig()
        return self.register(
            SteerableInstance(
                instance_id=instance_id,
                role=role,
                strategy=cfg.empty_queue_strategy,
                default_response=cfg.default_response,
                wait_timeout=cfg.wait_timeout,
            )
        )

    def list_for_session(self, session_id: Any) -> list[SteerableInstance]:
        """Return all instances belonging to the given session."""
        prefix = f"session:{session_id}:"
        return [
            instance
            for instance_id, instance in sorted(self._instances.items())
            if instance_id.startswith(prefix)
        ]

    def clear(self) -> None:
        """Remove every registered instance."""
        self._instances.clear()


_GLOBAL_STEERABLE_REGISTRY: SteerableModelRegistry | None = None


def get_steerable_registry() -> SteerableModelRegistry:
    """Return the global steerable model registry."""
    global _GLOBAL_STEERABLE_REGISTRY
    if _GLOBAL_STEERABLE_REGISTRY is None:
        _GLOBAL_STEERABLE_REGISTRY = SteerableModelRegistry()
    return _GLOBAL_STEERABLE_REGISTRY


def reset_steerable_registry(
    registry: SteerableModelRegistry | None = None,
) -> SteerableModelRegistry:
    """Reset the global steerable model registry (useful in tests)."""
    global _GLOBAL_STEERABLE_REGISTRY
    _GLOBAL_STEERABLE_REGISTRY = registry
    return get_steerable_registry()


def agent_instance_id(session_id: Any) -> str:
    """Return the registry id of the session's main agent model."""
    return f"session:{session_id}:agent"


def daemon_instance_id(session_id: Any, daemon: str = "naming") -> str:
    """Return the registry id of a session-scoped daemon model."""
    return f"session:{session_id}:daemon:{daemon}"


class SteerableChatModel(BaseChatModel):
    """A chat model that replays scripted responses instead of calling a provider."""

    model_name: str = DEFAULT_STEERABLE_MODEL_NAME
    instance_id: str = "steerable:default"
    role: str = "agent"

    _instance: SteerableInstance | None = PrivateAttr(default=None)

    @property
    def _llm_type(self) -> str:
        return "steerable"

    @property
    def instance(self) -> SteerableInstance:
        """Return the runtime instance backing this model, creating it if needed."""
        if self._instance is None:
            self._instance = get_steerable_registry().get_or_create(self.instance_id, self.role)
        return self._instance

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Any | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """Record the bound tool names so the Inspector can show them."""
        names: list[str] = []
        for tool in tools:
            name = getattr(tool, "name", None)
            if name is None and isinstance(tool, dict):
                name = tool.get("name")
            if name is None:
                function = tool.get("function") if isinstance(tool, dict) else None
                if isinstance(function, dict):
                    name = function.get("name")
            if isinstance(name, str):
                names.append(name)
        self.instance.known_tools = names
        return self.bind(tools=list(tools), **kwargs)

    def _consume_response(self) -> SteerableResponse:
        """Consume the next scripted response according to the instance strategy."""
        instance = self.instance
        response = instance.pop()
        if response is not None:
            return response

        if instance.strategy == SteerableEmptyQueueStrategy.REPEAT:
            return SteerableResponse(text=instance.default_response)
        if instance.strategy == SteerableEmptyQueueStrategy.ERROR:
            raise SteerableQueueEmptyError(
                f"Steerable model '{self.instance_id}' has an empty response queue."
            )

        # WAIT: block until a response is pushed (or the wait times out).
        response = instance.wait_for_response(instance.wait_timeout)
        if response is None:
            raise SteerableQueueEmptyError(
                f"Steerable model '{self.instance_id}' timed out after "
                f"{instance.wait_timeout}s waiting for a scripted response."
            )
        return response

    async def _consume_response_async(self) -> SteerableResponse:
        """Consume the next scripted response without blocking the event loop."""
        instance = self.instance
        response = instance.pop()
        if response is not None:
            return response

        if instance.strategy == SteerableEmptyQueueStrategy.REPEAT:
            return SteerableResponse(text=instance.default_response)
        if instance.strategy == SteerableEmptyQueueStrategy.ERROR:
            raise SteerableQueueEmptyError(
                f"Steerable model '{self.instance_id}' has an empty response queue."
            )

        response = await instance.wait_for_response_async(instance.wait_timeout)
        if response is None:
            raise SteerableQueueEmptyError(
                f"Steerable model '{self.instance_id}' timed out after "
                f"{instance.wait_timeout}s waiting for a scripted response."
            )
        return response

    def _warn_unknown_tools(self, response: SteerableResponse) -> None:
        """Log a warning when a scripted tool call targets an unbound tool."""
        known = set(self.instance.known_tools)
        if not known:
            return
        for call in response.tool_calls:
            if call.name not in known:
                logger.warning(
                    "Steerable model '%s' scripted a call to unknown tool '%s' (known tools: %s)",
                    self.instance_id,
                    call.name,
                    ", ".join(sorted(known)) or "(none)",
                )

    def _build_chunks(self, response: SteerableResponse) -> list[AIMessageChunk]:
        """Build the ordered generation chunks for a scripted response.

        Reasoning and text are emitted as separate chunks so the AG-UI layer
        surfaces them as distinct reasoning and text events. Reasoning travels
        in ``additional_kwargs["reasoning_content"]``, the same shape
        ``ReasoningChatOpenAI`` produces, so checkpointed messages and AG-UI
        snapshots treat scripted turns exactly like live ones. Tool calls are
        split into a name chunk and an arguments chunk, mirroring how OpenAI
        compatible providers stream tool calls.
        """
        self._warn_unknown_tools(response)
        message_id = f"msg_{uuid4().hex[:12]}"
        chunks: list[AIMessageChunk] = []

        if response.reasoning:
            chunks.append(
                AIMessageChunk(
                    content="",
                    additional_kwargs={REASONING_KWARG: response.reasoning},
                    id=message_id,
                )
            )

        if response.text:
            chunks.append(
                AIMessageChunk(
                    content=response.text,
                    id=message_id,
                )
            )

        for index, call in enumerate(response.tool_calls):
            call_id = f"call_{uuid4().hex[:12]}_{index}"
            chunks.append(
                AIMessageChunk(
                    content="",
                    tool_call_chunks=[
                        {"name": call.name, "args": "", "id": call_id, "index": index}
                    ],
                    id=message_id,
                )
            )
            chunks.append(
                AIMessageChunk(
                    content="",
                    tool_call_chunks=[
                        {
                            "name": None,
                            "args": json.dumps(call.args),
                            "id": call_id,
                            "index": index,
                        }
                    ],
                    id=message_id,
                )
            )

        if not chunks:
            chunks.append(AIMessageChunk(content="", id=message_id))
        return chunks

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Produce a scripted response for the given messages."""
        chunks = self._build_chunks(self._consume_response())
        message = _merge_chunks(chunks)
        return ChatResult(generations=[ChatGeneration(message=message)])

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Produce a scripted response without blocking the event loop."""
        chunks = self._build_chunks(await self._consume_response_async())
        message = _merge_chunks(chunks)
        return ChatResult(generations=[ChatGeneration(message=message)])

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        """Stream the scripted response as discrete chunks."""
        for chunk in self._build_chunks(self._consume_response()):
            yield ChatGenerationChunk(message=chunk)

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        """Stream the scripted response as discrete chunks (async path)."""
        for chunk in self._build_chunks(await self._consume_response_async()):
            yield ChatGenerationChunk(message=chunk)


def _merge_chunks(chunks: Sequence[AIMessageChunk]) -> AIMessage:
    """Merge generation chunks into the final assistant message."""
    from langchain_core.messages.ai import add_ai_message_chunks

    merged = chunks[0]
    for chunk in chunks[1:]:
        merged = add_ai_message_chunks(merged, chunk)
    return AIMessage(
        content=merged.content,
        tool_calls=merged.tool_calls,
        additional_kwargs=merged.additional_kwargs,
        id=merged.id,
    )


def build_steerable_model(
    instance_id: str,
    role: str,
    config: SteerableConfig | None = None,
    model_name: str = DEFAULT_STEERABLE_MODEL_NAME,
) -> SteerableChatModel:
    """Create a steerable chat model bound to a registry instance."""
    registry = get_steerable_registry()
    instance = registry.get_or_create(instance_id, role, config)
    model = SteerableChatModel(model_name=model_name, instance_id=instance_id, role=role)
    model._instance = instance
    return model


__all__ = [
    "DEFAULT_STEERABLE_MODEL_NAME",
    "SteerableChatModel",
    "SteerableInstance",
    "SteerableModelRegistry",
    "SteerableQueueEmptyError",
    "SteerableResponse",
    "SteerableToolCall",
    "agent_instance_id",
    "build_steerable_model",
    "daemon_instance_id",
    "get_steerable_registry",
    "reset_steerable_registry",
]
