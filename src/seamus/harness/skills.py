"""First-party native skills system for Seamus.

Provides resilient frontmatter parsing, implementation-agnostic discovery and
precedence resolution (INV-035), dynamic LM-XML prompt integration, and explicit
load_skill / unload_skill agent tools.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from typing import Any
from uuid import UUID

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelRequest, ModelResponse, ResponseT
from langchain_core.messages import AIMessage
from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, ConfigDict, Field

from seamus.config.models import (
    ArtifactsImplementation,
    ExternalRepositoryConfig,
    SkillsImplementation,
)
from seamus.config.settings import get_system_settings_store, resolve_skill_path
from seamus.domain.entities import Thread
from seamus.harness.sandbox import BUNDLED_SKILLS_DIR, get_sandbox_settings
from seamus.persistence.external_repo import calculate_mount_paths, get_external_repo_manager
from seamus.persistence.workspace import get_workspace_manager

logger = logging.getLogger(__name__)

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*(?:\n(.*))?$", re.DOTALL)


class DiscoveredSkill(BaseModel):
    """Information about a discovered skill across workspace, project, and system layers."""

    model_config = ConfigDict(populate_by_name=True)

    name: str
    description: str
    origin_layer: str
    sandbox_path: str
    host_path: str | None = None
    instructions: str
    allowed_tools: list[str] = Field(default_factory=list)
    active: bool = True
    loaded: bool = False
    content: str = ""

    def __init__(self, **data: Any) -> None:
        if "content" not in data and "instructions" in data:
            data["content"] = data["instructions"]
        elif "instructions" not in data and "content" in data:
            data["instructions"] = data["content"]
        super().__init__(**data)


def parse_skill_markdown(raw_text: str, default_name: str) -> tuple[str, str, str, list[str]]:
    """Parse SKILL.md frontmatter and body resiliently, handling unquoted colons and lists."""
    match = _FRONTMATTER_RE.match(raw_text)
    if not match:
        return default_name, "", raw_text.strip(), []

    fm_text = match.group(1)
    body = (match.group(2) or "").strip()

    parsed: dict[str, Any] = {}
    current_key: str | None = None
    current_val_lines: list[str] = []
    current_is_list: bool = False
    list_items: list[str] = []

    for line in fm_text.splitlines():
        list_match = re.match(r"^\s*-\s+(.*)$", line)
        if list_match and current_key is not None:
            current_is_list = True
            list_items.append(list_match.group(1).strip().strip("\"'"))
            continue

        key_match = re.match(r"^([A-Za-z0-9_-]+)\s*:\s*(.*)$", line)
        if key_match:
            if current_key is not None:
                if current_is_list:
                    parsed[current_key] = list(list_items)
                else:
                    parsed[current_key] = " ".join(current_val_lines).strip().strip("\"'")
            current_key = key_match.group(1)
            val_part = key_match.group(2).strip()
            current_is_list = False
            list_items = []
            if val_part.startswith("[") and val_part.endswith("]"):
                inner = val_part[1:-1].strip()
                if inner:
                    parsed[current_key] = [
                        item.strip().strip("\"'") for item in inner.split(",") if item.strip()
                    ]
                else:
                    parsed[current_key] = []
                current_key = None
            else:
                current_val_lines = (
                    [] if val_part in (">", "|", ">-", "|-") else ([val_part] if val_part else [])
                )
        elif current_key is not None and (line.startswith(" ") or line.startswith("\t")):
            current_val_lines.append(line.strip())

    if current_key is not None:
        if current_is_list:
            parsed[current_key] = list(list_items)
        else:
            parsed[current_key] = " ".join(current_val_lines).strip().strip("\"'")

    name = str(parsed.get("name") or default_name).strip() or default_name
    description = str(parsed.get("description") or "").strip()

    raw_tools = parsed.get("allowed_tools") or parsed.get("tools") or []
    if isinstance(raw_tools, str):
        allowed_tools = [t.strip().strip("\"'") for t in raw_tools.split(",") if t.strip()]
    elif isinstance(raw_tools, list):
        allowed_tools = [str(t).strip().strip("\"'") for t in raw_tools if str(t).strip()]
    else:
        allowed_tools = []

    return name, description, body, allowed_tools


ARTIFACT_RELATED_SKILLS: frozenset[str] = frozenset({"artifacts", "a2ui_components"})


def discover_session_skills(
    agent_id: UUID,
    session_id: UUID,
    skills_implementation: SkillsImplementation,
    repositories: Sequence[ExternalRepositoryConfig] | None = None,
    active_skill_names: Sequence[str] | None = None,
    artifacts_implementation: ArtifactsImplementation = ArtifactsImplementation.SEAMUS,
) -> list[DiscoveredSkill]:
    """Discover skills across workspace, mounted projects, and system directories.

    Enforces the implementation-agnostic precedence hierarchy (INV-035):
    1. /skills/bundled (bundled platform skills)
    2. /workspace/skills
    3. /workspace/.skills
    4. /projects/{mount_name}/skills, /projects/{mount_name}/.skills (in repository order)
    5. /skills/system/0, /skills/system/1, ... (system-wide host skill directories)
    """
    if skills_implementation == SkillsImplementation.NONE:
        return []

    ws_mgr = get_workspace_manager()
    sandbox_settings = get_sandbox_settings()
    system_settings = get_system_settings_store().get_settings()
    data_dir = ws_mgr.get_session_data_dir(agent_id, session_id)
    workdir = sandbox_settings.workdir.rstrip("/")

    search_roots: list[tuple[Path, str, str, bool]] = []
    if BUNDLED_SKILLS_DIR.is_dir():
        search_roots.append((BUNDLED_SKILLS_DIR, "/skills/bundled", "Bundled", True))
    search_roots.append((data_dir / "skills", f"{workdir}/skills", "Session (skills)", False))
    search_roots.append((data_dir / ".skills", f"{workdir}/.skills", "Session (.skills)", False))

    if repositories:
        ext_mgr = get_external_repo_manager()
        projects_dir = ext_mgr.get_session_projects_dir(agent_id, session_id)
        mount_paths = calculate_mount_paths(list(repositories))
        for repo in repositories:
            mount_name = mount_paths.get(repo.id, "repo")
            host_repo_dir = projects_dir / mount_name
            search_roots.append(
                (
                    host_repo_dir / "skills",
                    f"/projects/{mount_name}/skills",
                    f"Project {mount_name}",
                    False,
                )
            )
            search_roots.append(
                (
                    host_repo_dir / ".skills",
                    f"/projects/{mount_name}/.skills",
                    f"Project {mount_name} (.skills)",
                    False,
                )
            )

    for idx, skill_dir_str in enumerate(system_settings.skill_directories):
        resolved = resolve_skill_path(skill_dir_str)
        if resolved is not None:
            label = (
                f"System #{idx} ({skill_dir_str})"
                if len(system_settings.skill_directories) > 1
                else f"System ({skill_dir_str})"
            )
            search_roots.append((resolved, f"/skills/system/{idx}", label, True))

    active_set = set(active_skill_names or [])
    seen_names: set[str] = set()
    discovered: list[DiscoveredSkill] = []

    for host_root, sandbox_root, origin_label, is_host_mounted in search_roots:
        if not host_root.exists() or not host_root.is_dir():
            continue

        skill_files = sorted(
            (p for p in host_root.rglob("SKILL.md") if p.is_file()),
            key=lambda p: str(p.relative_to(host_root)),
        )
        for skill_file in skill_files:
            try:
                raw_text = skill_file.read_text(encoding="utf-8")
            except Exception:
                continue
            rel_path = skill_file.relative_to(host_root).as_posix()
            default_name = (
                skill_file.parent.name if skill_file.parent != host_root else skill_file.stem
            )
            name, description, body, allowed_tools = parse_skill_markdown(raw_text, default_name)
            if (
                artifacts_implementation == ArtifactsImplementation.NONE
                and name in ARTIFACT_RELATED_SKILLS
            ):
                continue
            is_active = name not in seen_names
            seen_names.add(name)
            is_loaded = is_active and (name in active_set)

            discovered.append(
                DiscoveredSkill(
                    name=name,
                    description=description,
                    origin_layer=origin_label,
                    sandbox_path=f"{sandbox_root}/{rel_path}",
                    host_path=str(skill_file) if is_host_mounted else None,
                    instructions=body,
                    allowed_tools=allowed_tools,
                    active=is_active,
                    loaded=is_loaded,
                )
            )

    return discovered


class LoadSkillInput(BaseModel):
    """Input schema for load_skill tool."""

    name: str = Field(description="Name of the available skill to load into system prompt.")


class UnloadSkillInput(BaseModel):
    """Input schema for unload_skill tool."""

    name: str = Field(description="Exact name of the currently loaded skill to unload.")


class SeamusSkillsMiddleware(AgentMiddleware[Any, Any, Any]):
    """Native skills middleware providing explicit load/unload tools and tool gating."""

    def __init__(
        self,
        get_thread: Callable[[], Thread | None],
        discovered_skills_provider: Callable[[], list[DiscoveredSkill]],
        on_skills_changed: Callable[[list[str]], None] | None = None,
    ) -> None:
        super().__init__()
        self.get_thread = get_thread
        self.discovered_skills_provider = discovered_skills_provider
        self.on_skills_changed = on_skills_changed

        self.tools: list[BaseTool] = [
            StructuredTool.from_function(
                name="load_skill",
                description=(
                    "Load a skill from available skills into your active system prompt, "
                    "unlocking its specialized instructions and any associated tools."
                ),
                func=self.handle_load_skill,
                args_schema=LoadSkillInput,
            ),
            StructuredTool.from_function(
                name="unload_skill",
                description=(
                    "Unload an active skill from your system prompt once its workflow is "
                    "complete, freeing context window tokens."
                ),
                func=self.handle_unload_skill,
                args_schema=UnloadSkillInput,
            ),
        ]

    def _get_active_thread(self) -> Thread:
        thread = self.get_thread()
        if thread is None:
            raise RuntimeError("No active thread available for skill operation.")
        return thread

    def handle_load_skill(self, name: str) -> str:
        """Activate a skill by name in the current thread."""
        thread = self._get_active_thread()
        clean_name = name.strip()
        all_skills = self.discovered_skills_provider()
        available_map = {s.name: s for s in all_skills if s.active}

        if clean_name not in available_map:
            available_names = sorted(available_map.keys())
            return (
                f"Error: Skill '{clean_name}' not found or shadowed. "
                f"Available skills: {', '.join(available_names) if available_names else 'none'}"
            )

        if clean_name in thread.active_skills:
            return f"Skill '{clean_name}' is already loaded and active in your system prompt."

        thread.active_skills.append(clean_name)
        if self.on_skills_changed:
            self.on_skills_changed(list(thread.active_skills))

        skill = available_map[clean_name]
        tools_msg = ""
        if skill.allowed_tools:
            tools_msg = f" and associated tools ({', '.join(skill.allowed_tools)})"
        return (
            f"Skill '{clean_name}' loaded successfully. Its instructions{tools_msg} "
            "are now active in your system prompt."
        )

    def handle_unload_skill(self, name: str) -> str:
        """Deactivate a skill by name in the current thread."""
        thread = self._get_active_thread()
        clean_name = name.strip()

        if clean_name not in thread.active_skills:
            return f"Skill '{clean_name}' is not currently loaded."

        thread.active_skills = [s for s in thread.active_skills if s != clean_name]
        if self.on_skills_changed:
            self.on_skills_changed(list(thread.active_skills))

        return f"Skill '{clean_name}' unloaded successfully."

    def wrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], ModelResponse[ResponseT]],
    ) -> ModelResponse[ResponseT] | AIMessage:
        return handler(request)

    async def awrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], Awaitable[ModelResponse[ResponseT]]],
    ) -> ModelResponse[ResponseT] | AIMessage:
        return await handler(request)
