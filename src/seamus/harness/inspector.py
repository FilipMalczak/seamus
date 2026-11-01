"""Inspector service extracting agent configuration, runtime parameters, and branch state."""

import logging
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from seamus.domain.entities import AgentStatus, Thread
from seamus.domain.resolution import resolve_session, resolve_thread
from seamus.harness.prompt import build_effective_system_prompt, build_scaffold_prompt
from seamus.harness.runner import (
    ReasoningChatOpenAI,
    SessionAgentRunner,
    get_runner_registry,
)
from seamus.harness.sandbox import get_sandbox_settings
from seamus.harness.store import get_harness_store
from seamus.persistence import (
    extract_readable_messages,
    get_workspace_manager,
)

logger = logging.getLogger(__name__)

SANDBOX_TOOL_NAMES = frozenset(
    {"ls", "read_file", "write_file", "edit_file", "delete", "glob", "grep", "execute"}
)


class ToolInspectInfo(BaseModel):
    """Information about an available tool."""

    name: str
    description: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    backend: str = "opensandbox"


class SubAgentInspectInfo(BaseModel):
    """Information about a configured subagent."""

    name: str
    description: str
    subagent_type: str | None = None
    model: str | None = None


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
    subagents: list[SubAgentInspectInfo] = Field(default_factory=list)
    history: HistoryInspectInfo
    workspace: WorkspaceInspectInfo


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

        backend = "opensandbox" if name in SANDBOX_TOOL_NAMES else "harness"
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
        from pydantic import SecretStr

        dummy_llm = ReasoningChatOpenAI(
            model="dummy",
            api_key=SecretStr("dummy"),
            base_url="https://dummy.local/v1",
        )
        dummy_graph = create_deep_agent(model=dummy_llm)
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
            backend = "opensandbox" if name in SANDBOX_TOOL_NAMES else "harness"
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
                import pickle
                from base64 import b64decode

                blob = b64decode(latest_cp[0][1])
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
                logger.exception("Failed to decode checkpoint pickle")

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
    scaffold_prompt = build_scaffold_prompt(sandbox_settings.workdir)
    custom_prompt = (session.config.system_prompt or "").strip()

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

    composite_prompt = (
        runner.effective_system_prompt
        if runner is not None
        else build_effective_system_prompt(
            workdir=sandbox_settings.workdir,
            custom_prompt=custom_prompt or None,
            session_id=str(session.id),
            agent_id=str(agent.id),
        )
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

    # Message History
    messages, checkpoint_step = extract_thread_messages(agent.id, session.id, thread)
    history_info = HistoryInspectInfo(
        message_count=len(messages),
        checkpoint_step=checkpoint_step,
        messages=messages,
    )

    # Workspace Files
    data_dir = ws_mgr.get_session_data_dir(agent.id, session.id)
    files: list[str] = []
    if data_dir.exists():
        for p in data_dir.rglob("*"):
            if p.is_file() and p.name != ".gitkeep":
                try:
                    files.append(str(p.relative_to(data_dir)))
                except ValueError:
                    files.append(p.name)
    files.sort()

    workspace_info = WorkspaceInspectInfo(
        operational_dir=sandbox_settings.workdir,
        files=files,
    )

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
        subagents=[],
        history=history_info,
        workspace=workspace_info,
    )
