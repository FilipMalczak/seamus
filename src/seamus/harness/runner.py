"""Session agent execution runner, DeepAgent lifecycle, and AG-UI event broadcasting."""

import asyncio
import json
import logging
import os
import traceback
import urllib.error
import urllib.request
from collections.abc import AsyncGenerator, Mapping, Sequence
from typing import Any, Literal, cast
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
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.outputs import ChatGenerationChunk, ChatResult
from langchain_core.tools import StructuredTool
from langchain_openai import ChatOpenAI
from langgraph.types import Command
from pydantic import BaseModel, Field, SecretStr, model_validator

from seamus.config.models import (
    InferenceFormat,
    ReasoningEffort,
    SkillsImplementation,
    TodoImplementation,
    WebSearchImplementation,
)
from seamus.config.settings import get_system_settings_store
from seamus.domain.artifacts import (
    SYNTHETIC_MESSAGE_INDICATOR,
    ArtifactManifest,
    ClickResult,
)
from seamus.domain.entities import Agent, AgentStatus, Session, SessionStatus, Thread
from seamus.domain.modes import (
    ALL_HARNESS_TOOLS,
    ModeName,
    PlanPhase,
    normalize_mode_and_phase,
    resolve_available_harness_tools,
    resolve_mount_policy,
)
from seamus.harness.artifacts import (
    ArtifactBuilder,
    ArtifactResolver,
    FormBuilder,
    PlanBuilder,
    Question,
    QuestionItem,
    QuestionnaireBuilder,
    auto_declare_manifest_buttons,
    check_a2ui_surface_warnings,
    dispatch_button_click,
    normalize_a2ui_components,
    seed_default_artifacts,
    validate_a2ui_surface,
)
from seamus.harness.prompt import (
    ActiveSkillPromptItem,
    AvailableSkillPromptItem,
    DynamicSystemPromptMiddleware,
    SkillsPromptDocument,
    build_effective_system_prompt,
    build_scaffold_prompt,
    discover_context_files,
)
from seamus.harness.sandbox import (
    SeamusOpenSandboxBackend,
    get_sandbox_settings,
)
from seamus.harness.skills import (
    DiscoveredSkill,
    SeamusSkillsMiddleware,
    discover_session_skills,
)
from seamus.harness.todos import (
    SeamusTodoMiddleware,
    render_plan_text,
)
from seamus.harness.web_search import (
    WEB_SEARCH_TOOL_NAMES,
    get_web_search_tools,
)
from seamus.persistence import (
    GitCheckpointSaver,
    calculate_mount_paths,
    get_external_repo_manager,
    get_workspace_manager,
)
from seamus.vault import (
    collect_secret_references,
    get_default_vault_client,
    resolve_secrets_with_versions,
    resolve_secrets_with_versions_sync,
)

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


def _ensure_ollama_model(base_url: str, model_name: str) -> str:
    """Perform healthcheck on Ollama and ensure model is running / loaded into memory.

    Returns the effective base URL (auto-resolving localhost to host.docker.internal
    if running inside a container and localhost refuses connection).
    Returns the effective base URL (auto-resolving localhost to internal docker
    service 'ollama' or 'host.docker.internal' if running in a container).
    """
    candidates = [base_url]
    parsed_base = base_url.strip().rstrip("/")
    if "localhost" in parsed_base or "127.0.0.1" in parsed_base:
        docker_service_url = parsed_base.replace("localhost", "ollama").replace(
            "127.0.0.1", "ollama"
        )
        if docker_service_url not in candidates:
            candidates.append(docker_service_url)
        docker_host_url = parsed_base.replace("localhost", "host.docker.internal").replace(
            "127.0.0.1", "host.docker.internal"
        )
        if docker_host_url not in candidates:
            candidates.append(docker_host_url)

    last_exc: Exception | None = None
    for cand in candidates:
        ollama_base = cand.strip().rstrip("/").removesuffix("/v1").rstrip("/")
        try:
            req = urllib.request.Request(
                f"{ollama_base}/api/generate",
                data=json.dumps({"model": model_name}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if isinstance(data, dict) and "error" in data:
                    err_msg = str(data["error"])
                    if "not found" in err_msg.lower():
                        # Auto-pull model if missing
                        try:
                            pull_req = urllib.request.Request(
                                f"{ollama_base}/api/pull",
                                data=json.dumps({"model": model_name, "stream": False}).encode(
                                    "utf-8"
                                ),
                                headers={"Content-Type": "application/json"},
                            )
                            with urllib.request.urlopen(pull_req, timeout=600):
                                pass
                            # Retry generate to load model into memory
                            with urllib.request.urlopen(req, timeout=60) as retry_resp:
                                retry_data = json.loads(retry_resp.read().decode("utf-8"))
                                if isinstance(retry_data, dict) and "error" in retry_data:
                                    raise RuntimeError(
                                        f"Failed to run model '{model_name}' on Ollama after pull: "
                                        f"{retry_data['error']}"
                                    )
                                return cand
                        except Exception as pull_exc:
                            raise RuntimeError(
                                f"Failed to pull and run model '{model_name}' on Ollama: {pull_exc}"
                            ) from pull_exc
                    raise RuntimeError(
                        f"Failed to run model '{model_name}' on Ollama: {data['error']}"
                    )
            return cand
        except urllib.error.HTTPError as exc:
            err_msg = ""
            try:
                err_data = json.loads(exc.read().decode("utf-8"))
                if isinstance(err_data, dict):
                    err_msg = str(err_data.get("error", ""))
            except Exception:
                err_msg = str(exc)

            if exc.code == 404 and "not found" in err_msg.lower():
                try:
                    pull_req = urllib.request.Request(
                        f"{ollama_base}/api/pull",
                        data=json.dumps({"model": model_name, "stream": False}).encode("utf-8"),
                        headers={"Content-Type": "application/json"},
                    )
                    with urllib.request.urlopen(pull_req, timeout=600):
                        pass
                    with urllib.request.urlopen(req, timeout=60) as retry_resp:
                        retry_data = json.loads(retry_resp.read().decode("utf-8"))
                        if isinstance(retry_data, dict) and "error" in retry_data:
                            raise RuntimeError(
                                f"Failed to run model '{model_name}' on Ollama after pull: "
                                f"{retry_data['error']}"
                            )
                        return cand
                except Exception as pull_exc:
                    raise RuntimeError(
                        f"Failed to pull and run model '{model_name}' on Ollama: {pull_exc}"
                    ) from pull_exc

            raise RuntimeError(
                f"Failed to run model '{model_name}' on Ollama: {err_msg or exc}"
            ) from exc
        except urllib.error.URLError as exc:
            last_exc = exc
            continue

    ollama_base = base_url.strip().rstrip("/").removesuffix("/v1").rstrip("/")
    raise RuntimeError(
        f"Ollama healthcheck failed at {ollama_base}. "
        f"Ensure Ollama is running in background. If Seamus backend is running inside Docker "
        f"and Ollama is on the host, ensure Ollama is listening on all interfaces "
        f"(set OLLAMA_HOST=0.0.0.0): {last_exc}"
        f"Ensure Ollama is running (e.g. docker-compose 'ollama' service "
        f"or local daemon): {last_exc}"
    ) from last_exc


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


def select_message_overlap(messages: list[Any], max_count: int) -> list[Any]:
    """Select up to max_count trailing messages, ensuring no orphaned tool messages."""
    if not messages or max_count <= 0:
        return []
    window = list(messages[-max_count:])
    while window and (
        getattr(window[0], "type", None) == "tool"
        or getattr(window[0], "role", None) == "tool"
        or type(window[0]).__name__ == "ToolMessage"
    ):
        idx_in_orig = len(messages) - len(window)
        if idx_in_orig > 0:
            window.insert(0, messages[idx_in_orig - 1])
        else:
            window.pop(0)
    return window


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


class MakeArtifactInput(BaseModel):
    """Input schema for make_artifact tool."""

    family: str = Field(
        description=(
            "Artifact family directory under /artifacts/ "
            "(e.g. 'questionnaires', 'forms', 'plans', 'custom')"
        ),
    )
    manifest: dict[str, Any] | ArtifactManifest | str = Field(
        description="Behavioral and exposition manifest for the artifact",
    )
    components: list[dict[str, Any]] | Any = Field(
        description="A2UI basic catalog components sequence for body.json",
    )
    uuid: str | None = Field(
        default=None,
        description="Optional custom UUID for the artifact instance",
    )


class MakeQuestionnaireInput(BaseModel):
    """Input schema for make_questionnaire tool."""

    title: str = Field(
        default="Questionnaire",
        description="Display title for the questionnaire",
    )
    questions: list[Question] = Field(
        description="List of questions (body, answers, multiple_choice)",
    )
    blocking: bool = Field(
        default=True,
        description="Whether user text input is blocked until the questionnaire is submitted",
    )
    exposition: Literal["tabbed", "embedded"] = Field(
        default="embedded",
        description="Whether to expose questionnaire embedded in chat or in a tab",
    )


class MakeFormInput(BaseModel):
    """Input schema for make_form tool."""

    title: str = Field(
        default="Form",
        description="Display title for the form tab",
    )
    fields: list[Question] = Field(
        description="List of fields (body, answers, multiple_choice)",
    )
    blocking: bool = Field(
        default=False,
        description="Whether user text input is blocked until the form is submitted",
    )
    exposition: Literal["tabbed", "embedded"] = Field(
        default="tabbed",
        description="Whether to expose form in a dedicated tab or embedded in chat",
    )


class WaitForClickInput(BaseModel):
    """Input schema for wait_for_click tool."""

    artifact_id: str = Field(description="UUID of the artifact to observe.")
    button_id: str | None = Field(
        default=None,
        description="Optional button ID to filter on; if omitted, resumes on any button click.",
    )
    fresh: bool = Field(
        default=True,
        description="If True, ignores past interactions and suspends until a new click occurs.",
    )
    timeout: float | None = Field(
        default=None,
        description="Optional timeout in seconds to wait before unblocking.",
    )


class PlanTransitionInput(BaseModel):
    """Input schema for the plan() phase transition tool."""

    retained_skills: list[str] = Field(
        default_factory=list,
        description="Optional list of active skill names to retain into the new thread.",
    )


class MakePlanInput(BaseModel):
    """Input schema for the make_plan tool in Plan/Make phase."""

    title: str = Field(
        default="Plan",
        description="Display title for the Plan tab (defaults to 'Plan').",
    )
    steps: list[str] = Field(
        default_factory=list,
        description="List of markdown steps or section texts.",
    )
    content: str | None = Field(
        default=None,
        description="Full markdown plan body (overrides steps if provided).",
    )
    name: str | None = Field(
        default=None,
        description="Optional alias for title.",
    )
    blocking: bool = Field(
        default=False,
        description="Whether user text input is blocked until the plan is approved",
    )
    exposition: Literal["tabbed", "embedded"] = Field(
        default="tabbed",
        description="Exposition mode (defaults to 'tabbed')",
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
        self._turn_created_artifact_ids: set[str] = set()
        self._pending_phase_transition: tuple[str, str | None, bool] | None = None
        self._pending_retained_skills: list[str] | None = None
        self._pending_clicks: dict[tuple[str, str | None], asyncio.Future[str]] = {}
        self._loaded_secret_versions: dict[tuple[str, str], int] = {}
        self._resolved_system_prompt: str | None = None
        self._llm: ReasoningChatOpenAI | None = None

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
        resolved_config, version_map = resolve_secrets_with_versions_sync(self.session.config)
        self._loaded_secret_versions = dict(version_map)
        self.session.secret_versions = {
            f"{k[0]}:{k[1]}": v for k, v in self._loaded_secret_versions.items()
        }
        self._resolved_system_prompt = resolved_config.system_prompt
        api_key = resolved_config.inference.api_key or ""
        base_url = resolved_config.inference.base_url

        if resolved_config.inference.format == InferenceFormat.OLLAMA or "11434" in base_url:
            base_url = _ensure_ollama_model(base_url, resolved_config.model_name)
            if not api_key:
                api_key = "ollama"
            if not base_url.rstrip("/").endswith("/v1"):
                base_url = f"{base_url.rstrip('/')}/v1"

        reasoning_effort = (
            resolved_config.inference.reasoning_effort.value
            if resolved_config.inference.reasoning_effort != ReasoningEffort.DEFAULT
            else None
        )
        llm = ReasoningChatOpenAI(
            model=resolved_config.model_name,
            api_key=SecretStr(api_key),
            base_url=base_url,
            reasoning_effort=reasoning_effort,
        )
        self._llm = llm

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

        ext_mgr = get_external_repo_manager()
        if self.session.config.repositories:
            mount_paths = calculate_mount_paths(self.session.config.repositories)
            for repo_cfg in self.session.config.repositories:
                mount_name = mount_paths.get(repo_cfg.id, "repo")
                try:
                    ext_mgr.provision_session_working_copy(
                        agent_id=self.session.agent_id,
                        session_id=self.session.id,
                        repo_config=repo_cfg,
                        mount_name=mount_name,
                    )
                except Exception:
                    logger.exception(
                        "Failed to provision working copy for %s in session %s",
                        mount_name,
                        self.session.id,
                    )

        open_thread = (
            self.session.get_open_thread()
            if self.session.is_active or self.session.threads
            else None
        )
        mode = open_thread.mode if open_thread else ModeName.CHAT.value
        phase = open_thread.phase if open_thread else None
        mount_policy = resolve_mount_policy(mode, phase)

        sandbox_settings = get_sandbox_settings()
        if self.session.config.sandbox_image:
            sandbox_settings = sandbox_settings.model_copy(
                update={"image": self.session.config.sandbox_image}
            )
        system_settings = get_system_settings_store().get_settings()
        sandbox_backend = SeamusOpenSandboxBackend(
            agent_id=self.session.agent_id,
            session_id=self.session.id,
            data_dir=data_dir,
            artifacts_dir=artifacts_dir,
            notes_dir=notes_dir,
            workspace_root=getattr(ws_mgr, "workspace_root", None),
            workspace_readonly=mount_policy.workspace_readonly,
            notes_mounted=mount_policy.notes_mounted,
            notes_readonly=mount_policy.notes_readonly,
            settings=sandbox_settings,
            skill_directories=system_settings.skill_directories,
            repositories=self.session.config.repositories,
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
            prompt_provider=self._provide_prompt_for_request,
            tools_provider=lambda req: self.get_active_tools_for_request(req.tools),
            messages_provider=self._provide_messages_for_request,
            should_short_circuit=lambda _req: self._pending_phase_transition is not None,
        )

        checkpointer = GitCheckpointSaver(
            agent_id=self.session.agent_id,
            session_id=self.session.id,
            workspace_manager=ws_mgr,
            session=self.session,
            secret_versions_provider=lambda: dict(self._loaded_secret_versions),
            external_repo_manager=ext_mgr,
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
        elif self.session.config.todo_implementation == TodoImplementation.SEAMUS:
            runner_middleware.append(
                SeamusTodoMiddleware(
                    get_thread=lambda: self.session.get_open_thread(),
                    workspace_manager=ws_mgr,
                    agent_id=self.session.agent_id,
                    session_id=self.session.id,
                    on_todos_changed=lambda: self.session.touch(),
                )
            )
        if self.session.config.skills_implementation == SkillsImplementation.SEAMUS:
            runner_middleware.append(
                SeamusSkillsMiddleware(
                    get_thread=lambda: self.session.get_open_thread(),
                    discovered_skills_provider=lambda: self.get_discovered_skills(),
                    on_skills_changed=lambda _skills: self.session.touch(),
                )
            )

        make_artifact_tool = StructuredTool.from_function(
            name="make_artifact",
            description=(
                "Create a new atomic A2UI renderable artifact under `/artifacts/<family>/<uuid>/` "
                "with a custom manifest and basic catalog components."
            ),
            func=self.handle_make_artifact,
            args_schema=MakeArtifactInput,
        )

        make_questionnaire_tool = StructuredTool.from_function(
            name="make_questionnaire",
            description=(
                "Create an atomic questionnaire artifact with a list of questions, whitelisted "
                "submit button, and optional blocking behavior."
            ),
            func=self.handle_make_questionnaire,
            args_schema=MakeQuestionnaireInput,
        )

        make_form_tool = StructuredTool.from_function(
            name="make_form",
            description=(
                "Create an atomic non-blocking form artifact in a dedicated tab with fields "
                "and whitelisted submit button."
            ),
            func=self.handle_make_form,
            args_schema=MakeFormInput,
        )

        wait_for_click_tool = StructuredTool.from_function(
            name="wait_for_click",
            description=(
                "Suspend agent execution within the current turn until the user clicks a button "
                "on an artifact. Returns the clicked button ID and context payload."
            ),
            func=lambda *args, **kwargs: "Suspended waiting for user click",
            coroutine=self.handle_wait_for_click,
            args_schema=WaitForClickInput,
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
            make_artifact_tool,
            make_questionnaire_tool,
            make_form_tool,
            wait_for_click_tool,
            plan_tool,
            make_plan_tool,
            update_plan_tool,
            edit_plan_tool,
            discard_tool,
        ]

        if self.session.config.web_search == WebSearchImplementation.DUCKDUCKGO:
            artifact_tools.extend(get_web_search_tools())

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

        gated_tools: set[str] = set()
        unlocked_tools: set[str] = set()
        if self.session.config.skills_implementation == SkillsImplementation.SEAMUS:
            all_skills = self.get_discovered_skills(thread=target_thread)
            for s in all_skills:
                if s.active:
                    for t in s.allowed_tools:
                        gated_tools.add(t)
                        if s.loaded:
                            unlocked_tools.add(t)

        filtered: list[Any] = []
        is_web_search_enabled = self.session.config.web_search == WebSearchImplementation.DUCKDUCKGO
        for tool_obj in request_tools:
            t_name = getattr(tool_obj, "name", None) or (
                tool_obj.get("name") if isinstance(tool_obj, dict) else None
            )
            if (
                isinstance(t_name, str)
                and not is_web_search_enabled
                and t_name in WEB_SEARCH_TOOL_NAMES
            ):
                continue
            if isinstance(t_name, str) and t_name in gated_tools and t_name not in unlocked_tools:
                continue
            if isinstance(t_name, str) and t_name in ALL_HARNESS_TOOLS:
                if t_name in allowed_harness:
                    filtered.append(tool_obj)
            else:
                filtered.append(tool_obj)
        return filtered

    def _apply_resolved_config_to_llm(self, resolved_config: Any) -> None:
        """Update the active ReasoningChatOpenAI instance with newly resolved secret values."""
        self._resolved_system_prompt = resolved_config.system_prompt
        if self._llm is None:
            return
        new_api_key = resolved_config.inference.api_key or ""
        new_base_url = resolved_config.inference.base_url
        new_model = resolved_config.model_name

        if resolved_config.inference.format == InferenceFormat.OLLAMA or "11434" in new_base_url:
            new_base_url = _ensure_ollama_model(new_base_url, new_model)
            if not new_api_key:
                new_api_key = "ollama"
            if not new_base_url.rstrip("/").endswith("/v1"):
                new_base_url = f"{new_base_url.rstrip('/')}/v1"

        current_key = (
            self._llm.openai_api_key.get_secret_value()
            if isinstance(self._llm.openai_api_key, SecretStr)
            else str(self._llm.openai_api_key or "")
        )
        if (
            current_key != new_api_key
            or self._llm.openai_api_base != new_base_url
            or self._llm.model_name != new_model
        ):
            reasoning_effort = (
                self.session.config.inference.reasoning_effort.value
                if self.session.config.inference.reasoning_effort != ReasoningEffort.DEFAULT
                else None
            )
            fresh_llm = ReasoningChatOpenAI(
                model=new_model,
                api_key=SecretStr(new_api_key),
                base_url=new_base_url,
                reasoning_effort=reasoning_effort,
            )
            self._llm.openai_api_key = fresh_llm.openai_api_key
            self._llm.openai_api_base = fresh_llm.openai_api_base
            self._llm.model_name = fresh_llm.model_name
            for attr in ("root_client", "client", "root_async_client", "async_client"):
                if hasattr(fresh_llm, attr):
                    setattr(self._llm, attr, getattr(fresh_llm, attr))

    def refresh_secrets_sync(self) -> bool:
        """Check referenced secrets in OpenBao and reload if any version has increased."""
        refs = collect_secret_references(self.session.config, allow_version=True)
        if not refs:
            return False

        client = get_default_vault_client()
        needs_reload = False
        checked_paths: dict[str, int] = {}

        for ref in refs:
            norm_path = ref.normalized_path
            loaded_ver = self._loaded_secret_versions.get((norm_path, ref.field))
            if loaded_ver is None:
                needs_reload = True
                break
            if norm_path not in checked_paths:
                try:
                    meta = client.get_secret_metadata_sync(ref.path)
                    checked_paths[norm_path] = int(meta.get("current_version") or 1)
                except Exception:
                    try:
                        _, ver = client.get_secret_with_version_sync(ref.path)
                        checked_paths[norm_path] = ver
                    except Exception:
                        logger.debug(
                            "Failed to check secret version for %s during sync refresh",
                            ref.path,
                            exc_info=True,
                        )
                        continue
            current_ver = checked_paths.get(norm_path)
            if current_ver is not None and current_ver > loaded_ver:
                needs_reload = True
                break

        if not needs_reload:
            return False

        resolved_config, version_map = resolve_secrets_with_versions_sync(
            self.session.config, client=client
        )
        self._loaded_secret_versions = dict(version_map)
        self.session.secret_versions = {
            f"{k[0]}:{k[1]}": v for k, v in self._loaded_secret_versions.items()
        }
        self._apply_resolved_config_to_llm(resolved_config)
        logger.info(
            "Reloaded updated secret versions for session %s: %s",
            self.session.id,
            self._loaded_secret_versions,
        )
        return True

    async def refresh_secrets(self) -> bool:
        """Async check referenced secrets in OpenBao and reload if any version increased."""
        refs = collect_secret_references(self.session.config, allow_version=True)
        if not refs:
            return False

        client = get_default_vault_client()
        needs_reload = False
        checked_paths: dict[str, int] = {}

        for ref in refs:
            norm_path = ref.normalized_path
            loaded_ver = self._loaded_secret_versions.get((norm_path, ref.field))
            if loaded_ver is None:
                needs_reload = True
                break
            if norm_path not in checked_paths:
                try:
                    meta = await client.get_secret_metadata(ref.path)
                    checked_paths[norm_path] = int(meta.get("current_version") or 1)
                except Exception:
                    try:
                        _, ver = await client.get_secret_with_version(ref.path)
                        checked_paths[norm_path] = ver
                    except Exception:
                        logger.debug(
                            "Failed to check secret version for %s during async refresh",
                            ref.path,
                            exc_info=True,
                        )
                        continue
            current_ver = checked_paths.get(norm_path)
            if current_ver is not None and current_ver > loaded_ver:
                needs_reload = True
                break

        if not needs_reload:
            return False

        resolved_config, version_map = await resolve_secrets_with_versions(
            self.session.config, client=client
        )
        self._loaded_secret_versions = dict(version_map)
        self.session.secret_versions = {
            f"{k[0]}:{k[1]}": v for k, v in self._loaded_secret_versions.items()
        }
        self._apply_resolved_config_to_llm(resolved_config)
        logger.info(
            "Reloaded updated secret versions for session %s: %s",
            self.session.id,
            self._loaded_secret_versions,
        )
        return True

    def _provide_prompt_for_request(self, _req: Any) -> str:
        """Check for newer secret versions per-inference and return the effective system prompt."""
        try:
            self.refresh_secrets_sync()
        except Exception:
            logger.debug("Error refreshing secrets before model inference", exc_info=True)
        return self.build_effective_system_prompt()

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
            repositories=self.session.config.repositories,
        )

    def get_sandbox_backend(self) -> SeamusOpenSandboxBackend:
        """Return or lazily initialize the SeamusOpenSandboxBackend for this session."""
        if self._sandbox_backend is None:
            self._agent = self._build_deep_agent()
        if self._sandbox_backend is None:
            msg = f"Sandbox backend was not initialized for session {self.session.id}"
            raise RuntimeError(msg)
        return self._sandbox_backend

    async def stream_terminal_command(
        self,
        command: str,
        working_directory: str | None = None,
        timeout: int | None = 300,
    ) -> AsyncGenerator[str, None]:
        """Stream command execution inside the sandbox container via SSE events.

        Yields SSE formatted data lines:
        - data: {"type": "stdout", "data": line}
        - data: {"type": "stderr", "data": line}
        - data: {"type": "exit", "exit_code": int, "working_directory": str}
        - data: {"type": "error", "message": str}
        """
        backend = self.get_sandbox_backend()
        effective_timeout = timeout if timeout is not None else 300
        initial_workdir = (working_directory or "").strip() or backend.settings.workdir

        cmd_stripped = command.strip()
        if not cmd_stripped:
            exit_data = {
                "type": "exit",
                "exit_code": 0,
                "working_directory": initial_workdir,
            }
            yield f"data: {json.dumps(exit_data)}\n\n"
            return

        wrapped_command = (
            f"{command}\n"
            f"__SEAMUS_STATUS__=$?\n"
            f'echo "__SEAMUS_CWD__=$(pwd)"\n'
            f"exit $__SEAMUS_STATUS__"
        )

        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        loop = asyncio.get_running_loop()
        current_workdir = initial_workdir
        delivered_any = False

        def on_stdout(msg: Any) -> None:
            nonlocal current_workdir, delivered_any
            text = getattr(msg, "text", str(msg))
            if text.startswith("__SEAMUS_CWD__="):
                current_workdir = text.split("__SEAMUS_CWD__=", 1)[1].strip()
                return
            delivered_any = True
            loop.call_soon_threadsafe(queue.put_nowait, {"type": "stdout", "data": text})

        def on_stderr(msg: Any) -> None:
            nonlocal delivered_any
            text = getattr(msg, "text", str(msg))
            delivered_any = True
            loop.call_soon_threadsafe(queue.put_nowait, {"type": "stderr", "data": text})

        def run_sync() -> None:
            try:
                from datetime import timedelta

                from opensandbox.models.execd import RunCommandOpts
                from opensandbox.models.execd_sync import ExecutionHandlersSync

                sandbox = backend._sandbox
                handlers = ExecutionHandlersSync(
                    on_stdout=on_stdout,
                    on_stderr=on_stderr,
                )
                opts = RunCommandOpts(
                    working_directory=initial_workdir,
                    timeout=timedelta(seconds=effective_timeout) if effective_timeout else None,
                )
                execution = sandbox.commands.run(wrapped_command, opts=opts, handlers=handlers)

                # Fallback delivery for mocked / non-streaming execution handlers in tests
                if not delivered_any and hasattr(execution, "logs"):
                    for m in getattr(execution.logs, "stdout", []):
                        on_stdout(m)
                    for m in getattr(execution.logs, "stderr", []):
                        on_stderr(m)

                exit_code = getattr(execution, "exit_code", 0)
                if exit_code is None:
                    exit_code = 0

                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    {
                        "type": "exit",
                        "exit_code": int(exit_code),
                        "working_directory": current_workdir,
                    },
                )
            except Exception as exc:
                logger.error("Terminal command execution failed: %s", exc, exc_info=True)
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    {"type": "error", "message": str(exc)},
                )
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        task = asyncio.create_task(asyncio.to_thread(run_sync))
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield f"data: {json.dumps(item)}\n\n"
        finally:
            if not task.done():
                task.cancel()

    def build_effective_system_prompt(
        self,
        include_dynamic_context: bool = True,
        thread: Thread | None = None,
    ) -> str:
        """Dynamically assemble the effective LM-XML system prompt for the session."""
        sandbox_settings = get_sandbox_settings()
        raw_prompt = (
            self._resolved_system_prompt
            if self._resolved_system_prompt is not None
            else (self.session.config.system_prompt or "")
        )
        custom_prompt = raw_prompt.strip()
        target_thread = thread or (
            self.session.get_open_thread()
            if self.session.is_active or self.session.threads
            else None
        )
        mode = target_thread.mode if target_thread else ModeName.CHAT.value
        phase = target_thread.phase if target_thread else None

        ws_mgr = get_workspace_manager()
        data_dir = ws_mgr.get_session_data_dir(self.session.agent_id, self.session.id)
        ext_mgr = get_external_repo_manager()
        projects_dir = ext_mgr.get_session_projects_dir(self.session.agent_id, self.session.id)
        discovered = discover_context_files(
            workspace_data_dir=data_dir,
            repositories=self.session.config.repositories,
            projects_dir=projects_dir,
            rules_patterns=self.session.config.rules_patterns,
        )

        skills_doc: SkillsPromptDocument | None = None
        if self.session.config.skills_implementation == SkillsImplementation.SEAMUS:
            all_skills = self.get_discovered_skills(thread=target_thread)
            avail = [
                AvailableSkillPromptItem(name=s.name, description=s.description)
                for s in all_skills
                if s.active
            ]
            active_items = [
                ActiveSkillPromptItem(name=s.name, instructions=s.instructions)
                for s in all_skills
                if s.active and s.loaded
            ]
            if avail:
                skills_doc = SkillsPromptDocument(
                    available_skills=avail,
                    active_skills=active_items if active_items else None,
                )

        plan_str: str | None = None
        if self.session.config.todo_implementation == TodoImplementation.SEAMUS:
            if target_thread and target_thread.todos:
                plan_str = render_plan_text(target_thread.todos)

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
            discovered_context=discovered,
            skills=skills_doc,
            plan=plan_str,
        )

    def get_discovered_skills(self, thread: Thread | None = None) -> list[DiscoveredSkill]:
        """Return discovered skills for this session, reflecting precedence and load state."""
        target_thread = thread or (
            self.session.get_open_thread()
            if self.session.is_active or self.session.threads
            else None
        )
        active_skill_names = target_thread.active_skills if target_thread else []
        return discover_session_skills(
            agent_id=self.session.agent_id,
            session_id=self.session.id,
            skills_implementation=self.session.config.skills_implementation,
            repositories=self.session.config.repositories,
            active_skill_names=active_skill_names,
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
            old_repos = {r.id: r for r in self.session.config.repositories}
            new_repos = {r.id: r for r in session.config.repositories}
            removed_ids = set(old_repos.keys()) - set(new_repos.keys())
            if removed_ids:
                old_mounts = calculate_mount_paths(self.session.config.repositories)
                ext_mgr = get_external_repo_manager()
                for rem_id in removed_ids:
                    mount_name = old_mounts.get(rem_id, "repo")
                    ext_mgr.unmount_working_copy(self.session.agent_id, self.session.id, mount_name)
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

    def handle_make_artifact(
        self,
        family: str,
        manifest: ArtifactManifest | dict[str, Any] | str,
        components: list[dict[str, Any]] | Any,
        uuid: str | None = None,
    ) -> str:
        """Create an atomic A2UI renderable artifact in /artifacts/<family>/<uuid>/."""
        mutations: list[str] = []

        raw_manifest = manifest
        if isinstance(raw_manifest, str):
            try:
                raw_manifest = json.loads(raw_manifest)
                mutations.append("Parsed manifest from JSON string.")
            except Exception as e:
                return (
                    f"Failed to render A2UI surface. Artifact was not stored.\n"
                    f"Validation errors:\n- Invalid manifest JSON: {e}"
                )

        manifest_obj: ArtifactManifest | None = None
        manifest_errors: list[str] = []
        if isinstance(raw_manifest, ArtifactManifest):
            manifest_obj = raw_manifest
        elif isinstance(raw_manifest, dict):
            try:
                manifest_obj = ArtifactManifest.model_validate(raw_manifest)
            except Exception as e:
                manifest_errors.append(f"Invalid manifest: {e}")
        else:
            manifest_errors.append(
                f"Invalid manifest: expected dict or ArtifactManifest, got "
                f"{type(raw_manifest).__name__}."
            )

        if manifest_errors or manifest_obj is None:
            formatted_errors = "\n".join(f"- {err}" for err in manifest_errors)
            return (
                f"Failed to render A2UI surface. Artifact was not stored.\n"
                f"Validation errors:\n{formatted_errors}"
            )

        # Normalize components loosely and auto-declare any undeclared buttons in manifest
        normalized_components = normalize_a2ui_components(components, mutation_log=mutations)
        auto_declare_manifest_buttons(manifest_obj, normalized_components, mutation_log=mutations)

        surface_errors = validate_a2ui_surface(
            components=normalized_components,
            manifest=manifest_obj,
        )
        if surface_errors:
            formatted_errors = "\n".join(f"- {err}" for err in surface_errors)
            return (
                f"Failed to render A2UI surface. Artifact was not stored.\n"
                f"Validation errors:\n{formatted_errors}"
            )

        surface_warnings = check_a2ui_surface_warnings(components=components)

        ws_mgr = get_workspace_manager()
        artifacts_dir = ws_mgr.get_session_artifacts_dir(self.session.agent_id, self.session.id)
        inst_uuid = ArtifactBuilder.create_artifact(
            artifacts_dir=artifacts_dir,
            family=family,
            manifest=manifest_obj,
            components=normalized_components,
            uuid=uuid,
        )
        art_event = {
            "type": "ARTIFACT_CREATED",
            "artifact_id": inst_uuid,
            "kind": family,
            "uuid": inst_uuid,
            "title": manifest_obj.name,
        }
        self.broadcaster.broadcast_sync(art_event)
        thread = self.session.get_open_thread()
        if thread is not None:
            thread.append_event(art_event)

        response = inst_uuid
        if mutations:
            mutations_text = "\n".join(f"- {m}" for m in mutations)
            response += f"\n\nNotice: Automatically normalized component tree:\n{mutations_text}"
        if surface_warnings:
            warnings_text = "\n".join(f"- {w}" for w in surface_warnings)
            response += f"\n\nWarning: Incomplete A2UI component tree:\n{warnings_text}"

        return response

    def handle_make_questionnaire(
        self,
        title: str = "Questionnaire",
        questions: list[Question | dict[str, Any]] | None = None,
        blocking: bool = True,
        exposition: Literal["tabbed", "embedded"] = "embedded",
    ) -> str:
        """Create an atomic questionnaire artifact."""
        q_objs: list[Question] = []
        for q in questions or []:
            if isinstance(q, Question):
                q_objs.append(q)
            elif isinstance(q, QuestionItem):
                q_objs.append(q.to_question())
            elif isinstance(q, dict):
                q_objs.append(Question.model_validate(q))
        ws_mgr = get_workspace_manager()
        artifacts_dir = ws_mgr.get_session_artifacts_dir(self.session.agent_id, self.session.id)
        inst_uuid = QuestionnaireBuilder.create_questionnaire(
            artifacts_dir=artifacts_dir,
            title=title,
            questions=q_objs,
            blocking=blocking,
            exposition=exposition,
        )
        art_event = {
            "type": "ARTIFACT_CREATED",
            "artifact_id": inst_uuid,
            "kind": "questionnaires",
            "uuid": inst_uuid,
            "title": title,
        }
        self.broadcaster.broadcast_sync(art_event)
        thread = self.session.get_open_thread()
        if thread is not None:
            thread.append_event(art_event)
        return inst_uuid

    def handle_make_form(
        self,
        title: str = "Form",
        fields: list[Question | dict[str, Any]] | None = None,
        blocking: bool = False,
        exposition: Literal["tabbed", "embedded"] = "tabbed",
    ) -> str:
        """Create an atomic form artifact."""
        f_objs: list[Question] = []
        for f in fields or []:
            if isinstance(f, Question):
                f_objs.append(f)
            elif isinstance(f, QuestionItem):
                f_objs.append(f.to_question())
            elif isinstance(f, dict):
                f_objs.append(Question.model_validate(f))
        ws_mgr = get_workspace_manager()
        artifacts_dir = ws_mgr.get_session_artifacts_dir(self.session.agent_id, self.session.id)
        inst_uuid = FormBuilder.create_form(
            artifacts_dir=artifacts_dir,
            title=title,
            fields=f_objs,
            blocking=blocking,
            exposition=exposition,
        )
        art_event = {
            "type": "ARTIFACT_CREATED",
            "artifact_id": inst_uuid,
            "kind": "forms",
            "uuid": inst_uuid,
            "title": title,
        }
        self.broadcaster.broadcast_sync(art_event)
        thread = self.session.get_open_thread()
        if thread is not None:
            thread.append_event(art_event)
        return inst_uuid

    async def handle_wait_for_click(
        self,
        artifact_id: str,
        button_id: str | None = None,
        fresh: bool = True,
        timeout: float | None = None,
    ) -> str:
        """Suspend execution until the user clicks a button on the specified artifact."""
        ws_mgr = get_workspace_manager()
        artifacts_dir = ws_mgr.get_session_artifacts_dir(self.session.agent_id, self.session.id)
        resolver = ArtifactResolver(artifacts_dir)
        matched = resolver.resolve_artifact(artifact_id)
        if matched is None:
            raise ValueError(f"Artifact '{artifact_id}' does not exist.")

        family = matched.family
        inst_dir = artifacts_dir / family / artifact_id
        interactions_dir = inst_dir / "interactions"

        # Check existing clicks if fresh=False
        if not fresh and interactions_dir.is_dir():
            if button_id:
                norm_id = button_id.replace("-", "_")
                btn_file = interactions_dir / f"{button_id}.json"
                if not btn_file.is_file() and norm_id != button_id:
                    btn_file = interactions_dir / f"{norm_id}.json"
                if btn_file.is_file():
                    try:
                        ctx = json.loads(btn_file.read_text(encoding="utf-8"))
                        mtime = btn_file.stat().st_mtime
                        return ClickResult(
                            artifact_id=artifact_id,
                            button_id=button_id,
                            context=ctx if isinstance(ctx, dict) else {},
                            timestamp=mtime,
                        ).model_dump_json()
                    except Exception:
                        pass
            else:
                json_files = sorted(
                    interactions_dir.glob("*.json"),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                )
                if json_files:
                    latest = json_files[0]
                    try:
                        ctx = json.loads(latest.read_text(encoding="utf-8"))
                        return ClickResult(
                            artifact_id=artifact_id,
                            button_id=latest.stem,
                            context=ctx if isinstance(ctx, dict) else {},
                            timestamp=latest.stat().st_mtime,
                        ).model_dump_json()
                    except Exception:
                        pass

        # We must suspend waiting for a user click
        thread = self.session.get_open_thread()
        tool_call_id: str | None = None
        for ev in reversed(thread.events):
            ev_type = getattr(ev, "type", None) or (
                ev.get("type") if isinstance(ev, dict) else None
            )
            if ev_type in ("TOOL_CALL_START", "tool_call_start"):
                name = getattr(ev, "tool_call_name", None) or (
                    ev.get("tool_call_name") if isinstance(ev, dict) else None
                )
                if name == "wait_for_click":
                    tool_call_id = getattr(ev, "tool_call_id", None) or (
                        ev.get("tool_call_id") if isinstance(ev, dict) else None
                    )
                    break
        if not tool_call_id:
            tool_call_id = f"call_{uuid4().hex[:12]}"

        session_dir = ws_mgr.get_session_workspace_path(self.session.agent_id, self.session.id)
        state_dir = session_dir / "agent" / "state" / "threads" / str(thread.id)
        state_dir.mkdir(parents=True, exist_ok=True)
        pending_wait_file = state_dir / "pending_wait.json"

        wait_payload = {
            "artifact_id": artifact_id,
            "button_id": button_id,
            "tool_call_id": tool_call_id,
            "thread_id": str(thread.id),
        }
        pending_wait_file.write_text(json.dumps(wait_payload, indent=2), encoding="utf-8")

        thread.status = AgentStatus.AWAITING_USER
        thread.touch()
        self.session.touch()
        ws_mgr.save_thread_events(self.session.agent_id, self.session.id, thread.id, thread.events)
        ws_mgr.commit_checkpoint_changes(self.session.agent_id, self.session.id, thread.id)

        # Broadcast status change to AWAITING_USER so frontend knows execution
        # is suspended waiting for user interaction
        await self.broadcaster.broadcast(
            {
                "type": "STATUS_CHANGED",
                "status": AgentStatus.AWAITING_USER.value,
            }
        )

        fut: asyncio.Future[str] = asyncio.get_running_loop().create_future()
        key = (artifact_id, button_id)
        self._pending_clicks[key] = fut

        try:
            if timeout is not None:
                res = await asyncio.wait_for(fut, timeout=timeout)
            else:
                res = await fut
            return res
        finally:
            self._pending_clicks.pop(key, None)
            if pending_wait_file.exists():
                try:
                    pending_wait_file.unlink()
                except OSError:
                    pass

    def handle_plan(self, retained_skills: list[str] | None = None) -> str:
        """Transition from Plan/Discuss to Plan/Make in a new thread and auto-wake."""
        open_thread = self.session.get_open_thread()
        if open_thread.mode != ModeName.PLAN.value or open_thread.phase != PlanPhase.DISCUSS.value:
            raise ValueError("The 'plan' tool can only be called during the Plan/Discuss phase.")
        self._pending_phase_transition = (
            ModeName.PLAN.value,
            PlanPhase.MAKE.value,
            True,
        )
        self._pending_retained_skills = retained_skills
        return "Transitioning session to Plan/Make phase in a new thread."

    def handle_make_plan(
        self,
        content: str | None = None,
        name: str = "Plan",
        title: str | None = None,
        steps: list[str] | None = None,
        blocking: bool = False,
        exposition: Literal["tabbed", "embedded"] = "tabbed",
    ) -> str:
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
        clean_title = (title or name or "Plan").strip() or "Plan"
        plan_text = content if content is not None else ("\n\n".join(steps) if steps else "")
        PlanBuilder.create_plan(artifacts_dir, plan_id, plan_text, title=clean_title)
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
                del_file = artifacts_dir / art.family / art.uuid / "closed.marker"
                del_file.touch(exist_ok=True)
                close_ev = {
                    "type": "ARTIFACT_CLOSED",
                    "artifact_id": art.uuid,
                    "kind": art.family,
                    "family": art.family,
                    "uuid": art.uuid,
                }
                self.broadcaster.broadcast_sync(close_ev)
                open_thread.append_event(close_ev)

        self._pending_phase_transition = (ModeName.PLAN.value, PlanPhase.DISCUSS.value, False)
        self._pending_retained_skills = None
        return "Discarded active plan and resetting session to a new Plan/Discuss thread."

    async def transition_to_phase(
        self,
        mode: str,
        phase: str | None = None,
        *,
        auto_wake: bool = False,
        retained_skills: list[str] | None = None,
    ) -> Thread:
        """Close the current thread, open a new thread in (mode, phase), and auto-wake if set."""
        resolved_mode, resolved_phase = normalize_mode_and_phase(mode, phase)
        new_thread = self.session.create_thread(
            mode=resolved_mode,
            phase=resolved_phase,
            retained_skills=retained_skills,
        )
        if auto_wake:
            new_thread.status = AgentStatus.AWAITING_LLM
        self.sync_sandbox_mounts(new_thread)

        try:
            ws_mgr = get_workspace_manager()
            ws_mgr.save_thread_events(
                self.session.agent_id, self.session.id, new_thread.id, new_thread.events
            )
            ws_mgr.commit_state_changes(self.session.agent_id, self.session.id, new_thread.id)
            ws_mgr.commit_session_config(self.session, secret_versions=self._loaded_secret_versions)
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

    def has_open_blocking_artifact(self) -> bool:
        """Check if the session currently has any open artifact with blocking=True."""
        try:
            ws_mgr = get_workspace_manager()
            artifacts_dir = ws_mgr.get_session_artifacts_dir(self.session.agent_id, self.session.id)
            resolver = ArtifactResolver(artifacts_dir)
            return resolver.has_open_blocking_artifact()
        except Exception:
            return False

    async def dispatch_artifact_click(
        self,
        family: str,
        uuid: str,
        button_id: str,
        context: dict[str, Any] | None = None,
        *,
        event: str | None = None,
        timestamp: str | None = None,
        data: dict[str, Any] | None = None,
        comments: list[dict[str, Any]] | None = None,
    ) -> ClickResult:
        """Process an artifact button click, update state/interactions, and handle resumption."""
        async with self._lock:
            if not self.session.is_active:
                msg = (
                    f"Session '{self.session.id}' is not active "
                    f"(current status: {self.session.status.value})."
                )
                raise SessionBusyError(msg)

            ws_mgr = get_workspace_manager()
            artifacts_dir = ws_mgr.get_session_artifacts_dir(self.session.agent_id, self.session.id)
            target_dir = artifacts_dir / family / uuid
            if not target_dir.is_dir():
                msg = f"Artifact '{family}/{uuid}' does not exist."
                raise ValueError(msg)

            resolver = ArtifactResolver(artifacts_dir)
            if resolver.is_closed(family, uuid):
                msg = f"Artifact '{family}/{uuid}' is already closed."
                raise ValueError(msg)

            # Record click and update state.json
            click_res = dispatch_button_click(
                artifacts_dir,
                family,
                uuid,
                button_id,
                context=context,
                event=event,
                timestamp=timestamp,
                data=data,
                comments=comments,
            )

            thread = self.session.get_open_thread()
            art_click = {
                "type": "ARTIFACT_INTERACTION",
                "family": family,
                "uuid": uuid,
                "button_id": button_id,
                "event": click_res.event,
                "timestamp": click_res.timestamp,
                "context": click_res.context,
                "data": click_res.data,
                "comments": click_res.comments,
            }
            thread.append_event(art_click)
            await self.broadcaster.broadcast(art_click)

            # Check if artifact closed after click
            if resolver.is_closed(family, uuid):
                art_closed = {
                    "type": "ARTIFACT_CLOSED",
                    "artifact_id": uuid,
                    "kind": family,
                    "family": family,
                    "uuid": uuid,
                }
                thread.append_event(art_closed)
                await self.broadcaster.broadcast(art_closed)

            # Handle plan proceed transition
            if family == "plans" and button_id in ("proceed_btn", "proceed-btn", "proceed"):
                PlanBuilder.approve_plan(artifacts_dir, uuid)
                self.session.active_plan_id = uuid
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
                return click_res

            # Check in-memory pending click future
            fut = self._pending_clicks.get((uuid, button_id)) or self._pending_clicks.get(
                (uuid, None)
            )
            if fut is not None and not fut.done():
                fut.set_result(click_res.model_dump_json())
                return click_res

            # Check on-disk pending_wait.json for restart-safe resumption
            session_dir = ws_mgr.get_session_workspace_path(self.session.agent_id, self.session.id)
            pending_wait_file = (
                session_dir / "agent" / "state" / "threads" / str(thread.id) / "pending_wait.json"
            )
            if pending_wait_file.is_file():
                try:
                    wait_record = json.loads(pending_wait_file.read_text(encoding="utf-8"))
                    if wait_record.get("artifact_id") == uuid and (
                        wait_record.get("button_id") is None
                        or wait_record.get("button_id") == button_id
                    ):
                        try:
                            pending_wait_file.unlink()
                        except OSError:
                            pass
                        call_id = wait_record.get("tool_call_id") or f"call_{uuid4().hex[:12]}"
                        tc_result = {
                            "type": "TOOL_CALL_RESULT",
                            "tool_call_id": call_id,
                            "content": click_res.model_dump_json(),
                            "role": "tool",
                        }
                        thread.append_event(tc_result)
                        await self.broadcaster.broadcast(tc_result)

                        tool_msg = ToolMessage(
                            content=click_res.model_dump_json(),
                            tool_call_id=call_id,
                            name="wait_for_click",
                        )
                        try:
                            self._agent.graph.update_state(
                                {"configurable": {"thread_id": thread.id.hex}},
                                {"messages": [tool_msg]},
                                as_node="tools",
                            )
                        except Exception:
                            logger.exception(
                                "Failed to update graph state with synthetic tool message"
                            )

                        thread.status = AgentStatus.AWAITING_LLM
                        thread.touch()
                        self.session.touch()
                        try:
                            ws_mgr.save_thread_events(
                                self.session.agent_id, self.session.id, thread.id, thread.events
                            )
                            ws_mgr.commit_checkpoint_changes(
                                self.session.agent_id, self.session.id, thread.id
                            )
                        except Exception:
                            logger.exception("Failed to save thread events or commit checkpoint")

                        self._active_task = asyncio.create_task(
                            self._run_loop(thread=thread, user_message=None)
                        )
                        return click_res
                except Exception:
                    logger.exception("Failed to process pending_wait.json on click")

            # If agent is idle / turn completed, notify agent with synthetic message
            if self.is_awaiting_user():
                payload_str = json.dumps(click_res.model_dump(exclude_none=True))
                synthetic_msg = (
                    f"{SYNTHETIC_MESSAGE_INDICATOR} User clicked '{button_id}' on artifact "
                    f"'{uuid}' with payload: {payload_str}"
                )
                asyncio.create_task(self.dispatch_user_input(synthetic_msg, is_synthetic=True))

            return click_res

    async def dispatch_artifact_submission(
        self,
        kind: str,
        name: str,
        data: dict[str, Any],
    ) -> str:
        """Transitional bridge for dispatch_artifact_submission to dispatch_artifact_click."""
        click_res = await self.dispatch_artifact_click(kind, name, "submit", data)
        return str(click_res.button_id)

    async def dispatch_user_input(
        self,
        text: str,
        message_id: str | None = None,
        is_synthetic: bool = False,
    ) -> str:
        """Dispatch a user message to the active thread and start execution."""
        async with self._lock:
            if not self.session.is_active:
                msg = (
                    f"Session '{self.session.id}' is not active "
                    f"(current status: {self.session.status.value})."
                )
                raise SessionBusyError(msg)

            if text.startswith(SYNTHETIC_MESSAGE_INDICATOR) and not is_synthetic:
                raise ValueError(
                    "Synthetic message indicator prefix is reserved for platform notifications."
                )

            if self.has_open_blocking_artifact() and not is_synthetic:
                msg = (
                    f"Session '{self.session.id}' has an open blocking artifact. "
                    "User must interact with the blocking artifact before sending messages."
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

    def _seed_thread_overlap(self, thread: Thread) -> None:
        """Seed an empty thread with trailing messages from its immediate predecessor thread."""
        overlap = getattr(self.session.config, "thread_message_overlap", 5)
        if overlap <= 0:
            return

        try:
            cur_state = self._agent.graph.get_state({"configurable": {"thread_id": thread.id.hex}})
            cur_messages = cur_state.values.get("messages", []) if cur_state else []
            if cur_messages:
                return

            thread_list = list(self.session.threads.values())
            if thread not in thread_list:
                return
            idx = thread_list.index(thread)
            if idx <= 0:
                return

            prev_thread = thread_list[idx - 1]
            prev_state = self._agent.graph.get_state(
                {"configurable": {"thread_id": prev_thread.id.hex}}
            )
            if not prev_state or not prev_state.values.get("messages"):
                return

            prev_messages = list(prev_state.values["messages"])
            carryover = select_message_overlap(prev_messages, overlap)
            if carryover:
                self._agent.graph.update_state(
                    {"configurable": {"thread_id": thread.id.hex}},
                    {"messages": carryover},
                )
                logger.info(
                    "Seeded thread %s with %d overlap messages from predecessor thread %s",
                    thread.id,
                    len(carryover),
                    prev_thread.id,
                )
        except Exception:
            logger.exception("Failed to seed thread message overlap for thread %s", thread.id)

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
        self._turn_created_artifact_ids.clear()
        self._pending_phase_transition = None
        self.sync_sandbox_mounts(thread)
        self._seed_thread_overlap(thread)
        input_data = RunAgentInput(
            thread_id=thread.id.hex,
            run_id=run_id,
            messages=[user_message] if user_message is not None else [],
        )

        ws_mgr = get_workspace_manager()
        ws_mgr.sync_session_workspace(self.session)
        try:
            await self.refresh_secrets()
        except Exception:
            logger.debug("Error refreshing secrets at start of _run_loop", exc_info=True)

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
                        pending_skills = self._pending_retained_skills
                        self._pending_phase_transition = None
                        self._pending_retained_skills = None
                        self._turn_created_artifact_ids.clear()
                        if thread.status != AgentStatus.ERROR and self.session.is_active:
                            thread.status = AgentStatus.AWAITING_USER
                            thread.exchange_count += 1
                            naming_cfg = self.session.config.daemons.naming
                            if naming_cfg.enabled and naming_cfg.model:
                                from seamus.harness.daemons.naming import (
                                    execute_session_naming,
                                    execute_thread_naming,
                                    is_stepback_trigger,
                                )

                                if is_stepback_trigger(thread.exchange_count):
                                    asyncio.create_task(execute_thread_naming(self, thread))

                                if len(self.session.threads) > 1 and is_stepback_trigger(
                                    self.session.total_exchange_count
                                ):
                                    asyncio.create_task(execute_session_naming(self))
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
                            ws_mgr.commit_session_config(
                                self.session, secret_versions=self._loaded_secret_versions
                            )
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
                                retained_skills=pending_skills,
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

    async def stream_session_events(
        self,
        session: Session,
        accept_header: str | None = None,
        follow: bool = True,
    ) -> AsyncGenerator[str, None]:
        """Stream past events concatenated from all threads, then stream live events."""
        encoder = EventEncoder(accept=accept_header or "*/*")
        sorted_threads = sorted(session.threads.values(), key=lambda t: t.created_at)

        # 1. Replay past events across all threads in chronological order
        for idx, thread in enumerate(sorted_threads):
            transition_ev = {
                "type": "THREAD_TRANSITION",
                "thread_id": str(thread.id),
                "thread_name": thread.name,
                "mode": thread.mode,
                "phase": thread.phase,
                "mode_label": thread.mode_label,
                "is_first": idx == 0,
                "is_open": thread.is_open,
                "created_at": thread.created_at.isoformat(),
            }
            yield self._format_sse_event(encoder, transition_ev)

            for event in thread.events:
                yield self._format_sse_event(encoder, event)

        # If session is terminal or client requested replay only, finish stream immediately
        if session.status != SessionStatus.ACTIVE or not follow:
            return

        # 2. Subscribe and stream live events from broadcaster across threads
        queue = self.broadcaster.subscribe()
        try:
            while session.status == SessionStatus.ACTIVE:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=1.0)
                    yield self._format_sse_event(encoder, event)
                except TimeoutError:
                    # Keepalive ping or check if session status changed
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
