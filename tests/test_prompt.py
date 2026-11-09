"""Unit tests for structured XML system prompt engineering and dynamic runtime middleware."""

from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from langchain.agents.middleware import ModelRequest, ModelResponse
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from seamus.config.models import AgentConfig, InferenceConfig
from seamus.domain.entities import Agent
from seamus.harness.prompt import (
    DEFAULT_OPERATIONAL_DIR,
    DynamicSystemPromptMiddleware,
    build_communication_style,
    build_default_identity,
    build_dynamic_context,
    build_effective_system_prompt,
    build_engineering_discipline,
    build_operating_environment,
    build_scaffold_prompt,
    build_tool_usage,
)
from seamus.harness.runner import SessionAgentRunner


def test_build_default_identity() -> None:
    identity = build_default_identity()
    assert "Seamus" in identity
    assert "autonomous AI software engineering agent" in identity


def test_build_operating_environment() -> None:
    env_default = build_operating_environment()
    assert env_default.workspace_directory == DEFAULT_OPERATIONAL_DIR
    assert DEFAULT_OPERATIONAL_DIR in env_default.filesystem_persistence
    assert "transient" in env_default.filesystem_persistence.lower()
    assert "sandbox" in env_default.execution_sandbox.lower()

    custom_dir = "/app/workdir"
    env_custom = build_operating_environment(custom_dir)
    assert env_custom.workspace_directory == custom_dir
    assert custom_dir in env_custom.filesystem_persistence


def test_build_engineering_discipline() -> None:
    discipline = build_engineering_discipline()
    assert len(discipline) >= 6
    text = " ".join(discipline).lower()
    assert "investigate before modifying" in text
    assert "surgical" in text
    assert "commentary policy" in text
    assert "scratchpad" in text
    assert "verification before completion" in text


def test_build_tool_usage() -> None:
    tools = build_tool_usage()
    assert len(tools) >= 4
    text = " ".join(tools).lower()
    assert "dedicated tools first" in text
    assert "reserve shell execution" in text
    assert "no colon before tool calls" in text
    assert "direct communication" in text


def test_build_communication_style() -> None:
    styles = build_communication_style()
    assert len(styles) >= 4
    text = " ".join(styles).lower()
    assert "concise" in text
    assert "emoji policy" in text
    assert "markdown" in text
    assert "code citations" in text


def test_build_dynamic_context() -> None:
    fixed_time = datetime(2026, 11, 1, 12, 0, 0, tzinfo=UTC)
    ctx = build_dynamic_context(
        workdir="/workspace",
        session_id="sess-123",
        agent_id="agent-456",
        timestamp=fixed_time,
    )
    assert ctx.current_timestamp == "2026-11-01T12:00:00+00:00"
    assert ctx.operational_workdir == "/workspace"
    assert ctx.session_id == "sess-123"
    assert ctx.agent_id == "agent-456"


def test_build_scaffold_prompt() -> None:
    scaffold = build_scaffold_prompt("/workspace")
    assert "<identity>" in scaffold
    assert "</identity>" in scaffold
    assert "<operating_environment>" in scaffold
    assert "<workspace_directory>/workspace</workspace_directory>" in scaffold
    assert "<engineering_discipline>" in scaffold
    assert "<list>" in scaffold
    assert '<item index="0">' in scaffold
    assert "<tool_usage>" in scaffold
    assert "<communication_style>" in scaffold
    assert "<custom_instructions>" not in scaffold
    assert "<dynamic_context>" not in scaffold


def test_build_effective_system_prompt_with_custom_and_dynamic() -> None:
    fixed_time = datetime(2026, 11, 1, 12, 0, 0, tzinfo=UTC)
    prompt = build_effective_system_prompt(
        workdir="/custom/dir",
        custom_prompt="Always write docstrings.",
        session_id="sess-abc",
        agent_id="agent-def",
        include_dynamic_context=True,
        timestamp=fixed_time,
    )
    assert "<identity>" in prompt
    assert "<workspace_directory>/custom/dir</workspace_directory>" in prompt
    assert "<dynamic_context>" in prompt
    assert "<current_timestamp>2026-11-01T12:00:00+00:00</current_timestamp>" in prompt
    assert "<session_id>sess-abc</session_id>" in prompt
    assert "<agent_id>agent-def</agent_id>" in prompt
    assert "<custom_instructions>" in prompt
    assert "Always write docstrings." in prompt


def test_build_effective_system_prompt_omits_empty_custom() -> None:
    prompt = build_effective_system_prompt(
        workdir="/workspace",
        custom_prompt="",
        include_dynamic_context=False,
    )
    assert "<custom_instructions>" not in prompt
    assert "<dynamic_context>" not in prompt


class _FakeChatModel(BaseChatModel):
    captured_messages: list[list[Any]] = []

    def _generate(
        self,
        messages: list[Any],
        stop: Any = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.captured_messages.append(messages)
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="reply"))])

    async def _agenerate(
        self,
        messages: list[Any],
        stop: Any = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.captured_messages.append(messages)
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="async reply"))])

    @property
    def _llm_type(self) -> str:
        return "fake-chat"

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> Any:
        return self


def test_dynamic_system_prompt_middleware_sync() -> None:
    call_count = 0

    def provider(_req: ModelRequest[Any]) -> str:
        nonlocal call_count
        call_count += 1
        return f"<prompt><turn>{call_count}</turn></prompt>"

    mw = DynamicSystemPromptMiddleware(prompt_provider=provider)
    model = _FakeChatModel()

    req = ModelRequest(
        model=model,
        messages=[HumanMessage(content="hello")],
        system_prompt="initial",
    )

    def handler(overridden_req: ModelRequest[Any]) -> ModelResponse[Any]:
        assert overridden_req.system_message is not None
        assert overridden_req.system_message.content == "<prompt><turn>1</turn></prompt>"
        return ModelResponse([AIMessage(content="done")])

    res = mw.wrap_model_call(req, handler)
    assert isinstance(res, ModelResponse)
    assert res.result[0].content == "done"
    assert call_count == 1


@pytest.mark.asyncio
async def test_dynamic_system_prompt_middleware_async() -> None:
    call_count = 0

    def provider(_req: ModelRequest[Any]) -> str:
        nonlocal call_count
        call_count += 1
        return f"<prompt><turn>{call_count}</turn></prompt>"

    mw = DynamicSystemPromptMiddleware(prompt_provider=provider)
    model = _FakeChatModel()

    req = ModelRequest(
        model=model,
        messages=[HumanMessage(content="hello")],
        system_prompt="initial",
    )

    async def ahandler(overridden_req: ModelRequest[Any]) -> ModelResponse[Any]:
        assert overridden_req.system_message is not None
        assert overridden_req.system_message.content == "<prompt><turn>1</turn></prompt>"
        return ModelResponse([AIMessage(content="async done")])

    res = await mw.awrap_model_call(req, ahandler)
    assert isinstance(res, ModelResponse)
    assert res.result[0].content == "async done"
    assert call_count == 1


def test_session_agent_runner_system_prompts() -> None:
    config = AgentConfig(
        model_name="openai/gpt-4o",
        inference=InferenceConfig(api_key="sk-test", base_url="https://api.openai.com/v1"),
        system_prompt="Custom project instructions.",
    )
    agent = Agent(config=config, name="prompt-test-agent")
    session = agent.create_session(name="prompt-test-session")

    captured_kwargs: dict[str, Any] = {}

    def fake_create_deep_agent(**kwargs: Any) -> MagicMock:
        captured_kwargs.update(kwargs)
        return MagicMock()

    from unittest.mock import patch

    with patch("seamus.harness.runner.create_deep_agent", side_effect=fake_create_deep_agent):
        runner = SessionAgentRunner(session=session, agent_entity=agent)

    # Verify properties
    assert "<identity>" in runner.sandbox_system_prompt
    assert "<workspace_directory>/workspace</workspace_directory>" in runner.sandbox_system_prompt
    assert "<custom_instructions>" not in runner.sandbox_system_prompt

    effective = runner.effective_system_prompt
    assert "<identity>" in effective
    assert "<dynamic_context>" in effective
    assert "<custom_instructions>" in effective
    assert "Custom project instructions." in effective

    # Verify create_deep_agent arguments
    assert "<identity>" in captured_kwargs["system_prompt"]
    assert any(isinstance(m, DynamicSystemPromptMiddleware) for m in captured_kwargs["middleware"])


@pytest.mark.asyncio
async def test_dynamic_prompt_with_todo_list_middleware_composition() -> None:
    """Verify DynamicSystemPromptMiddleware + TodoListMiddleware prompt composition."""
    from langchain.agents.middleware import TodoListMiddleware

    dynamic_mw = DynamicSystemPromptMiddleware(prompt_provider=lambda _req: "<seamus_prompt/>")
    todo_mw = TodoListMiddleware()

    captured_requests: list[ModelRequest[Any]] = []

    async def fake_handler(req: ModelRequest[Any]) -> ModelResponse[Any]:
        captured_requests.append(req)
        return ModelResponse([AIMessage(content="done")])

    req = ModelRequest(
        model=_FakeChatModel(),
        messages=[HumanMessage(content="test")],
        system_prompt="base",
    )

    async def call_todo(r: ModelRequest[Any]) -> ModelResponse[Any]:
        res = await todo_mw.awrap_model_call(r, fake_handler)
        assert isinstance(res, ModelResponse)
        return res

    res = await dynamic_mw.awrap_model_call(req, call_todo)
    assert isinstance(res, ModelResponse)
    assert len(captured_requests) == 1
    final_sys = captured_requests[0].system_message
    assert final_sys is not None

    content_str = str(final_sys.content)
    assert "<seamus_prompt/>" in content_str
    assert "write_todos" in content_str


def test_discover_context_files_ordering_and_deduplication(tmp_path: Path) -> None:
    """Verify discover_context_files ordering, sorting, and deduplication."""
    from seamus.config.models import ExternalRepositoryConfig
    from seamus.harness.prompt import (
        DEFAULT_RULES_PATTERNS,
        discover_context_files,
    )

    workspace_dir = tmp_path / "workspace"
    projects_dir = tmp_path / "projects"
    workspace_dir.mkdir(parents=True)
    projects_dir.mkdir(parents=True)

    # 1. Setup workspace files (with leading/trailing newlines to verify stripping)
    (workspace_dir / "AGENTS.md").write_text(
        "\n\nWorkspace AGENTS instructions\n\n", encoding="utf-8"
    )
    rules_dir = workspace_dir / ".seamus" / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "02-testing.md").write_text("Test rules", encoding="utf-8")
    (rules_dir / "01-architecture.md").write_text("Architecture rules", encoding="utf-8")

    # .git directory in workspace should be ignored
    git_dir = workspace_dir / ".git"
    git_dir.mkdir(parents=True)
    (git_dir / "config").write_text("git config", encoding="utf-8")

    # 2. Setup project files
    repo1_dir = projects_dir / "repo-alpha"
    repo1_dir.mkdir(parents=True)
    (repo1_dir / "AGENTS.md").write_text("Repo Alpha AGENTS", encoding="utf-8")
    repo1_rules = repo1_dir / ".seamus" / "rules"
    repo1_rules.mkdir(parents=True)
    (repo1_rules / "style.md").write_text("Alpha style", encoding="utf-8")

    repo2_dir = projects_dir / "repo-beta"
    repo2_dir.mkdir(parents=True)
    (repo2_dir / "AGENTS.md").write_text("Repo Beta AGENTS", encoding="utf-8")

    repos = [
        ExternalRepositoryConfig(
            id="alpha", url="https://github.com/org/repo-alpha.git", branch="main"
        ),
        ExternalRepositoryConfig(
            id="beta", url="https://github.com/org/repo-beta.git", branch="main"
        ),
    ]

    discovered = discover_context_files(
        workspace_data_dir=workspace_dir,
        repositories=repos,
        projects_dir=projects_dir,
        rules_patterns=DEFAULT_RULES_PATTERNS,
    )

    expected_paths = [
        "/workspace/AGENTS.md",
        "/workspace/.seamus/rules/01-architecture.md",
        "/workspace/.seamus/rules/02-testing.md",
        "/projects/repo-alpha/AGENTS.md",
        "/projects/repo-alpha/.seamus/rules/style.md",
        "/projects/repo-beta/AGENTS.md",
    ]
    actual_paths = [item.path for item in discovered]
    assert actual_paths == expected_paths

    assert discovered[0].content == "Workspace AGENTS instructions"
    assert discovered[1].content == "Architecture rules"
    assert discovered[2].content == "Test rules"
    assert discovered[3].content == "Repo Alpha AGENTS"
    assert discovered[4].content == "Alpha style"
    assert discovered[5].content == "Repo Beta AGENTS"

    # Test deduplication: overlapping patterns should keep earliest match
    overlapping = discover_context_files(
        workspace_data_dir=workspace_dir,
        repositories=repos,
        projects_dir=projects_dir,
        rules_patterns=["AGENTS.md", "**/*.md"],
    )
    # /workspace/AGENTS.md should appear only once (under AGENTS.md, not again under **/*.md)
    ws_agents_matches = [item for item in overlapping if item.path == "/workspace/AGENTS.md"]
    assert len(ws_agents_matches) == 1


def test_discover_context_files_size_and_binary_safeguards(tmp_path: Path) -> None:
    """Verify large files (> max_file_size_bytes) and binary files are skipped safely."""
    from seamus.harness.prompt import discover_context_files

    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir(parents=True)

    # Valid file
    (workspace_dir / "AGENTS.md").write_text("Valid text", encoding="utf-8")

    # Binary file that fails utf-8 decoding
    rules_dir = workspace_dir / ".seamus" / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "binary.bin").write_bytes(b"\x80\xff\xfe\x00\x01\x02")

    # Oversized file
    (rules_dir / "large.md").write_text("X" * 200, encoding="utf-8")

    discovered = discover_context_files(
        workspace_data_dir=workspace_dir,
        rules_patterns=["AGENTS.md", ".seamus/rules/**"],
        max_file_size_bytes=100,  # lower limit for test
    )

    paths = [item.path for item in discovered]
    assert paths == ["/workspace/AGENTS.md"]


def test_discovered_context_prompt_xml_serialization() -> None:
    """Verify system prompt includes <discovered_context> when items exist, omitted when empty."""
    from seamus.harness.prompt import DiscoveredContextItem, build_effective_system_prompt

    # 1. With items
    items = [
        DiscoveredContextItem(path="/workspace/AGENTS.md", content="Follow rules."),
        DiscoveredContextItem(path="/projects/repo/style.md", content="Use snake_case."),
    ]
    prompt_with_items = build_effective_system_prompt(
        discovered_context=items,
        include_dynamic_context=False,
    )
    assert "<discovered_context>" in prompt_with_items
    assert "<path>/workspace/AGENTS.md</path>" in prompt_with_items
    assert "<content>Follow rules.</content>" in prompt_with_items
    assert "<path>/projects/repo/style.md</path>" in prompt_with_items
    assert "<content>Use snake_case.</content>" in prompt_with_items

    # 2. With empty list or None
    prompt_none = build_effective_system_prompt(
        discovered_context=None, include_dynamic_context=False
    )
    assert "<discovered_context>" not in prompt_none

    prompt_empty = build_effective_system_prompt(
        discovered_context=[], include_dynamic_context=False
    )
    assert "<discovered_context>" not in prompt_empty
