"""Inspector service extracting agent configuration, runtime parameters, and branch state."""

import json
import logging
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from deepagents.middleware.skills import SKILLS_SYSTEM_PROMPT, SkillMetadata, SkillsMiddleware
from pydantic import BaseModel, Field, model_validator

from seamus.config.models import (
    ArtifactsImplementation,
    ExternalRepositoryConfig,
    SkillsImplementation,
    TodoImplementation,
    WebSearchImplementation,
)
from seamus.config.settings import get_system_settings_store, resolve_skill_path
from seamus.domain.entities import AgentStatus, Thread
from seamus.domain.modes import ALL_HARNESS_TOOLS, resolve_available_harness_tools
from seamus.domain.resolution import resolve_session, resolve_thread
from seamus.harness.prompt import (
    ActiveSkillPromptItem,
    AvailableSkillPromptItem,
    SkillsPromptDocument,
    build_effective_system_prompt,
    build_scaffold_prompt,
    discover_context_files,
)
from seamus.harness.runner import (
    SEAMUS_WRITE_TODOS_SYSTEM_PROMPT,
    ReasoningChatOpenAI,
    SessionAgentRunner,
    get_runner_registry,
)
from seamus.harness.sandbox import BUNDLED_SKILLS_DIR, get_sandbox_settings
from seamus.harness.skills import discover_session_skills, parse_skill_markdown
from seamus.harness.steerable import (
    SteerableResponse,
    get_steerable_registry,
)
from seamus.harness.store import get_harness_store
from seamus.harness.web_search import (
    WEB_SEARCH_TOOL_NAMES,
    get_web_search_tools,
)
from seamus.persistence import (
    calculate_mount_paths,
    derive_project_id,
    extract_readable_messages,
    get_external_repo_manager,
    get_workspace_manager,
)

logger = logging.getLogger(__name__)

SANDBOX_TOOL_NAMES = frozenset(
    {"ls", "read_file", "write_file", "edit_file", "delete", "glob", "grep", "execute"}
)


class ToolLabelInfo(BaseModel):
    """Semantic label and display color assigned to a tool."""

    title: str
    color: str


_TOOL_LABELING_CACHE: tuple[dict[str, ToolLabelInfo], dict[str, list[str]]] | None = None


def get_tool_labeling() -> tuple[dict[str, ToolLabelInfo], dict[str, list[str]]]:
    """Load and cache tool labeling configuration from tool_labeling.json."""
    global _TOOL_LABELING_CACHE
    if _TOOL_LABELING_CACHE is None:
        resource_path = Path(__file__).parent / "resources" / "tool_labeling.json"
        try:
            with open(resource_path, encoding="utf-8") as f:
                data = json.load(f)
            labels = {
                lbl["title"]: ToolLabelInfo(title=lbl["title"], color=lbl["color"])
                for lbl in data.get("labels", [])
                if "title" in lbl and "color" in lbl
            }
            tools = data.get("tools", {})
            _TOOL_LABELING_CACHE = (labels, tools)
        except Exception:
            logger.exception("Failed to load tool_labeling.json resource")
            _TOOL_LABELING_CACHE = ({}, {})
    return _TOOL_LABELING_CACHE


def get_tool_labels(name: str) -> list[ToolLabelInfo]:
    """Retrieve all assigned semantic labels for a tool by name."""
    labels_dict, tools_dict = get_tool_labeling()
    titles = tools_dict.get(name, [])
    return [labels_dict[t] for t in titles if t in labels_dict]


def categorize_tool(name: str) -> str:
    """Return taxonomy category for a tool by name."""
    lbls = get_tool_labels(name)
    if lbls:
        return lbls[0].title.capitalize()
    return "Custom"


class ToolInspectInfo(BaseModel):
    """Information about an available tool."""

    name: str
    description: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    backend: str = "opensandbox"
    category: str = "Sandbox"
    labels: list[ToolLabelInfo] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _default_labels_and_category(cls, data: Any) -> Any:
        if isinstance(data, dict):
            name = str(data.get("name", ""))
            if "labels" not in data or not data["labels"]:
                data["labels"] = [lbl.model_dump() for lbl in get_tool_labels(name)]
            if "category" not in data or not data["category"]:
                lbls = data.get("labels", [])
                if lbls and isinstance(lbls[0], dict) and "title" in lbls[0]:
                    data["category"] = lbls[0]["title"].capitalize()
                else:
                    data["category"] = "Custom"
        return data


class TodoInspectItem(BaseModel):
    """Information about a task todo item."""

    id: str | None = None
    content: str
    status: str = "pending"
    parent_id: str | None = None
    path: str | None = None
    depth: int = 0


class SkillInspectInfo(BaseModel):
    """Information about a discovered filesystem skill."""

    name: str
    description: str = ""
    origin_layer: str
    sandbox_path: str
    host_path: str | None = None
    content: str = ""
    active: bool = True
    loaded: bool = False
    allowed_tools: list[str] = Field(default_factory=list)


class SubAgentInspectInfo(BaseModel):
    """Information about a configured subagent."""

    name: str
    description: str
    subagent_type: str | None = None
    model: str | None = None


class MountedRepoInspectInfo(BaseModel):
    """Information about a mounted external Git repository."""

    id: str
    mount_path: str
    url: str
    branch: str
    credentials_configured: bool = False
    project_id: str = ""
    gitea_repo_name: str | None = None
    gitea_repo_url: str | None = None


class GitInspectInfo(BaseModel):
    """Git branch, commit, and remote Gitea repository information."""

    branch: str
    commit_sha: str | None = None
    commit_message: str | None = None
    commit_time: str | None = None
    repo_name: str
    gitea_url: str | None = None


class InferenceInspectInfo(BaseModel):
    """Model and inference runtime configuration."""

    model_name: str
    format: str
    base_url: str
    api_key_configured: bool


class PromptInspectInfo(BaseModel):
    """Decomposed system prompt information."""

    composite: str
    scaffold: str
    custom: str


class MessageHistoryItem(BaseModel):
    """Human-readable conversation message turn."""

    id: str | None = None
    role: str
    content: str | None = None
    reasoning: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None


class HistoryInspectInfo(BaseModel):
    """Message history and execution trajectory summary."""

    message_count: int
    checkpoint_step: int
    messages: list[MessageHistoryItem] = Field(default_factory=list)


class WorkspaceInspectInfo(BaseModel):
    """Agent operational workspace and file footprint."""

    operational_dir: str = "/workspace"
    files: list[str] = Field(default_factory=list)


class SteerableInspectInfo(BaseModel):
    """Runtime state of a single steerable model instance."""

    instance_id: str
    role: str
    strategy: str
    default_response: str
    wait_timeout: float
    pending_count: int = 0
    known_tools: list[str] = Field(default_factory=list)
    responses: list[SteerableResponse] = Field(default_factory=list)


class AgentInspectReport(BaseModel):
    """Consolidated agent inspection report as of the latest inference run."""

    agent_id: UUID
    agent_name: str | None = None
    session_id: UUID
    session_name: str | None = None
    thread_id: UUID
    thread_name: str | None = None
    status: AgentStatus
    git: GitInspectInfo
    inference: InferenceInspectInfo
    prompts: PromptInspectInfo
    tools: list[ToolInspectInfo] = Field(default_factory=list)
    todos: list[TodoInspectItem] = Field(default_factory=list)
    todo_implementation: TodoImplementation = TodoImplementation.DEEPAGENTS
    skills: list[SkillInspectInfo] = Field(default_factory=list)
    skills_implementation: SkillsImplementation = SkillsImplementation.DEEPAGENTS
    web_search: WebSearchImplementation = WebSearchImplementation.DUCKDUCKGO
    artifacts_implementation: ArtifactsImplementation = ArtifactsImplementation.SEAMUS
    subagents: list[SubAgentInspectInfo] = Field(default_factory=list)
    mounted_repositories: list[MountedRepoInspectInfo] = Field(default_factory=list)
    history: HistoryInspectInfo
    workspace: WorkspaceInspectInfo
    steerable_models: list[SteerableInspectInfo] = Field(default_factory=list)


_CACHED_DEFAULT_TOOLS: list[ToolInspectInfo] | None = None


def extract_tools_from_graph(graph: Any) -> list[ToolInspectInfo]:
    """Extract tool names, descriptions, and JSON argument schemas from a compiled agent graph."""
    if graph is None or not hasattr(graph, "nodes"):
        return get_default_tools_inspect_info()

    tools_node = graph.nodes.get("tools")
    if tools_node is None:
        return get_default_tools_inspect_info()

    bound = getattr(tools_node, "bound", None)
    tools_dict: dict[str, Any] = (
        getattr(bound, "tools_by_name", None) or getattr(bound, "_tools_by_name", None) or {}
    )

    if not tools_dict:
        return get_default_tools_inspect_info()

    results: list[ToolInspectInfo] = []
    for name in sorted(tools_dict.keys()):
        tool = tools_dict[name]
        desc = getattr(tool, "description", "") or ""
        params: dict[str, Any] = {}
        args_schema = getattr(tool, "args_schema", None)
        if args_schema is not None and hasattr(args_schema, "model_json_schema"):
            try:
                params = args_schema.model_json_schema()
            except Exception:
                params = {}
        elif hasattr(tool, "args") and isinstance(tool.args, dict):
            params = tool.args

        backend = (
            "opensandbox"
            if name in SANDBOX_TOOL_NAMES
            else ("web" if name in WEB_SEARCH_TOOL_NAMES else "harness")
        )
        results.append(
            ToolInspectInfo(
                name=name,
                description=desc,
                parameters=params,
                backend=backend,
            )
        )
    return results


def get_default_tools_inspect_info() -> list[ToolInspectInfo]:
    """Return default DeepAgents tool suite inspect definitions (cached)."""
    global _CACHED_DEFAULT_TOOLS
    if _CACHED_DEFAULT_TOOLS is not None:
        return _CACHED_DEFAULT_TOOLS

    try:
        from deepagents import create_deep_agent
        from langchain_core.tools import StructuredTool
        from pydantic import SecretStr

        from seamus.harness.runner import (
            DiscardInput,
            EditPlanInput,
            MakeArtifactInput,
            MakeFormInput,
            MakePlanInput,
            MakeQuestionnaireInput,
            PlanTransitionInput,
            SeamusTodoListMiddleware,
            UpdatePlanInput,
            WaitForClickInput,
        )
        from seamus.harness.todos import (
            CreateTodoItemInput,
            DeleteTodoItemInput,
            EditTodoItemInput,
        )

        dummy_tools = [
            StructuredTool.from_function(
                name="make_artifact",
                description="Create a new atomic A2UI renderable artifact.",
                func=lambda *args, **kwargs: "OK",
                args_schema=MakeArtifactInput,
            ),
            StructuredTool.from_function(
                name="make_questionnaire",
                description="Create an atomic questionnaire artifact.",
                func=lambda *args, **kwargs: "OK",
                args_schema=MakeQuestionnaireInput,
            ),
            StructuredTool.from_function(
                name="make_form",
                description="Create an atomic non-blocking form artifact.",
                func=lambda *args, **kwargs: "OK",
                args_schema=MakeFormInput,
            ),
            StructuredTool.from_function(
                name="wait_for_click",
                description="Suspend agent execution until the user clicks an active button.",
                func=lambda *args, **kwargs: "OK",
                args_schema=WaitForClickInput,
            ),
            StructuredTool.from_function(
                name="plan",
                description=(
                    "Transition the session from the Discuss phase to the Make phase "
                    "in a new thread."
                ),
                func=lambda *args, **kwargs: "OK",
                args_schema=PlanTransitionInput,
            ),
            StructuredTool.from_function(
                name="make_plan",
                description=(
                    "Create the session's Markdown implementation plan artifact in a dedicated tab."
                ),
                func=lambda *args, **kwargs: "OK",
                args_schema=MakePlanInput,
            ),
            StructuredTool.from_function(
                name="update_plan",
                description=(
                    "Overwrite the full Markdown content of the active session plan artifact."
                ),
                func=lambda *args, **kwargs: "OK",
                args_schema=UpdatePlanInput,
            ),
            StructuredTool.from_function(
                name="edit_plan",
                description="Perform an exact string replacement on the active session plan.",
                func=lambda *args, **kwargs: "OK",
                args_schema=EditPlanInput,
            ),
            StructuredTool.from_function(
                name="discard",
                description=(
                    "Discard any active session plan and open a new thread back in "
                    "the Discuss phase."
                ),
                func=lambda *args, **kwargs: "OK",
                args_schema=DiscardInput,
            ),
            StructuredTool.from_function(
                name="create_todo_item",
                description="Create a new task item in your active plan.",
                func=lambda *args, **kwargs: "OK",
                args_schema=CreateTodoItemInput,
            ),
            StructuredTool.from_function(
                name="edit_todo_item",
                description="Update or move an existing task item.",
                func=lambda *args, **kwargs: "OK",
                args_schema=EditTodoItemInput,
            ),
            StructuredTool.from_function(
                name="delete_todo_item",
                description="Delete a task item and all of its subtasks.",
                func=lambda *args, **kwargs: "OK",
                args_schema=DeleteTodoItemInput,
            ),
            *get_web_search_tools(),
        ]

        dummy_llm = ReasoningChatOpenAI(
            model="dummy",
            api_key=SecretStr("dummy"),
            base_url="https://dummy.local/v1",
        )
        dummy_graph = create_deep_agent(
            model=dummy_llm,
            tools=dummy_tools,
            middleware=[SeamusTodoListMiddleware()],
        )
        tools_node = dummy_graph.nodes.get("tools")
        bound = getattr(tools_node, "bound", None)
        tools_dict = (
            getattr(bound, "tools_by_name", None) or getattr(bound, "_tools_by_name", None) or {}
        )
        extracted: list[ToolInspectInfo] = []
        for name in sorted(tools_dict.keys()):
            tool = tools_dict[name]
            desc = getattr(tool, "description", "") or ""
            params: dict[str, Any] = {}
            args_schema = getattr(tool, "args_schema", None)
            if args_schema is not None and hasattr(args_schema, "model_json_schema"):
                try:
                    params = args_schema.model_json_schema()
                except Exception:
                    params = {}
            backend = (
                "opensandbox"
                if name in SANDBOX_TOOL_NAMES
                else ("web" if name in WEB_SEARCH_TOOL_NAMES else "harness")
            )
            extracted.append(
                ToolInspectInfo(
                    name=name,
                    description=desc,
                    parameters=params,
                    backend=backend,
                )
            )
        _CACHED_DEFAULT_TOOLS = extracted
        return _CACHED_DEFAULT_TOOLS
    except Exception:
        logger.exception("Failed to compile dummy graph for default tools schema")
        return [
            ToolInspectInfo(
                name="ls",
                description="Lists all files in a directory.",
                backend="opensandbox",
            ),
            ToolInspectInfo(
                name="read_file",
                description="Reads a file from the filesystem.",
                backend="opensandbox",
            ),
            ToolInspectInfo(
                name="write_file",
                description="Writes content to a file.",
                backend="opensandbox",
            ),
            ToolInspectInfo(
                name="edit_file",
                description="Performs exact string replacements in files.",
                backend="opensandbox",
            ),
            ToolInspectInfo(
                name="delete",
                description="Deletes a file or directory from the filesystem.",
                backend="opensandbox",
            ),
            ToolInspectInfo(
                name="glob",
                description="Find files matching a glob pattern.",
                backend="opensandbox",
            ),
            ToolInspectInfo(
                name="grep",
                description="Search for a LITERAL text pattern across files.",
                backend="opensandbox",
            ),
            ToolInspectInfo(
                name="execute",
                description="Executes a shell command in an isolated sandbox.",
                backend="opensandbox",
            ),
            ToolInspectInfo(
                name="task",
                description="Launch an ephemeral subagent.",
                backend="harness",
            ),
            ToolInspectInfo(
                name="write_todos",
                description=(
                    "Use this tool to create and manage a structured task list "
                    "for your current work session."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "todos": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "content": {"type": "string"},
                                    "status": {
                                        "type": "string",
                                        "enum": ["pending", "in_progress", "completed"],
                                    },
                                },
                                "required": ["content", "status"],
                            },
                        }
                    },
                    "required": ["todos"],
                },
                backend="harness",
            ),
            ToolInspectInfo(
                name="make_artifact",
                description="Create a new atomic A2UI renderable artifact.",
                parameters=MakeArtifactInput.model_json_schema(),
                backend="harness",
            ),
            ToolInspectInfo(
                name="make_questionnaire",
                description="Create an atomic questionnaire artifact.",
                parameters=MakeQuestionnaireInput.model_json_schema(),
                backend="harness",
            ),
            ToolInspectInfo(
                name="make_form",
                description="Create an atomic non-blocking form artifact.",
                parameters=MakeFormInput.model_json_schema(),
                backend="harness",
            ),
            ToolInspectInfo(
                name="wait_for_click",
                description="Suspend agent execution until the user clicks an active button.",
                parameters=WaitForClickInput.model_json_schema(),
                backend="harness",
            ),
            ToolInspectInfo(
                name="create_todo_item",
                description="Create a new task item in your active plan.",
                parameters=CreateTodoItemInput.model_json_schema(),
                backend="harness",
            ),
            ToolInspectInfo(
                name="edit_todo_item",
                description="Update or move an existing task item.",
                parameters=EditTodoItemInput.model_json_schema(),
                backend="harness",
            ),
            ToolInspectInfo(
                name="delete_todo_item",
                description="Delete a task item and all of its subtasks.",
                parameters=DeleteTodoItemInput.model_json_schema(),
                backend="harness",
            ),
        ]


def extract_thread_messages(
    agent_id: UUID,
    session_id: UUID,
    thread: Thread,
) -> tuple[list[MessageHistoryItem], int]:
    """Extract message history and checkpoint count for a thread."""
    ws_mgr = get_workspace_manager()

    # 1. Try loading from messages.json
    raw_msgs = ws_mgr.load_thread_messages(agent_id, session_id, thread.id)
    checkpoint_step = 0

    # Read checkpoint count
    cp_data = ws_mgr.load_thread_checkpoints(agent_id, session_id, thread.id)
    if cp_data and isinstance(cp_data, dict):
        storage = cp_data.get("storage", {})
        for ns_dict in storage.values():
            for cp_dict in ns_dict.values():
                checkpoint_step += len(cp_dict)

    if raw_msgs:
        items = [
            MessageHistoryItem(
                id=str(m.get("id")) if m.get("id") else None,
                role=m.get("role", "unknown"),
                content=m.get("content") or "",
                tool_calls=m.get("tool_calls"),
                tool_call_id=m.get("tool_call_id"),
            )
            for m in raw_msgs
        ]
        return items, checkpoint_step

    # 2. Try loading from checkpoints.json if messages.json was not yet created
    if cp_data and isinstance(cp_data, dict):
        # Extract messages from latest checkpoint tuple
        storage = cp_data.get("storage", {})
        latest_cp: Any = None
        for ns_dict in storage.values():
            for cp_dict in ns_dict.values():
                for cp_entry in cp_dict.values():
                    latest_cp = cp_entry  # last one

        if latest_cp:
            try:
                # cp_entry is (cp_data, meta_data, parent_id)
                # where cp_data is (val_type, base64_blob)
                from base64 import b64decode

                from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

                val_type = latest_cp[0][0]
                blob = b64decode(latest_cp[0][1])
                try:
                    cp_obj = JsonPlusSerializer().loads_typed((val_type, blob))
                except Exception:
                    import pickle

                    cp_obj = pickle.loads(blob)
                extracted = extract_readable_messages(cp_obj)
                items = [
                    MessageHistoryItem(
                        id=str(m.get("id")) if m.get("id") else None,
                        role=m.get("role", "unknown"),
                        content=m.get("content") or "",
                        tool_calls=m.get("tool_calls"),
                        tool_call_id=m.get("tool_call_id"),
                    )
                    for m in extracted
                ]
                return items, checkpoint_step
            except Exception:
                logger.exception("Failed to decode checkpoint")

    # 3. Fall back to thread.events if present
    items = []
    for ev in thread.events:
        ev_type = getattr(ev, "type", None) or (ev.get("type") if isinstance(ev, dict) else None)
        if ev_type == "TEXT_MESSAGE_END":
            txt = getattr(ev, "content", None) or (
                ev.get("content") if isinstance(ev, dict) else ""
            )
            items.append(MessageHistoryItem(role="assistant", content=txt))
        elif ev_type == "USER_INPUT":
            txt = getattr(ev, "input", None) or (ev.get("input") if isinstance(ev, dict) else "")
            items.append(MessageHistoryItem(role="user", content=txt))

    return items, checkpoint_step or len(thread.events)


def extract_thread_todos(
    agent_id: UUID,
    session_id: UUID,
    thread: Thread,
    runner: SessionAgentRunner | None = None,
) -> list[TodoInspectItem]:
    """Extract task todos for a thread from live thread entities, workspace, or checkpoints."""
    # 0. Try live thread.todos entity collection
    if thread.todos:
        from seamus.harness.todos import compute_hierarchical_paths

        rendered = compute_hierarchical_paths(thread.todos)
        return [
            TodoInspectItem(
                id=r.item.id,
                content=r.item.content,
                status=r.item.status,
                parent_id=r.item.parent_id,
                path=r.path,
                depth=r.depth,
            )
            for r in rendered
        ]

    # 1. Try runner active graph state
    if runner is not None and hasattr(runner, "agent") and hasattr(runner.agent, "graph"):
        try:
            config = {"configurable": {"thread_id": str(thread.id)}}
            state = runner.agent.graph.get_state(config)
            if state and hasattr(state, "values") and isinstance(state.values, dict):
                raw_todos = state.values.get("todos")
                if isinstance(raw_todos, list) and raw_todos:
                    return [
                        TodoInspectItem(
                            content=str(t.get("content", "")),
                            status=str(t.get("status", "pending")),
                        )
                        for t in raw_todos
                        if isinstance(t, dict)
                    ]
        except Exception:
            logger.debug("Could not get todos from live graph state for thread %s", thread.id)

    # 2. Try loading from workspace todos.json
    ws_mgr = get_workspace_manager()
    raw_todos = ws_mgr.load_thread_todos(agent_id, session_id, thread.id)
    if raw_todos:
        if any("id" in t for t in raw_todos if isinstance(t, dict)):
            from seamus.domain.entities import TodoItem
            from seamus.harness.todos import compute_hierarchical_paths

            items = [
                TodoItem.model_validate(t) for t in raw_todos if isinstance(t, dict) and "id" in t
            ]
            rendered = compute_hierarchical_paths(items)
            return [
                TodoInspectItem(
                    id=r.item.id,
                    content=r.item.content,
                    status=r.item.status,
                    parent_id=r.item.parent_id,
                    path=r.path,
                    depth=r.depth,
                )
                for r in rendered
            ]
        return [
            TodoInspectItem(
                content=str(t.get("content", "")),
                status=str(t.get("status", "pending")),
            )
            for t in raw_todos
            if isinstance(t, dict)
        ]

    # 3. Try loading from checkpoints.json
    cp_data = ws_mgr.load_thread_checkpoints(agent_id, session_id, thread.id)
    if cp_data and isinstance(cp_data, dict):
        storage = cp_data.get("storage", {})
        latest_cp: Any = None
        for ns_dict in storage.values():
            for cp_dict in ns_dict.values():
                for cp_entry in cp_dict.values():
                    latest_cp = cp_entry
        if latest_cp:
            try:
                from base64 import b64decode

                from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

                from seamus.persistence.checkpointer import extract_readable_todos

                val_type = latest_cp[0][0]
                blob = b64decode(latest_cp[0][1])
                try:
                    cp_obj = JsonPlusSerializer().loads_typed((val_type, blob))
                except Exception:
                    import pickle

                    cp_obj = pickle.loads(blob)
                extracted = extract_readable_todos(cp_obj)
                if extracted:
                    return [
                        TodoInspectItem(
                            content=str(t.get("content", "")),
                            status=str(t.get("status", "pending")),
                        )
                        for t in extracted
                    ]
            except Exception:
                logger.debug("Could not decode checkpoint for todos")

    return []


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*(?:\n(.*))?$", re.DOTALL)


def _parse_skill_markdown(raw_text: str, default_name: str) -> tuple[str, str, str]:
    """Parse SKILL.md frontmatter and body resiliently, tolerating unquoted colons/braces."""
    name, desc, body, _tools = parse_skill_markdown(raw_text, default_name)
    return name, desc, body


def extract_session_skills(
    agent_id: UUID,
    session_id: UUID,
    skills_implementation: SkillsImplementation,
    repositories: Sequence[ExternalRepositoryConfig] | None = None,
    active_skill_names: Sequence[str] | None = None,
    artifacts_implementation: ArtifactsImplementation = ArtifactsImplementation.SEAMUS,
) -> list[SkillInspectInfo]:
    """Discover skills across workspace, mounted projects, and system directories."""
    skills = discover_session_skills(
        agent_id=agent_id,
        session_id=session_id,
        skills_implementation=skills_implementation,
        repositories=repositories,
        active_skill_names=active_skill_names,
        artifacts_implementation=artifacts_implementation,
    )
    return [
        SkillInspectInfo(
            name=s.name,
            description=s.description,
            origin_layer=s.origin_layer,
            sandbox_path=s.sandbox_path,
            host_path=s.host_path,
            content=s.content,
            active=s.active,
            loaded=s.loaded,
            allowed_tools=s.allowed_tools,
        )
        for s in skills
    ]


def build_middleware_prompt_sections(
    *,
    todo_implementation: TodoImplementation,
    skills_implementation: SkillsImplementation,
    skills: Sequence[SkillInspectInfo],
    workdir: str = "/workspace",
    artifacts_implementation: ArtifactsImplementation = ArtifactsImplementation.SEAMUS,
) -> str:
    """Assemble the system prompt sections appended at runtime by active DeepAgents middleware."""
    sections: list[str] = []
    norm_workdir = workdir.rstrip("/") or "/workspace"

    if todo_implementation == TodoImplementation.DEEPAGENTS:
        sections.append(SEAMUS_WRITE_TODOS_SYSTEM_PROMPT)

    if skills_implementation == SkillsImplementation.DEEPAGENTS:
        system_settings = get_system_settings_store().get_settings()
        valid_sys_dirs = [
            d for d in system_settings.skill_directories if resolve_skill_path(d) is not None
        ]
        skill_sources = [f"/skills/system/{i}" for i in range(len(valid_sys_dirs))] + [
            f"{norm_workdir}/.skills",
            f"{norm_workdir}/skills",
        ]
        if artifacts_implementation != ArtifactsImplementation.NONE and BUNDLED_SKILLS_DIR.is_dir():
            skill_sources.append("/skills/bundled")
        sm = SkillsMiddleware(backend=cast(Any, None), sources=skill_sources)
        active_meta: list[SkillMetadata] = [
            SkillMetadata(
                name=s.name,
                description=s.description,
                path=s.sandbox_path,
                license=None,
                compatibility=None,
                metadata={},
                allowed_tools=[],
            )
            for s in skills
            if s.active
        ]
        skills_section = SKILLS_SYSTEM_PROMPT.format(
            skills_locations=sm._format_skills_locations(),
            skills_load_warnings="",
            skills_list=sm._format_skills_list(active_meta),
        )
        sections.append(skills_section)

    return "\n\n".join(s for s in sections if s)


def build_agent_inspect_report(
    agent_identifier: str,
    session_identifier: str,
    thread_identifier: str | None = None,
) -> AgentInspectReport:
    """Build a complete AgentInspectReport for the requested agent, session, and thread."""
    store = get_harness_store()
    agent = store.resolve_agent(agent_identifier)
    session = resolve_session(agent, session_identifier)

    if thread_identifier is not None:
        thread = resolve_thread(session, thread_identifier)
    else:
        thread = session.get_open_thread()

    ws_mgr = get_workspace_manager()
    persist_settings = ws_mgr.settings

    # Git Provenance
    git_meta = ws_mgr.get_session_git_info(agent.id, session.id)
    gitea_url: str | None = None
    if persist_settings.enabled and persist_settings.gitea_external_url:
        gitea_url = (
            f"{persist_settings.gitea_external_url.rstrip('/')}/"
            f"{persist_settings.gitea_admin_user}/agent-{agent.id}/src/branch/session/{session.id}"
        )

    git_info = GitInspectInfo(
        branch=f"session/{session.id}",
        commit_sha=git_meta.get("commit_sha"),
        commit_message=git_meta.get("commit_message"),
        commit_time=git_meta.get("commit_time"),
        repo_name=ws_mgr.get_agent_repo_name(agent.id),
        gitea_url=gitea_url,
    )

    # Inference Configuration
    api_key_configured = bool(
        session.config.inference.api_key and session.config.inference.api_key.strip()
    )
    inference_info = InferenceInspectInfo(
        model_name=session.config.model_name,
        format=session.config.inference.format.value,
        base_url=session.config.inference.base_url,
        api_key_configured=api_key_configured,
    )

    # System Prompts
    sandbox_settings = get_sandbox_settings()
    base_scaffold_prompt = build_scaffold_prompt(
        sandbox_settings.workdir,
        mode=thread.mode,
        phase=thread.phase,
        active_plan_id=session.active_plan_id,
    )
    custom_prompt = (session.config.system_prompt or "").strip()
    data_dir = ws_mgr.get_session_data_dir(agent.id, session.id)
    artifacts_dir = ws_mgr.get_session_artifacts_dir(agent.id, session.id)
    notes_dir = ws_mgr.get_session_notes_dir(agent.id, session.id)

    # Runner & Tools
    registry = get_runner_registry()
    session_key = str(session.id)
    runner: SessionAgentRunner | None = registry._runners.get(session_key)

    if runner is None and session.config.is_complete():
        try:
            runner = registry.get_runner(session, agent)
        except Exception:
            logger.debug(
                "Could not instantiate runner for session %s during inspection", session.id
            )

    skills = extract_session_skills(
        agent.id,
        session.id,
        session.config.skills_implementation,
        repositories=session.config.repositories,
        active_skill_names=thread.active_skills if thread else None,
        artifacts_implementation=session.config.artifacts_implementation,
    )

    if runner is not None:
        base_composite_prompt = runner.build_effective_system_prompt(thread=thread)
    else:
        ws_mgr = get_workspace_manager()
        ext_mgr = get_external_repo_manager()
        data_dir = ws_mgr.get_session_data_dir(agent.id, session.id)
        projects_dir = ext_mgr.get_session_projects_dir(agent.id, session.id)
        discovered_ctx = discover_context_files(
            workspace_data_dir=data_dir,
            repositories=session.config.repositories,
            projects_dir=projects_dir,
            rules_patterns=session.config.rules_patterns,
        )
        skills_doc: SkillsPromptDocument | None = None
        if session.config.skills_implementation == SkillsImplementation.SEAMUS:
            avail = [
                AvailableSkillPromptItem(name=s.name, description=s.description)
                for s in skills
                if s.active
            ]
            active_items = [
                ActiveSkillPromptItem(name=s.name, instructions=s.content)
                for s in skills
                if s.active and s.loaded
            ]
            if avail:
                skills_doc = SkillsPromptDocument(
                    available_skills=avail,
                    active_skills=active_items if active_items else None,
                )
        plan_str: str | None = None
        if session.config.todo_implementation == TodoImplementation.SEAMUS and thread.todos:
            from seamus.harness.todos import render_plan_text

            plan_str = render_plan_text(thread.todos)

        base_composite_prompt = build_effective_system_prompt(
            workdir=sandbox_settings.workdir,
            custom_prompt=custom_prompt or None,
            session_id=str(session.id),
            agent_id=str(agent.id),
            mode=thread.mode,
            phase=thread.phase,
            active_plan_id=session.active_plan_id,
            discovered_context=discovered_ctx,
            skills=skills_doc,
            plan=plan_str,
            artifacts_implementation=session.config.artifacts_implementation,
        )

    middleware_prompt_sections = build_middleware_prompt_sections(
        todo_implementation=session.config.todo_implementation,
        skills_implementation=session.config.skills_implementation,
        skills=skills,
        workdir=sandbox_settings.workdir,
        artifacts_implementation=session.config.artifacts_implementation,
    )

    scaffold_prompt = (
        f"{base_scaffold_prompt}\n\n{middleware_prompt_sections}"
        if middleware_prompt_sections
        else base_scaffold_prompt
    )
    composite_prompt = (
        f"{base_composite_prompt}\n\n{middleware_prompt_sections}"
        if middleware_prompt_sections
        else base_composite_prompt
    )

    prompt_info = PromptInspectInfo(
        composite=composite_prompt,
        scaffold=scaffold_prompt,
        custom=custom_prompt,
    )

    if runner is not None and hasattr(runner, "agent") and hasattr(runner.agent, "graph"):
        tools = extract_tools_from_graph(runner.agent.graph)
    else:
        tools = get_default_tools_inspect_info()

    allowed_harness_tools = resolve_available_harness_tools(
        thread.mode,
        thread.phase,
        has_active_plan=bool(session.active_plan_id),
        artifacts_implementation=session.config.artifacts_implementation,
    )
    tools = [t for t in tools if t.name not in ALL_HARNESS_TOOLS or t.name in allowed_harness_tools]

    if session.config.todo_implementation == TodoImplementation.NONE:
        tools = [
            t
            for t in tools
            if t.name
            not in (
                "write_todos",
                "create_todo_item",
                "edit_todo_item",
                "delete_todo_item",
            )
        ]
        todos = []
    elif session.config.todo_implementation == TodoImplementation.DEEPAGENTS:
        tools = [
            t
            for t in tools
            if t.name
            not in (
                "create_todo_item",
                "edit_todo_item",
                "delete_todo_item",
            )
        ]
        todos = extract_thread_todos(agent.id, session.id, thread, runner=runner)
    else:  # SEAMUS
        tools = [t for t in tools if t.name != "write_todos"]
        todos = extract_thread_todos(agent.id, session.id, thread, runner=runner)

    if session.config.web_search == WebSearchImplementation.NONE:
        tools = [t for t in tools if t.name not in WEB_SEARCH_TOOL_NAMES]

    # Message History
    messages, checkpoint_step = extract_thread_messages(agent.id, session.id, thread)
    history_info = HistoryInspectInfo(
        message_count=len(messages),
        checkpoint_step=checkpoint_step,
        messages=messages,
    )

    # Workspace Files
    files: list[str] = []
    if data_dir.exists():
        for p in data_dir.rglob("*"):
            if p.is_file() and p.name != ".gitkeep":
                try:
                    files.append(str(p.relative_to(data_dir)))
                except ValueError:
                    files.append(p.name)
    if artifacts_dir.exists():
        for p in artifacts_dir.rglob("*"):
            if p.is_file() and p.name != ".gitkeep":
                try:
                    files.append(f"artifacts/{p.relative_to(artifacts_dir)}")
                except ValueError:
                    files.append(f"artifacts/{p.name}")
    if notes_dir.exists():
        for p in notes_dir.rglob("*"):
            if p.is_file() and p.name != ".gitkeep":
                try:
                    files.append(f"notes/{p.relative_to(notes_dir)}")
                except ValueError:
                    files.append(f"notes/{p.name}")
    files = sorted(set(files))

    workspace_info = WorkspaceInspectInfo(
        operational_dir=sandbox_settings.workdir,
        files=files,
    )

    mounted_repositories: list[MountedRepoInspectInfo] = []
    if session.config.repositories:
        ws_mgr = get_workspace_manager()
        mount_paths = calculate_mount_paths(session.config.repositories)
        for repo in session.config.repositories:
            mount_name = mount_paths.get(repo.id, "repo")
            p_id = derive_project_id(repo.url)
            g_name = f"project-{p_id}"
            g_url = (
                f"{ws_mgr.settings.gitea_url.rstrip('/')}/"
                f"{ws_mgr.settings.gitea_admin_user}/{g_name}"
                if ws_mgr.settings.enabled
                else None
            )
            mounted_repositories.append(
                MountedRepoInspectInfo(
                    id=repo.id,
                    mount_path=f"/projects/{mount_name}",
                    url=repo.url,
                    branch=repo.branch,
                    credentials_configured=bool(repo.credentials and repo.credentials.strip()),
                    project_id=p_id,
                    gitea_repo_name=g_name,
                    gitea_repo_url=g_url,
                )
            )

    steerable_models = [
        SteerableInspectInfo(
            instance_id=instance.instance_id,
            role=instance.role,
            strategy=instance.strategy.value,
            default_response=instance.default_response,
            wait_timeout=instance.wait_timeout,
            pending_count=instance.pending_count,
            known_tools=list(instance.known_tools),
            responses=list(instance.responses),
        )
        for instance in get_steerable_registry().list_for_session(session.id)
    ]

    return AgentInspectReport(
        agent_id=agent.id,
        agent_name=agent.name,
        session_id=session.id,
        session_name=session.name,
        thread_id=thread.id,
        thread_name=thread.name,
        status=thread.status,
        git=git_info,
        inference=inference_info,
        prompts=prompt_info,
        tools=tools,
        todos=todos,
        todo_implementation=session.config.todo_implementation,
        skills=skills,
        skills_implementation=session.config.skills_implementation,
        web_search=session.config.web_search,
        artifacts_implementation=session.config.artifacts_implementation,
        subagents=[],
        mounted_repositories=mounted_repositories,
        history=history_info,
        workspace=workspace_info,
        steerable_models=steerable_models,
    )
