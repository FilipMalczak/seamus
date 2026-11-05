"""Session agent execution runner, DeepAgent lifecycle, and AG-UI event broadcasting."""

import asyncio
import json
import logging
import os
import traceback
from collections.abc import AsyncGenerator, Mapping, Sequence
from typing import Any, Literal, Self, cast
from uuid import uuid4

import logfire
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
from langchain.agents.middleware import TodoListMiddleware
from langchain.agents.middleware.todo import (
    WRITE_TODOS_SYSTEM_PROMPT,
    WRITE_TODOS_TOOL_DESCRIPTION,
    PlanningState,
)
from langchain.agents.middleware.types import ContextT, ResponseT
from langchain.tools import ToolRuntime
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGenerationChunk, ChatResult
from langchain_core.tools import StructuredTool
from langchain_openai import ChatOpenAI
from langgraph.types import Command
from pydantic import BaseModel, Field, SecretStr, model_validator

from seamus.config.models import SkillsImplementation, TodoImplementation
from seamus.config.settings import get_system_settings_store
from seamus.domain.artifacts import CadenceMode
from seamus.domain.entities import Agent, AgentStatus, Session, Thread
from seamus.domain.modes import (
    ALL_HARNESS_TOOLS,
    ModeName,
    PlanPhase,
    normalize_mode_and_phase,
    resolve_available_harness_tools,
    resolve_mount_policy,
)
from seamus.harness.artifacts import (
    ArtifactResolver,
    PlanBuilder,
    QuestionItem,
    QuestionnaireBuilder,
    seed_default_artifacts,
)
from seamus.harness.prompt import (
    DynamicSystemPromptMiddleware,
    build_effective_system_prompt,
    build_scaffold_prompt,
)
from seamus.harness.sandbox import (
    SeamusOpenSandboxBackend,
    get_sandbox_settings,
)
from seamus.persistence import GitCheckpointSaver, get_workspace_manager

logger = logging.getLogger(__name__)

DEFAULT_RECURSION_LIMIT: int = 250


def _extract_reasoning_text(payload: Mapping[str, Any]) -> str | None:
    """Extract reasoning text from OpenAI-compatible or OpenRouter message/delta payloads."""
    for key in ("reasoning", "reasoning_content"):
        val = payload.get(key)
        if isinstance(val, str) and val:
            return val

    details = payload.get("reasoning_details")
    if isinstance(details, list):
        parts: list[str] = []
        for item in details:
            if isinstance(item, Mapping):
                text = item.get("text") or item.get("summary")
                if isinstance(text, str) and text:
                    parts.append(text)
        if parts:
            return "".join(parts)

    return None


class ReasoningChatOpenAI(ChatOpenAI):
    """ChatOpenAI subclass that preserves OpenAI-compatible and OpenRouter reasoning fields."""

    def _convert_chunk_to_generation_chunk(
        self,
        chunk: dict[str, Any],
        default_chunk_class: type,
        base_generation_info: dict[str, Any] | None,
    ) -> ChatGenerationChunk | None:
        gen_chunk = super()._convert_chunk_to_generation_chunk(
            chunk, default_chunk_class, base_generation_info
        )
        if gen_chunk is not None:
            choices = chunk.get("choices") or chunk.get("chunk", {}).get("choices") or []
            if choices and isinstance(choices[0], Mapping):
                delta = choices[0].get("delta")
                if isinstance(delta, Mapping):
                    reasoning_text = _extract_reasoning_text(delta)
                    if reasoning_text:
                        gen_chunk.message.additional_kwargs["reasoning_content"] = reasoning_text
        return gen_chunk

    def _create_chat_result(
        self,
        response: dict[str, Any] | Any,
        generation_info: dict[str, Any] | None = None,
    ) -> ChatResult:
        result = super()._create_chat_result(response, generation_info)
        response_dict: Mapping[str, Any] = (
            response
            if isinstance(response, Mapping)
            else response.model_dump(
                exclude={"choices": {"__all__": {"message": {"parsed"}}}},
                warnings=False,
            )
            if hasattr(response, "model_dump")
            else {}
        )
        choices = response_dict.get("choices") or []
        for choice, gen in zip(choices, result.generations, strict=False):
            if isinstance(choice, Mapping):
                msg_dict = choice.get("message")
                if isinstance(msg_dict, Mapping):
                    reasoning_text = _extract_reasoning_text(msg_dict)
                    if reasoning_text:
                        gen.message.additional_kwargs["reasoning_content"] = reasoning_text
        return result


class SeamusLangGraphAgent(LangGraphAgent):  # type: ignore[misc]
    """LangGraphAgent subclass that preserves full checkpoint message history in graph input."""

    def langgraph_default_merge_state(
        self,
        state: Any,
        messages: list[Any],
        input: RunAgentInput,
    ) -> Any:
        existing_messages = list(state.get("messages", [])) if isinstance(state, Mapping) else []
        merged = super().langgraph_default_merge_state(state, messages, input)
        if isinstance(merged, dict):
            delta_messages = list(merged.get("messages", []))
            delta_by_id = {
                getattr(m, "id", None): m for m in delta_messages if getattr(m, "id", None)
            }
            existing_ids = {
                getattr(m, "id", None) for m in existing_messages if getattr(m, "id", None)
            }
            combined = [delta_by_id.get(getattr(m, "id", None), m) for m in existing_messages]
            combined.extend(m for m in delta_messages if getattr(m, "id", None) not in existing_ids)
            merged["messages"] = combined
        return merged


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

    def broadcast_sync(self, event: Any) -> None:
        """Deliver an event synchronously without awaiting queue.put."""
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except Exception:
                pass


class ResilientTodoItem(BaseModel):
    """Normalized todo item accepting common LLM field variations."""

    content: str = Field(description="The content/description of the todo item.")
    status: Literal["pending", "in_progress", "completed"] = Field(
        default="pending",
        description="The current status of the todo item.",
    )

    @model_validator(mode="before")
    @classmethod
    def _normalize_item(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        d = dict(data)
        if "content" not in d:
            for alias in ("task", "name", "title", "description", "todo"):
                if alias in d and d[alias]:
                    d["content"] = str(d[alias])
                    break
        status_val = d.get("status")
        if status_val is None:
            for alias in ("state", "progress", "condition"):
                if alias in d:
                    status_val = d[alias]
                    break
        if isinstance(status_val, str):
            s = status_val.strip().lower().replace("-", "_").replace(" ", "_")
            if s in ("pending", "todo", "open", "not_started", "unstarted", "waiting"):
                d["status"] = "pending"
            elif s in ("in_progress", "inprogress", "running", "active", "started", "working"):
                d["status"] = "in_progress"
            elif s in ("completed", "complete", "done", "finished", "closed", "resolved"):
                d["status"] = "completed"
            else:
                d["status"] = "pending"
        else:
            d["status"] = "pending"
        return d


class ResilientWriteTodosInput(BaseModel):
    """Input schema for write_todos tool that normalizes LLM argument variations."""

    todos: list[ResilientTodoItem] = Field(description="List of todo items.")

    @model_validator(mode="before")
    @classmethod
    def _normalize_todos(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        d = dict(data)
        if "todos" not in d:
            for alias in ("tasks", "items", "todo_list", "plan"):
                if alias in d:
                    d["todos"] = d[alias]
                    break
        if not isinstance(d.get("todos"), list):
            if isinstance(d.get("todos"), dict):
                d["todos"] = [d["todos"]]
            elif "content" in d or "task" in d or "name" in d:
                d["todos"] = [d]
        return d


def _resilient_write_todos(
    runtime: ToolRuntime[ContextT, PlanningState[ResponseT]],
    todos: Sequence[Any],
) -> Command[Any]:
    validated = ResilientWriteTodosInput.model_validate({"todos": list(todos)})
    normalized = [{"content": t.content, "status": t.status} for t in validated.todos]
    return Command(
        update={
            "todos": normalized,
            "messages": [
                ToolMessage(
                    content=f"Updated todo list to {normalized}",
                    tool_call_id=runtime.tool_call_id,
                )
            ],
        }
    )


async def _aresilient_write_todos(
    runtime: ToolRuntime[ContextT, PlanningState[ResponseT]],
    todos: Sequence[Any],
) -> Command[Any]:
    return _resilient_write_todos(runtime, todos=todos)


SEAMUS_WRITE_TODOS_SYSTEM_PROMPT = f"""{WRITE_TODOS_SYSTEM_PROMPT}

## Expected Tool Arguments Schema

When calling `write_todos`, always provide `todos` as a list of objects with `content` and `status`:
```json
{{
  "todos": [
    {{"content": "Step 1 description", "status": "in_progress"}},
    {{"content": "Step 2 description", "status": "pending"}}
  ]
}}
```
Valid statuses: "pending", "in_progress", "completed".
"""


class ResilientAskInput(BaseModel):
    """Input schema for the ask tool."""

    question: str = Field(description="The closed question to ask the user.")
    answers: list[str] = Field(
        ...,
        description=(
            "The list of possible answers for the user to choose from. Required. "
            "Must contain at least 2 choices if writein=False and multiple=False, "
            "or at least 1 choice if writein=True or multiple=True."
        ),
    )
    multiple: bool = Field(
        default=False,
        description="Whether to allow selecting multiple options (multi-select).",
    )
    writein: bool = Field(
        default=False,
        description="Whether to include an 'Other: [text field]' option for user write-in.",
    )
    id: str | None = Field(
        default=None,
        description="Optional unique identifier for the question (e.g. 'backgroundColor').",
    )

    @model_validator(mode="before")
    @classmethod
    def _normalize_answers(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        d = dict(data)
        if "answers" not in d:
            for alias in ("options", "choices", "asnwers", "possible_answers"):
                if alias in d:
                    d["answers"] = d[alias]
                    break
        if not isinstance(d.get("answers"), list):
            if d.get("answers") is not None:
                d["answers"] = [str(d["answers"])]
        if "multiple" not in d:
            for m_alias in ("multi_select", "multiselect", "multi"):
                if m_alias in d:
                    d["multiple"] = bool(d[m_alias])
                    break
        return d

    @model_validator(mode="after")
    def _validate_answers_cardinality(self) -> Self:
        min_answers = 1 if (self.writein or self.multiple) else 2
        if len(self.answers) < min_answers:
            if self.multiple:
                msg = (
                    f"Question '{self.question}' with multiple=True requires at least 1 choice in "
                    f"'answers' (got {len(self.answers)})."
                )
            elif self.writein:
                msg = (
                    f"Question '{self.question}' with writein=True requires at least 1 choice in "
                    f"'answers' (got {len(self.answers)})."
                )
            else:
                msg = (
                    f"Question '{self.question}' with writein=False requires at least 2 choices in "
                    f"'answers' (got {len(self.answers)})."
                )
            raise ValueError(msg)
        return self


class ResilientFormInput(ResilientAskInput):
    """Input schema for the form tool (tabbed, non-blocking questionnaire in Plan/Discuss)."""

    title: str = Field(
        default="Form",
        description="Optional display title for the form tab (defaults to 'Form').",
    )


class ReadArtifactSubmissionInput(BaseModel):
    """Input schema for read_artifact_submission tool."""

    artifact_id: str = Field(description="UUID of the questionnaire, form, or plan artifact.")


class PlanTransitionInput(BaseModel):
    """Input schema for the plan() phase transition tool."""


class MakePlanInput(BaseModel):
    """Input schema for the make_plan tool in Plan/Make phase."""

    content: str = Field(description="Full GitHub-Flavored Markdown content of the plan.")
    name: str = Field(
        default="Plan",
        description="Display title for the Plan tab (defaults to 'Plan').",
    )


class UpdatePlanInput(BaseModel):
    """Input schema for the update_plan tool in Plan/Make phase."""

    content: str = Field(description="Updated full GitHub-Flavored Markdown content of the plan.")


class EditPlanInput(BaseModel):
    """Input schema for the edit_plan tool in Plan/Make phase."""

    old_string: str = Field(
        description="Exact existing substring in the active plan Markdown to replace."
    )
    new_string: str = Field(description="Replacement string to substitute in place of old_string.")


class DiscardInput(BaseModel):
    """Input schema for the discard() tool across Plan mode phases."""


class SeamusTodoListMiddleware(TodoListMiddleware):
    """TodoListMiddleware providing resilient argument normalization and JSON schema guidance."""

    def __init__(
        self,
        *,
        system_prompt: str = SEAMUS_WRITE_TODOS_SYSTEM_PROMPT,
        tool_description: str = WRITE_TODOS_TOOL_DESCRIPTION,
    ) -> None:
        super().__init__(system_prompt=system_prompt, tool_description=tool_description)
        self.tools = [
            StructuredTool.from_function(
                name="write_todos",
                description=tool_description,
                func=_resilient_write_todos,
                coroutine=_aresilient_write_todos,
                args_schema=ResilientWriteTodosInput,
                infer_schema=False,
            )
        ]


class SessionAgentRunner:
    """Manages the DeepAgent instance and execution loop for a single session."""

    def __init__(
        self,
        session: Session,
        agent: LangGraphAgent | None = None,
        agent_entity: Agent | None = None,
        recursion_limit: int | None = None,
    ) -> None:
        self.session = session
        self.recursion_limit = (
            recursion_limit
            if recursion_limit is not None
            else int(os.environ.get("SEAMUS_RECURSION_LIMIT", str(DEFAULT_RECURSION_LIMIT)))
        )
        self.broadcaster = EventBroadcaster()
        self._lock = asyncio.Lock()
        self._active_task: asyncio.Task[None] | None = None
        self._agent_entity = agent_entity
        self._sandbox_backend: SeamusOpenSandboxBackend | None = None
        self.checkpointer: GitCheckpointSaver | None = getattr(agent, "checkpointer", None)
        self._pending_questions: list[QuestionItem] = []
        self._current_questionnaire_id: str | None = None
        self._pending_form_questions: list[QuestionItem] = []
        self._current_form_id: str | None = None
        self._current_form_title: str = "Form"
        self._turn_created_artifact_ids: set[str] = set()
        self._pending_phase_transition: tuple[str, str | None, bool] | None = None

        if agent is not None:
            self._agent = agent
            if hasattr(self._agent, "config"):
                agent_cfg = dict(self._agent.config) if self._agent.config else {}
                if "recursion_limit" not in agent_cfg:
                    agent_cfg["recursion_limit"] = self.recursion_limit
                    self._agent.config = agent_cfg
        else:
            self._agent = self._build_deep_agent()

    def _resolve_agent_entity(self) -> Agent | None:
        """Resolve the parent Agent entity if not already provided."""
        if self._agent_entity is not None:
            return self._agent_entity
        try:
            from seamus.harness.store import get_harness_store

            store = get_harness_store()
            self._agent_entity = store.resolve_agent(str(self.session.agent_id))
            return self._agent_entity
        except Exception:
            return None

    def _build_deep_agent(self) -> LangGraphAgent:
        """Instantiate the DeepAgent graph and wrap it in a SeamusLangGraphAgent."""
        self.session.config.validate_complete()
        api_key = self.session.config.inference.api_key or ""
        base_url = self.session.config.inference.base_url

        llm = ReasoningChatOpenAI(
            model=self.session.config.model_name,
            api_key=SecretStr(api_key),
            base_url=base_url,
        )

        # Prepare Git workspace and isolate agent files under data/
        ws_mgr = get_workspace_manager()
        agent_entity = self._resolve_agent_entity()
        if agent_entity is not None:
            ws_mgr.create_session_workspace(self.session, agent_entity)

        data_dir = ws_mgr.get_session_data_dir(self.session.agent_id, self.session.id)
        data_dir.mkdir(parents=True, exist_ok=True)
        artifacts_dir = ws_mgr.get_session_artifacts_dir(self.session.agent_id, self.session.id)
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        seed_default_artifacts(artifacts_dir)
        notes_dir = ws_mgr.get_session_notes_dir(self.session.agent_id, self.session.id)
        notes_dir.mkdir(parents=True, exist_ok=True)

        open_thread = (
            self.session.get_open_thread()
            if self.session.is_active or self.session.threads
            else None
        )
        mode = open_thread.mode if open_thread else ModeName.CHAT.value
        phase = open_thread.phase if open_thread else None
        mount_policy = resolve_mount_policy(mode, phase)

        sandbox_settings = get_sandbox_settings()
        system_settings = get_system_settings_store().get_settings()
        sandbox_backend = SeamusOpenSandboxBackend(
            agent_id=self.session.agent_id,
            session_id=self.session.id,
            data_dir=data_dir,
            artifacts_dir=artifacts_dir,
            notes_dir=notes_dir,
            workspace_readonly=mount_policy.workspace_readonly,
            notes_mounted=mount_policy.notes_mounted,
            notes_readonly=mount_policy.notes_readonly,
            settings=sandbox_settings,
            skill_directories=system_settings.skill_directories,
        )
        self._sandbox_backend = sandbox_backend
        sandbox_prompt = build_scaffold_prompt(
            sandbox_settings.workdir,
            mode=mode,
            phase=phase,
            active_plan_id=self.session.active_plan_id,
            active_plan_title=self._get_active_plan_title(),
        )
        effective_prompt = self.build_effective_system_prompt()

        self._sandbox_system_prompt = sandbox_prompt
        self._effective_system_prompt = effective_prompt

        dynamic_prompt_middleware = DynamicSystemPromptMiddleware(
            prompt_provider=lambda _req: self.build_effective_system_prompt(),
            tools_provider=lambda req: self.get_active_tools_for_request(req.tools),
            messages_provider=self._provide_messages_for_request,
            should_short_circuit=lambda _req: self._pending_phase_transition is not None,
        )

        checkpointer = GitCheckpointSaver(
            agent_id=self.session.agent_id,
            session_id=self.session.id,
            workspace_manager=ws_mgr,
        )
        self.checkpointer = checkpointer

        skill_sources = (
            sandbox_backend.get_skill_sources()
            if self.session.config.skills_implementation == SkillsImplementation.DEEPAGENTS
            else None
        )

        runner_middleware: list[Any] = [dynamic_prompt_middleware]
        if self.session.config.todo_implementation == TodoImplementation.DEEPAGENTS:
            runner_middleware.append(SeamusTodoListMiddleware())

        ask_tool = StructuredTool.from_function(
            name="ask",
            description=(
                "Ask the user a closed question with multiple choices and an optional write-in "
                "field. Batch multiple questions in the same turn to generate an embedded, "
                "blocking questionnaire."
            ),
            func=self.handle_ask,
            args_schema=ResilientAskInput,
        )

        form_tool = StructuredTool.from_function(
            name="form",
            description=(
                "Create a tabbed, non-blocking questionnaire form in a dedicated tab to the "
                "right of Changes. Batch multiple questions in the same turn to populate the form."
            ),
            func=self.handle_form,
            args_schema=ResilientFormInput,
        )

        read_sub_tool = StructuredTool.from_function(
            name="read_artifact_submission",
            description=(
                "Read the canonical user-submitted data model for a questionnaire or form "
                "artifact. Calling this on a non-blocking artifact promotes it to blocking. "
                "Cannot be called in the same turn that created the artifact."
            ),
            func=self.handle_read_artifact_submission,
            args_schema=ReadArtifactSubmissionInput,
        )

        plan_tool = StructuredTool.from_function(
            name="plan",
            description=(
                "Transition the session from the Discuss phase to the Make phase in a new "
                "thread. Call only after recording organized requirement notes in "
                "`/workspace/notes`."
            ),
            func=self.handle_plan,
            args_schema=PlanTransitionInput,
        )

        make_plan_tool = StructuredTool.from_function(
            name="make_plan",
            description=(
                "Create the session's Markdown implementation plan artifact in a dedicated "
                "tab with a Proceed button. Once called, make_plan is replaced by update_plan "
                "and edit_plan."
            ),
            func=self.handle_make_plan,
            args_schema=MakePlanInput,
        )

        update_plan_tool = StructuredTool.from_function(
            name="update_plan",
            description=(
                "Overwrite the full Markdown content of the active session plan artifact."
            ),
            func=self.handle_update_plan,
            args_schema=UpdatePlanInput,
        )

        edit_plan_tool = StructuredTool.from_function(
            name="edit_plan",
            description=(
                "Perform an exact string replacement (old_string -> new_string) on the active "
                "session plan's Markdown content."
            ),
            func=self.handle_edit_plan,
            args_schema=EditPlanInput,
        )

        discard_tool = StructuredTool.from_function(
            name="discard",
            description=(
                "Discard any active session plan and open a new thread back in the Discuss "
                "phase. Use ONLY when explicitly commanded by the user."
            ),
            func=self.handle_discard,
            args_schema=DiscardInput,
        )

        artifact_tools = [
            ask_tool,
            form_tool,
            read_sub_tool,
            plan_tool,
            make_plan_tool,
            update_plan_tool,
            edit_plan_tool,
            discard_tool,
        ]

        graph = create_deep_agent(
            model=llm,
            tools=artifact_tools,
            backend=sandbox_backend,
            system_prompt=effective_prompt,
            middleware=runner_middleware,
            checkpointer=checkpointer,
            skills=cast(Any, skill_sources),
        )

        return SeamusLangGraphAgent(
            name=f"session-agent-{self.session.id}",
            graph=graph,
            description=f"DeepAgent for session {self.session.id}",
            config={"recursion_limit": self.recursion_limit},
        )

    def _get_active_plan_title(self) -> str | None:
        """Return the display title of the session's active plan if one exists."""
        if not self.session.active_plan_id:
            return None
        try:
            ws_mgr = get_workspace_manager()
            artifacts_dir = ws_mgr.get_session_artifacts_dir(self.session.agent_id, self.session.id)
            _, title = PlanBuilder.read_plan(artifacts_dir, self.session.active_plan_id)
            return title
        except Exception:
            return "Plan"

    def get_active_tools_for_request(
        self,
        request_tools: Sequence[Any],
        thread: Thread | None = None,
    ) -> list[Any]:
        """Filter bound tools dynamically for the current mode, phase, and active plan state."""
        if self._pending_phase_transition is not None:
            return []
        target_thread = thread or self.session.get_open_thread()
        has_active_plan = bool(self.session.active_plan_id)
        allowed_harness = resolve_available_harness_tools(
            target_thread.mode,
            target_thread.phase,
            has_active_plan=has_active_plan,
        )
        filtered: list[Any] = []
        for tool_obj in request_tools:
            t_name = getattr(tool_obj, "name", None) or (
                tool_obj.get("name") if isinstance(tool_obj, dict) else None
            )
            if isinstance(t_name, str) and t_name in ALL_HARNESS_TOOLS:
                if t_name in allowed_harness:
                    filtered.append(tool_obj)
            else:
                filtered.append(tool_obj)
        return filtered

    def _provide_messages_for_request(self, request: Any) -> list[Any] | None:
        """Supply a synthetic trigger HumanMessage when auto-waking a fresh phase thread."""
        msgs = getattr(request, "messages", None)
        if not msgs:
            open_thread = self.session.get_open_thread()
            return [
                HumanMessage(
                    content=(
                        f"Begin execution for mode '{open_thread.mode}'"
                        + (f" phase '{open_thread.phase}'." if open_thread.phase else ".")
                    )
                )
            ]
        return None

    def sync_sandbox_mounts(self, thread: Thread | None = None) -> None:
        """Synchronize sandbox volume mount permissions with the active thread's mode/phase."""
        if self._sandbox_backend is None:
            return
        target_thread = thread or self.session.get_open_thread()
        policy = resolve_mount_policy(target_thread.mode, target_thread.phase)
        self._sandbox_backend.reconfigure_mounts(
            workspace_readonly=policy.workspace_readonly,
            notes_mounted=policy.notes_mounted,
            notes_readonly=policy.notes_readonly,
        )

    def build_effective_system_prompt(
        self,
        include_dynamic_context: bool = True,
        thread: Thread | None = None,
    ) -> str:
        """Dynamically assemble the effective LM-XML system prompt for the session."""
        sandbox_settings = get_sandbox_settings()
        custom_prompt = (self.session.config.system_prompt or "").strip()
        target_thread = thread or (
            self.session.get_open_thread()
            if self.session.is_active or self.session.threads
            else None
        )
        mode = target_thread.mode if target_thread else ModeName.CHAT.value
        phase = target_thread.phase if target_thread else None
        return build_effective_system_prompt(
            workdir=sandbox_settings.workdir,
            custom_prompt=custom_prompt or None,
            session_id=str(self.session.id),
            agent_id=str(self.session.agent_id),
            include_dynamic_context=include_dynamic_context,
            mode=mode,
            phase=phase,
            active_plan_id=self.session.active_plan_id,
            active_plan_title=self._get_active_plan_title(),
        )

    @property
    def sandbox_system_prompt(self) -> str:
        """Return the base OpenSandbox scaffolding system prompt."""
        sandbox_settings = get_sandbox_settings()
        open_thread = self.session.get_open_thread()
        return build_scaffold_prompt(
            sandbox_settings.workdir,
            mode=open_thread.mode,
            phase=open_thread.phase,
            active_plan_id=self.session.active_plan_id,
            active_plan_title=self._get_active_plan_title(),
        )

    @property
    def effective_system_prompt(self) -> str:
        """Return the composite effective system prompt passed to the agent."""
        return self.build_effective_system_prompt()

    @property
    def agent(self) -> LangGraphAgent:
        """Return the underlying LangGraphAgent instance."""
        return self._agent

    def reload_config(self, session: Session | None = None) -> None:
        """Recompile agent graph with updated session config while preserving SSE and state."""
        if session is not None:
            self.session = session
        self._agent = self._build_deep_agent()

    def is_awaiting_user(self) -> bool:
        """Check if the session's active thread is currently awaiting user input."""
        if not self.session.is_active:
            return False
        thread = self.session.get_open_thread()
        return thread.status == AgentStatus.AWAITING_USER and (
            self._active_task is None or self._active_task.done()
        )

    def kill(self) -> None:
        """Manually terminate the runner task and transition session to KILLED."""
        was_running = self._active_task is not None and not self._active_task.done()
        if self._active_task is not None and not self._active_task.done():
            self._active_task.cancel()
        if self._sandbox_backend is not None:
            self._sandbox_backend.destroy()

        try:
            thread = self.session.get_open_thread()
            started_tids: set[str] = set()
            finished_tids: set[str] = set()
            for ev in thread.events:
                ev_type = getattr(ev, "type", None) or (
                    ev.get("type") if isinstance(ev, dict) else None
                )
                tid = getattr(ev, "tool_call_id", None) or (
                    ev.get("tool_call_id") if isinstance(ev, dict) else None
                )
                if tid:
                    if ev_type in ("TOOL_CALL_START", "TOOL_CALL_ARGS", "TOOL_CALL_END"):
                        started_tids.add(str(tid))
                    elif ev_type in ("TOOL_CALL_RESULT", "tool_call_result"):
                        finished_tids.add(str(tid))

            pending_tids = started_tids - finished_tids
            if pending_tids or thread.status == AgentStatus.EXECUTING_TOOL:
                if not pending_tids:
                    pending_tids = {"interrupted"}
                for tid in sorted(pending_tids):
                    interrupted_res = {
                        "type": "TOOL_CALL_RESULT",
                        "tool_call_id": tid,
                        "content": "Execution interrupted: session was killed.",
                        "role": "tool",
                        "is_error": True,
                    }
                    thread.append_event(interrupted_res)
                    self.broadcaster.broadcast_sync(interrupted_res)

            is_active_turn = thread.status in (
                AgentStatus.AWAITING_LLM,
                AgentStatus.EXECUTING_TOOL,
            )
            if was_running or is_active_turn:
                err_event = {
                    "type": "RUN_ERROR",
                    "message": "Session was killed mid-execution.",
                }
                thread.append_event(err_event)
                self.broadcaster.broadcast_sync(err_event)

            thread.status = AgentStatus.ERROR
            thread.touch()
            try:
                ws_mgr = get_workspace_manager()
                ws_mgr.save_thread_events(
                    self.session.agent_id, self.session.id, thread.id, thread.events
                )
            except Exception:
                pass
        except Exception:
            logger.exception("Error cleaning up interrupted tool calls on kill")

        self.session.kill()

    async def resume_turn(self, thread: Thread | None = None) -> None:
        """Resume execution in an existing thread without adding a new user message.

        Used when branching after tool calls to retry/generate LLM inference from
        existing tool results in the checkpointer state.
        """
        async with self._lock:
            if not self.session.is_active:
                msg = f"Session '{self.session.id}' is not active."
                raise SessionBusyError(msg)
            target_thread = thread or self.session.get_open_thread()
            target_thread.status = AgentStatus.AWAITING_LLM
            target_thread.touch()
            self.session.touch()

            self._active_task = asyncio.create_task(
                self._run_loop(target_thread, user_message=None)
            )

    def handle_ask(
        self,
        question: str,
        answers: list[str],
        multiple: bool = False,
        writein: bool = False,
        id: str | None = None,
    ) -> str:
        """Handle execution of the 'ask' tool during an inference turn."""
        item = QuestionItem(
            question=question,
            answers=answers,
            multiple=multiple,
            writein=writein,
            id=id or "",
        )
        if any(q.id == item.id for q in self._pending_questions):
            raise ValueError(
                f"Question with id '{item.id}' already exists in the current questionnaire. "
                f"Each question in a questionnaire must have a unique id."
            )
        if self._current_questionnaire_id is None:
            self._current_questionnaire_id = uuid4().hex
        self._turn_created_artifact_ids.add(self._current_questionnaire_id)
        self._pending_questions.append(item)

        ws_mgr = get_workspace_manager()
        artifacts_dir = ws_mgr.get_session_artifacts_dir(self.session.agent_id, self.session.id)
        target_dir = artifacts_dir / "questionnaires" / self._current_questionnaire_id
        target_dir.mkdir(parents=True, exist_ok=True)

        card_dict = QuestionnaireBuilder.build_card(self._pending_questions)
        (target_dir / "card.json").write_text(json.dumps(card_dict, indent=2), encoding="utf-8")

        art_event = {
            "type": "ARTIFACT_CREATED",
            "artifact_id": self._current_questionnaire_id,
            "kind": "questionnaires",
        }
        self.broadcaster.broadcast_sync(art_event)
        thread = self.session.get_open_thread()
        if thread is not None:
            thread.append_event(art_event)
        return "OK"

    def handle_form(
        self,
        question: str,
        answers: list[str],
        multiple: bool = False,
        writein: bool = False,
        id: str | None = None,
        title: str = "Form",
    ) -> str:
        """Handle execution of the 'form' tool (tabbed, non-blocking questionnaire) in Discuss."""
        item = QuestionItem(
            question=question,
            answers=answers,
            multiple=multiple,
            writein=writein,
            id=id or "",
        )
        if any(q.id == item.id for q in self._pending_form_questions):
            raise ValueError(
                f"Question with id '{item.id}' already exists in the current form. "
                f"Each question in a form must have a unique id."
            )
        if self._current_form_id is None:
            self._current_form_id = uuid4().hex
            self._current_form_title = title.strip() or "Form"
        elif title and title.strip() and title.strip() != "Form":
            self._current_form_title = title.strip()

        self._turn_created_artifact_ids.add(self._current_form_id)
        self._pending_form_questions.append(item)

        ws_mgr = get_workspace_manager()
        artifacts_dir = ws_mgr.get_session_artifacts_dir(self.session.agent_id, self.session.id)
        seed_default_artifacts(artifacts_dir)
        target_dir = artifacts_dir / "forms" / self._current_form_id
        target_dir.mkdir(parents=True, exist_ok=True)

        manifest_payload = {
            "exposition": "tabbed",
            "cadence": "nonblocking",
            "title": self._current_form_title,
        }
        (target_dir / "manifest.json").write_text(
            json.dumps(manifest_payload, indent=2),
            encoding="utf-8",
        )
        card_dict = QuestionnaireBuilder.build_card(
            self._pending_form_questions,
            title=self._current_form_title,
        )
        (target_dir / "card.json").write_text(
            json.dumps(card_dict, indent=2),
            encoding="utf-8",
        )

        art_event = {
            "type": "ARTIFACT_CREATED",
            "artifact_id": self._current_form_id,
            "kind": "forms",
            "title": self._current_form_title,
        }
        self.broadcaster.broadcast_sync(art_event)
        thread = self.session.get_open_thread()
        if thread is not None:
            thread.append_event(art_event)
        return "OK"

    def handle_plan(self) -> str:
        """Transition from Plan/Discuss to Plan/Make in a new thread and auto-wake."""
        open_thread = self.session.get_open_thread()
        if open_thread.mode != ModeName.PLAN.value or open_thread.phase != PlanPhase.DISCUSS.value:
            raise ValueError("The 'plan' tool can only be called during the Plan/Discuss phase.")
        self._pending_phase_transition = (ModeName.PLAN.value, PlanPhase.MAKE.value, True)
        return "Transitioning session to Plan/Make phase in a new thread."

    def handle_make_plan(self, content: str, name: str = "Plan") -> str:
        """Create the session-local Plan artifact in Plan/Make phase."""
        open_thread = self.session.get_open_thread()
        if open_thread.mode != ModeName.PLAN.value or open_thread.phase != PlanPhase.MAKE.value:
            raise ValueError("make_plan is only available in the Plan/Make phase.")

        ws_mgr = get_workspace_manager()
        artifacts_dir = ws_mgr.get_session_artifacts_dir(self.session.agent_id, self.session.id)
        resolver = ArtifactResolver(artifacts_dir)

        if self.session.active_plan_id and not resolver.is_closed(
            "plans", self.session.active_plan_id
        ):
            raise ValueError(
                f"Active plan '{self.session.active_plan_id}' already exists for this session. "
                "Use update_plan or edit_plan to modify it."
            )

        plan_id = uuid4().hex
        clean_title = name.strip() or "Plan"
        PlanBuilder.create_plan(artifacts_dir, plan_id, content, title=clean_title)
        self.session.active_plan_id = plan_id
        self.session.touch()
        self._turn_created_artifact_ids.add(plan_id)

        art_event = {
            "type": "ARTIFACT_CREATED",
            "artifact_id": plan_id,
            "kind": "plans",
            "title": clean_title,
        }
        self.broadcaster.broadcast_sync(art_event)
        open_thread.append_event(art_event)
        return f"Created plan '{clean_title}' (id={plan_id})."

    def handle_update_plan(self, content: str) -> str:
        """Overwrite the full Markdown content of the active session plan in Plan/Make phase."""
        open_thread = self.session.get_open_thread()
        if open_thread.mode != ModeName.PLAN.value or open_thread.phase != PlanPhase.MAKE.value:
            raise ValueError("update_plan is only available in the Plan/Make phase.")
        if not self.session.active_plan_id:
            raise ValueError("No active plan exists in this session. Call make_plan first.")

        ws_mgr = get_workspace_manager()
        artifacts_dir = ws_mgr.get_session_artifacts_dir(self.session.agent_id, self.session.id)
        plan_id = self.session.active_plan_id
        PlanBuilder.update_plan(artifacts_dir, plan_id, content)
        self.session.touch()

        upd_event = {
            "type": "ARTIFACT_UPDATED",
            "artifact_id": plan_id,
            "kind": "plans",
        }
        self.broadcaster.broadcast_sync(upd_event)
        open_thread.append_event(upd_event)
        return f"Updated plan (id={plan_id})."

    def handle_edit_plan(self, old_string: str, new_string: str) -> str:
        """Perform an exact string replacement on the active session plan in Plan/Make phase."""
        open_thread = self.session.get_open_thread()
        if open_thread.mode != ModeName.PLAN.value or open_thread.phase != PlanPhase.MAKE.value:
            raise ValueError("edit_plan is only available in the Plan/Make phase.")
        if not self.session.active_plan_id:
            raise ValueError("No active plan exists in this session. Call make_plan first.")

        ws_mgr = get_workspace_manager()
        artifacts_dir = ws_mgr.get_session_artifacts_dir(self.session.agent_id, self.session.id)
        plan_id = self.session.active_plan_id
        PlanBuilder.edit_plan(artifacts_dir, plan_id, old_string, new_string)
        self.session.touch()

        upd_event = {
            "type": "ARTIFACT_UPDATED",
            "artifact_id": plan_id,
            "kind": "plans",
        }
        self.broadcaster.broadcast_sync(upd_event)
        open_thread.append_event(upd_event)
        return f"Edited plan (id={plan_id})."

    def close_active_plan(self) -> str | None:
        """Close the active session plan artifact if present and clear session.active_plan_id."""
        plan_id = self.session.active_plan_id
        if not plan_id:
            return None
        ws_mgr = get_workspace_manager()
        artifacts_dir = ws_mgr.get_session_artifacts_dir(self.session.agent_id, self.session.id)
        PlanBuilder.close_plan(artifacts_dir, plan_id)
        self.session.active_plan_id = None
        self.session.touch()
        close_event = {
            "type": "ARTIFACT_CLOSED",
            "artifact_id": plan_id,
            "kind": "plans",
        }
        self.broadcaster.broadcast_sync(close_event)
        return plan_id

    def handle_discard(self) -> str:
        """Discard any active session plan and open a new thread back in Plan/Discuss."""
        open_thread = self.session.get_open_thread()
        if open_thread.mode != ModeName.PLAN.value:
            raise ValueError("discard is only available in Plan mode.")

        closed_plan_id = self.close_active_plan()
        if closed_plan_id:
            open_thread.append_event(
                {
                    "type": "ARTIFACT_CLOSED",
                    "artifact_id": closed_plan_id,
                    "kind": "plans",
                }
            )

        # Also close any open forms or questionnaires in the session
        ws_mgr = get_workspace_manager()
        artifacts_dir = ws_mgr.get_session_artifacts_dir(self.session.agent_id, self.session.id)
        resolver = ArtifactResolver(artifacts_dir)
        for art in resolver.list_artifacts():
            if not art.is_closed:
                del_file = artifacts_dir / art.kind / art.name / "closed.json"
                del_file.write_text(
                    json.dumps({"closed": True}, indent=2),
                    encoding="utf-8",
                )
                close_ev = {
                    "type": "ARTIFACT_CLOSED",
                    "artifact_id": art.name,
                    "kind": art.kind,
                }
                self.broadcaster.broadcast_sync(close_ev)
                open_thread.append_event(close_ev)

        self._pending_phase_transition = (ModeName.PLAN.value, PlanPhase.DISCUSS.value, False)
        return "Discarded active plan and resetting session to a new Plan/Discuss thread."

    async def transition_to_phase(
        self,
        mode: str,
        phase: str | None = None,
        *,
        auto_wake: bool = False,
    ) -> Thread:
        """Close the current thread, open a new thread in (mode, phase), and auto-wake if set."""
        resolved_mode, resolved_phase = normalize_mode_and_phase(mode, phase)
        new_thread = self.session.create_thread(mode=resolved_mode, phase=resolved_phase)
        if auto_wake:
            new_thread.status = AgentStatus.AWAITING_LLM
        self.sync_sandbox_mounts(new_thread)

        try:
            ws_mgr = get_workspace_manager()
            ws_mgr.save_thread_events(
                self.session.agent_id, self.session.id, new_thread.id, new_thread.events
            )
            ws_mgr.commit_state_changes(self.session.agent_id, self.session.id, new_thread.id)
            ws_mgr.commit_session_config(self.session)
        except Exception:
            logger.exception("Failed to persist thread transition for session %s", self.session.id)

        transition_event = {
            "type": "THREAD_TRANSITION",
            "thread_id": str(new_thread.id),
            "mode": new_thread.mode,
            "phase": new_thread.phase,
            "mode_label": new_thread.mode_label,
            "active_plan_id": self.session.active_plan_id,
            "auto_wake": auto_wake,
        }
        await self.broadcaster.broadcast(transition_event)

        if auto_wake:
            self._active_task = asyncio.create_task(
                self._run_loop(thread=new_thread, user_message=None)
            )
        return new_thread

    def handle_read_artifact_submission(self, artifact_id: str) -> str:
        """Read the canonical user submission for a questionnaire, form, or plan artifact.

        If called for an open non-blocking artifact (cadence=nonblocking),
        that artifact instance is promoted to cadence=blocking.
        """
        is_same_turn = (
            artifact_id in self._turn_created_artifact_ids
            or (
                self._current_questionnaire_id is not None
                and (artifact_id == self._current_questionnaire_id or not artifact_id)
            )
            or (
                self._current_form_id is not None
                and (artifact_id == self._current_form_id or not artifact_id)
            )
            or any(q.id == artifact_id for q in self._pending_questions if q.id)
            or any(q.id == artifact_id for q in self._pending_form_questions if q.id)
        )
        if is_same_turn:
            msg = (
                f"Cannot read artifact submission for questionnaire '{artifact_id}' in the same "
                f"turn it was created with 'ask' or 'form'. The artifact must first be submitted "
                f"by the user in a subsequent turn."
            )
            raise ValueError(msg)

        ws_mgr = get_workspace_manager()
        artifacts_dir = ws_mgr.get_session_artifacts_dir(self.session.agent_id, self.session.id)
        resolver = ArtifactResolver(artifacts_dir)

        matched_kind = "questionnaires"
        for candidate_kind in ("questionnaires", "forms", "plans"):
            if (artifacts_dir / candidate_kind / artifact_id).is_dir():
                matched_kind = candidate_kind
                break

        # If open and nonblocking, promote instance manifest to blocking
        inst_dir = artifacts_dir / matched_kind / artifact_id
        if inst_dir.is_dir() and not resolver.is_closed(matched_kind, artifact_id):
            try:
                manifest = resolver.load_manifest(matched_kind, artifact_id)
                if manifest.cadence == CadenceMode.NONBLOCKING:
                    promoted = manifest.model_copy(update={"cadence": CadenceMode.BLOCKING})
                    (inst_dir / "manifest.json").write_text(
                        promoted.model_dump_json(indent=2, exclude_none=True),
                        encoding="utf-8",
                    )
                    self.broadcaster.broadcast_sync(
                        {
                            "type": "ARTIFACT_UPDATED",
                            "artifact_id": artifact_id,
                            "kind": matched_kind,
                        }
                    )
            except Exception:
                logger.exception(
                    "Failed to promote artifact %s/%s to blocking",
                    matched_kind,
                    artifact_id,
                )

        data_path = resolver.resolve_file(matched_kind, artifact_id, "submission.json")
        if not data_path or not data_path.is_file():
            legacy_path = resolver.resolve_file(matched_kind, artifact_id, "updateDataModel.json")
            if legacy_path and legacy_path.is_file():
                try:
                    loaded = json.loads(legacy_path.read_text(encoding="utf-8"))
                    data_val = loaded.get("updateDataModel", {}).get("value", loaded)
                    return json.dumps({"data": data_val})
                except Exception:
                    pass
            return json.dumps({"data": {}, "status": "pending"})
        try:
            loaded = json.loads(data_path.read_text(encoding="utf-8"))
            return json.dumps({"data": loaded})
        except Exception as exc:
            return json.dumps({"error": str(exc), "data": {}})

    def has_open_blocking_artifact(self) -> bool:
        """Check if the session currently has any open artifact with cadence=blocking."""
        try:
            ws_mgr = get_workspace_manager()
            artifacts_dir = ws_mgr.get_session_artifacts_dir(self.session.agent_id, self.session.id)
            resolver = ArtifactResolver(artifacts_dir)
            return resolver.has_open_blocking_artifact()
        except Exception:
            return False

    async def dispatch_artifact_submission(
        self,
        kind: str,
        name: str,
        data: dict[str, Any],
    ) -> str:
        """Process artifact submission, persist data, and resume agent with synthetic tool call."""
        async with self._lock:
            if not self.session.is_active:
                msg = (
                    f"Session '{self.session.id}' is not active "
                    f"(current status: {self.session.status.value})."
                )
                raise SessionBusyError(msg)

            ws_mgr = get_workspace_manager()
            artifacts_dir = ws_mgr.get_session_artifacts_dir(self.session.agent_id, self.session.id)
            target_dir = artifacts_dir / kind / name
            if not target_dir.is_dir():
                msg = f"Artifact '{kind}/{name}' does not exist."
                raise ValueError(msg)

            resolver = ArtifactResolver(artifacts_dir)
            if resolver.is_closed(kind, name):
                msg = f"Artifact '{kind}/{name}' is already closed."
                raise ValueError(msg)

            thread = self.session.get_open_thread()

            if kind == "plans":
                # User clicked Proceed on the Plan tab -> approve plan and transition to Execute
                PlanBuilder.approve_plan(artifacts_dir, name)
                self.session.active_plan_id = name
                art_sub = {
                    "type": "ARTIFACT_SUBMITTED",
                    "kind": kind,
                    "name": name,
                }
                art_upd = {
                    "type": "ARTIFACT_UPDATED",
                    "artifact_id": name,
                    "kind": "plans",
                }
                thread.append_event(art_sub)
                thread.append_event(art_upd)
                await self.broadcaster.broadcast(art_sub)
                await self.broadcaster.broadcast(art_upd)

                try:
                    ws_mgr.save_thread_events(
                        self.session.agent_id, self.session.id, thread.id, thread.events
                    )
                    ws_mgr.commit_checkpoint_changes(
                        self.session.agent_id, self.session.id, thread.id
                    )
                except Exception:
                    logger.exception("Failed to save thread events on plan approval")

                await self.transition_to_phase(
                    ModeName.PLAN.value,
                    PlanPhase.EXECUTE.value,
                    auto_wake=True,
                )
                return f"proceed_{name}"

            # 1. Write submission.json
            (target_dir / "submission.json").write_text(
                json.dumps(data, indent=2), encoding="utf-8"
            )

            # 2. Write closed.json to mark it closed
            (target_dir / "closed.json").write_text(
                json.dumps({"closed": True}, indent=2), encoding="utf-8"
            )

            # 3. Create synthetic tool call
            call_id = f"call_{uuid4().hex[:12]}"
            submission_payload = {"data": data}

            art_sub = {
                "type": "ARTIFACT_SUBMITTED",
                "kind": kind,
                "name": name,
            }
            art_closed = {
                "type": "ARTIFACT_CLOSED",
                "artifact_id": name,
                "kind": kind,
            }
            thread.append_event(art_sub)
            thread.append_event(art_closed)
            await self.broadcaster.broadcast(art_sub)
            await self.broadcaster.broadcast(art_closed)

            tc_start = {
                "type": "TOOL_CALL_START",
                "tool_call_id": call_id,
                "tool_call_name": "read_artifact_submission",
            }
            tc_args = {
                "type": "TOOL_CALL_ARGS",
                "tool_call_id": call_id,
                "args": {"artifact_id": name},
            }
            tc_end = {
                "type": "TOOL_CALL_END",
                "tool_call_id": call_id,
            }
            tc_result = {
                "type": "TOOL_CALL_RESULT",
                "tool_call_id": call_id,
                "content": json.dumps(submission_payload),
                "role": "tool",
            }

            thread.append_event(tc_start)
            thread.append_event(tc_args)
            thread.append_event(tc_end)
            thread.append_event(tc_result)

            await self.broadcaster.broadcast(tc_start)
            await self.broadcaster.broadcast(tc_args)
            await self.broadcaster.broadcast(tc_end)
            await self.broadcaster.broadcast(tc_result)

            # 4. Inject into checkpointer state for thread
            ai_msg = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "read_artifact_submission",
                        "args": {"artifact_id": name},
                        "id": call_id,
                    }
                ],
            )
            tool_msg = ToolMessage(
                content=json.dumps(submission_payload),
                tool_call_id=call_id,
                name="read_artifact_submission",
            )

            try:
                self._agent.graph.update_state(
                    {"configurable": {"thread_id": thread.id.hex}},
                    {"messages": [ai_msg, tool_msg]},
                    as_node="tools",
                )
            except Exception:
                logger.exception("Failed to update graph state with synthetic tool messages")

            thread.status = AgentStatus.AWAITING_LLM
            thread.touch()
            self.session.touch()

            try:
                ws_mgr.save_thread_events(
                    self.session.agent_id, self.session.id, thread.id, thread.events
                )
                ws_mgr.commit_checkpoint_changes(self.session.agent_id, self.session.id, thread.id)
            except Exception:
                logger.exception("Failed to save thread events or commit state on submission")

            # 5. Start background execution turn to resume agent
            self._active_task = asyncio.create_task(
                self._run_loop(thread=thread, user_message=None)
            )

            return call_id

    async def dispatch_user_input(
        self,
        text: str,
        message_id: str | None = None,
    ) -> str:
        """Dispatch a user message to the active thread and start execution."""
        async with self._lock:
            if not self.session.is_active:
                msg = (
                    f"Session '{self.session.id}' is not active "
                    f"(current status: {self.session.status.value})."
                )
                raise SessionBusyError(msg)

            if self.has_open_blocking_artifact():
                msg = (
                    f"Session '{self.session.id}' has an open blocking questionnaire. "
                    "User must submit the questionnaire before sending messages."
                )
                raise SessionBusyError(msg)

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

            try:
                ws_mgr = get_workspace_manager()
                ws_mgr.save_thread_events(
                    self.session.agent_id, self.session.id, thread.id, thread.events
                )
            except Exception:
                logger.exception("Failed to save thread events on user input dispatch")

            logfire.info(
                "Dispatched user input to thread {thread_id} in session {session_id}",
                thread_id=str(thread.id),
                session_id=str(self.session.id),
                message_id=user_msg_id,
            )

            # Start execution task in the background
            self._active_task = asyncio.create_task(
                self._run_loop(thread=thread, user_message=user_msg)
            )

            return user_msg_id

    async def _run_loop(self, thread: Thread, user_message: UserMessage | None = None) -> None:
        """Internal execution loop with hierarchical agent, session, and thread spans."""
        agent_entity = self._resolve_agent_entity()
        agent_id_str = str(self.session.agent_id)
        agent_name = agent_entity.name if agent_entity else None
        agent_identifier = agent_name or agent_id_str

        session_id_str = str(self.session.id)
        session_name = self.session.name
        session_identifier = session_name or session_id_str

        thread_id_str = str(thread.id)
        thread_name = thread.name
        thread_identifier = thread_name or thread_id_str

        run_id = uuid4().hex
        self._pending_questions = []
        self._current_questionnaire_id = None
        self._pending_form_questions = []
        self._current_form_id = None
        self._current_form_title = "Form"
        self._turn_created_artifact_ids.clear()
        self._pending_phase_transition = None
        self.sync_sandbox_mounts(thread)
        input_data = RunAgentInput(
            thread_id=thread.id.hex,
            run_id=run_id,
            messages=[user_message] if user_message is not None else [],
        )

        ws_mgr = get_workspace_manager()
        ws_mgr.sync_session_workspace(self.session)

        request_agent = self._agent.clone()
        with logfire.span(
            f"agent {agent_identifier}",
            agent_id=agent_id_str,
            agent_name=agent_name,
            agent_identifier=agent_identifier,
            model=self.session.config.model_name,
        ):
            with logfire.span(
                f"session {session_identifier}",
                session_id=session_id_str,
                session_name=session_name,
                session_identifier=session_identifier,
                agent_id=agent_id_str,
            ):
                with logfire.span(
                    f"thread {thread_identifier}",
                    thread_id=thread_id_str,
                    thread_name=thread_name,
                    thread_identifier=thread_identifier,
                    session_id=session_id_str,
                    agent_id=agent_id_str,
                    run_id=run_id,
                ):
                    try:
                        async for event in request_agent.run(input_data):
                            self._update_status_from_event(thread, event)
                            thread.append_event(event)
                            await self.broadcaster.broadcast(event)
                    except Exception as exc:
                        logger.exception("Error during session agent execution")
                        logfire.error(
                            "Session execution failed in thread {thread}: {error}",
                            thread=thread_identifier,
                            error=str(exc),
                        )
                        err_event = {
                            "type": "RUN_ERROR",
                            "message": str(exc) or type(exc).__name__,
                            "error_type": type(exc).__name__,
                            "traceback": traceback.format_exc(),
                        }
                        thread.append_event(err_event)
                        self.session.fail()
                        if self._sandbox_backend is not None:
                            self._sandbox_backend.destroy()
                        await self.broadcaster.broadcast(err_event)
                        try:
                            ws_mgr = get_workspace_manager()
                            agent_entity = self._resolve_agent_entity()
                            if agent_entity is not None:
                                ws_mgr.close_sync_pr(self.session, agent_entity)
                        except Exception:
                            logger.exception("Failed to close Sync PR on session failure")
                    finally:
                        pending_transition = self._pending_phase_transition
                        self._pending_phase_transition = None
                        self._pending_questions = []
                        self._current_questionnaire_id = None
                        self._pending_form_questions = []
                        self._current_form_id = None
                        self._current_form_title = "Form"
                        self._turn_created_artifact_ids.clear()
                        if thread.status != AgentStatus.ERROR and self.session.is_active:
                            thread.status = AgentStatus.AWAITING_USER
                        thread.touch()
                        self.session.touch()
                        try:
                            ws_mgr = get_workspace_manager()
                            ws_mgr.save_thread_events(
                                self.session.agent_id, self.session.id, thread.id, thread.events
                            )
                            ws_mgr.commit_state_changes(
                                self.session.agent_id, self.session.id, thread.id
                            )
                            ws_mgr.commit_session_config(self.session)
                        except Exception:
                            logger.exception(
                                "Failed to commit state changes on turn completion "
                                "for session %s thread %s",
                                self.session.id,
                                thread.id,
                            )
                        if (
                            pending_transition is not None
                            and thread.status != AgentStatus.ERROR
                            and self.session.is_active
                        ):
                            t_mode, t_phase, t_auto_wake = pending_transition
                            await self.transition_to_phase(
                                t_mode,
                                t_phase,
                                auto_wake=t_auto_wake,
                            )

    def _update_status_from_event(self, thread: Thread, event: Any) -> None:
        """Update thread status based on AG-UI event type."""
        event_type = getattr(event, "type", None)
        if event_type == EventType.RUN_STARTED:
            thread.status = AgentStatus.AWAITING_LLM
        elif event_type in (
            EventType.TOOL_CALL_START,
            EventType.TOOL_CALL_ARGS,
            EventType.TOOL_CALL_CHUNK,
            EventType.TOOL_CALL_END,
        ):
            thread.status = AgentStatus.EXECUTING_TOOL
        elif event_type in (
            EventType.TOOL_CALL_RESULT,
            EventType.TEXT_MESSAGE_START,
            EventType.TEXT_MESSAGE_CHUNK,
            EventType.TEXT_MESSAGE_CONTENT,
            EventType.TEXT_MESSAGE_END,
            EventType.REASONING_START,
            EventType.REASONING_MESSAGE_START,
            EventType.REASONING_MESSAGE_CONTENT,
            EventType.REASONING_MESSAGE_CHUNK,
            EventType.REASONING_MESSAGE_END,
            EventType.REASONING_END,
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
            while not queue.empty():
                event = queue.get_nowait()
                yield self._format_sse_event(encoder, event)
        finally:
            self.broadcaster.unsubscribe(queue)


class RunnerRegistry:
    """Maintains active SessionAgentRunner instances keyed by session ID."""

    def __init__(self) -> None:
        self._runners: dict[str, SessionAgentRunner] = {}

    def get_runner(self, session: Session, agent: Agent | None = None) -> SessionAgentRunner:
        """Get or create the SessionAgentRunner for a session."""
        session_key = str(session.id)
        if session_key not in self._runners:
            self._runners[session_key] = SessionAgentRunner(session=session, agent_entity=agent)
        elif agent is not None and self._runners[session_key]._agent_entity is None:
            self._runners[session_key]._agent_entity = agent
        return self._runners[session_key]

    def get_or_create(self, session: Session, agent: Agent | None = None) -> SessionAgentRunner:
        """Alias for get_runner."""
        return self.get_runner(session, agent)

    def set_runner(self, session_id: str, runner: SessionAgentRunner) -> None:
        """Register a specific runner instance (useful for testing with mock agents)."""
        self._runners[session_id] = runner

    def reload_session_runner(self, session: Session) -> None:
        """Reload the SessionAgentRunner for a session if currently cached."""
        session_key = str(session.id)
        if session_key in self._runners:
            self._runners[session_key].reload_config(session)


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
