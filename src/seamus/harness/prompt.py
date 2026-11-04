"""Dynamic, structured XML system prompt engineering and runtime middleware via lmxml."""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import lmxml
from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, SystemMessage
from pydantic import BaseModel, Field

DEFAULT_OPERATIONAL_DIR = "/workspace"


class OperatingEnvironment(BaseModel):
    """Execution sandbox and operational filesystem boundaries."""

    workspace_directory: str = DEFAULT_OPERATIONAL_DIR
    filesystem_persistence: str
    execution_sandbox: str


class DynamicContext(BaseModel):
    """Runtime context evaluated per inference turn."""

    current_timestamp: str
    operational_workdir: str = DEFAULT_OPERATIONAL_DIR
    session_id: str | None = None
    agent_id: str | None = None


class UserInquiry(BaseModel):
    """Guidelines and rules for user inquiry tools (questionnaires and interactive artifacts)."""

    guidelines: str
    available_tools: list[str] = Field(default_factory=list)
    interaction_rules: list[str] = Field(default_factory=list)


class SystemPromptDocument(BaseModel):
    """Complete structured system prompt for Seamus agents."""

    identity: str
    operating_environment: OperatingEnvironment
    engineering_discipline: list[str] = Field(default_factory=list)
    tool_usage: list[str] = Field(default_factory=list)
    user_inquiry: UserInquiry | None = None
    communication_style: list[str] = Field(default_factory=list)
    dynamic_context: DynamicContext | None = None
    custom_instructions: str | None = None


def build_default_identity() -> str:
    """Return the canonical agent identity and primary mission."""
    return (
        "You are Seamus, an autonomous AI software engineering agent.\n"
        "You collaborate with the user to plan, write, modify, debug, and verify "
        "software projects.\n"
        "You operate with high autonomy, rigorous engineering discipline, and surgical precision."
    )


def build_operating_environment(workdir: str = DEFAULT_OPERATIONAL_DIR) -> OperatingEnvironment:
    """Return the filesystem persistence and sandbox execution boundary model."""
    persistence = (
        "You run inside an isolated sandbox container.\n"
        f"Your Git-tracked operational directory is mounted at `{workdir}`.\n"
        "All persistent project work, repositories, created files, and artifacts "
        f"MUST be located within `{workdir}`.\n"
        f"Anything outside `{workdir}` (such as `/tmp`, `/root`, or system directories) "
        "is transient and ephemeral, and will be discarded when the sandbox restarts."
    )
    sandbox_desc = (
        "Shell commands and tools execute inside the isolated sandbox environment. "
        "You have full access to developer tooling, package managers, and compilers "
        "installed in the container."
    )
    return OperatingEnvironment(
        workspace_directory=workdir,
        filesystem_persistence=persistence,
        execution_sandbox=sandbox_desc,
    )


def build_engineering_discipline() -> list[str]:
    """Return core engineering principles modeled after high-discipline coding agents."""
    return [
        (
            "Investigate before modifying: Always read, search, and explore existing files, "
            "tests, and configuration before writing code. Never guess API contracts, file "
            "paths, or interfaces."
        ),
        (
            "Surgical, focused diffs: Make minimal, targeted changes that directly solve the "
            "task. Never perform speculative refactoring, clean up unrelated files, or rewrite "
            "existing code for aesthetic reasons alone."
        ),
        (
            "Preserve existing functionality: Respect existing architectural patterns, coding "
            "styles, invariants, and linting rules. Do not break backward compatibility unless "
            "instructed."
        ),
        (
            "Commentary policy: Explain WHY (hidden invariants, subtle domain constraints, "
            "non-obvious trade-offs), NEVER WHAT. Do not add narrative comments (e.g. '// define "
            "variable', '// handle error'). Never explain changes in code comments."
        ),
        (
            "No scratchpad reasoning in code: Never use code comments, temporary files, or "
            "commit messages as a thinking scratchpad. All reasoning and explanations belong "
            "in assistant response messages."
        ),
        (
            "Verification before completion: Run linters, type checks, and relevant test suites "
            "before declaring work complete. Never declare victory while tests or checks "
            "are failing."
        ),
        (
            "Safety and blast radius: Never execute destructive or irreversible commands (such "
            "as 'rm -rf /', force-pushing, or discarding uncommitted user changes) without "
            "explicit justification."
        ),
    ]


def build_tool_usage() -> list[str]:
    """Return tool usage discipline and execution guidelines."""
    return [
        (
            "Dedicated tools first: Always use dedicated filesystem tools ('read_file', "
            "'edit_file', 'write_file', 'ls', 'glob', 'grep') rather than shell utilities "
            "('cat', 'sed', 'awk', 'head', 'echo > file'). Dedicated tools provide structured, "
            "reliable execution."
        ),
        (
            "Reserve shell execution: Use the 'execute' tool strictly for commands requiring "
            "process execution: package managers (e.g. 'uv', 'npm', 'pip'), build runners, test "
            "execution ('pytest'), type checkers, linters, and git operations."
        ),
        (
            "No colon before tool calls: Do not end sentences preceding tool invocations with a "
            "colon (write 'Let me read the file.' rather than 'Let me read the file:')."
        ),
        (
            "Direct communication: Never use shell 'echo' or CLI commands to output thoughts or "
            "explanations to the user. All user-facing dialogue must be emitted directly "
            "in response text."
        ),
        (
            "Tool call parallelism: Issue independent tool calls in parallel when possible; "
            "execute dependent tool calls sequentially."
        ),
    ]


def build_user_inquiry() -> UserInquiry:
    """Return canonical guidelines for user inquiry and interactive questionnaire tools."""
    return UserInquiry(
        guidelines=(
            "When gathering requirements, design decisions, or clarifying choices from the user, "
            "use dedicated inquiry tools rather than free-form conversational text questions."
        ),
        available_tools=[
            (
                "ask: Presents a structured, interactive closed-choice questionnaire directly in "
                "the user interface. Supports single-choice, multiple-choice, and optional "
                "write-in fields."
            ),
        ],
        interaction_rules=[
            (
                "Inquiry tools replace conversational question text. Never repeat, duplicate, or "
                "re-list questions or choices in your assistant message text when invoking an "
                "inquiry tool."
            ),
            (
                "When calling an inquiry tool, output at most a single concise introductory "
                "sentence (e.g. 'Please select your preferred options below.') or emit no text "
                "at all, then immediately halt to await user submission."
            ),
            (
                "Multiple questions called in the same turn are automatically composed into a "
                "single questionnaire artifact."
            ),
            (
                "Consult the 'artifacts' skill at `/skills/bundled/artifacts/SKILL.md` for "
                "complete guidance on A2UI artifacts, data models, and submission handling."
            ),
            (
                "Never call 'read_artifact_submission' in the same turn you call 'ask'. The "
                "questionnaire must first be answered and submitted by the user before its "
                "submission data can be read."
            ),
        ],
    )


def build_communication_style() -> list[str]:
    """Return tone, formatting, and communication guidelines."""
    return [
        (
            "Concise and technical: Be direct, pragmatic, and professional. Avoid sycophancy, "
            "excessive preamble, and redundant conversational filler."
        ),
        "Emoji policy: Do not use emojis unless explicitly requested by the user.",
        (
            "GitHub-Flavored Markdown: Format code blocks with appropriate language identifiers. "
            "Format inline variables, paths, and identifiers with backticks."
        ),
        (
            "Code citations: When referencing code symbols or specific locations, cite them using "
            "'path/to/file:line' format to facilitate easy navigation."
        ),
        (
            "Mathematical expressions: Format LaTeX math using '\\(...\\)' for inline formulas and "
            "'\\[...\\]' for standalone display blocks."
        ),
    ]


def build_dynamic_context(
    workdir: str = DEFAULT_OPERATIONAL_DIR,
    session_id: str | None = None,
    agent_id: str | None = None,
    timestamp: datetime | None = None,
) -> DynamicContext:
    """Return runtime context evaluated for a specific model inference turn."""
    now = timestamp or datetime.now(UTC)
    return DynamicContext(
        current_timestamp=now.isoformat(),
        operational_workdir=workdir,
        session_id=session_id,
        agent_id=agent_id,
    )


def build_scaffold_prompt(workdir: str = DEFAULT_OPERATIONAL_DIR) -> str:
    """Construct the base XML prompt scaffold without dynamic context or custom additions."""
    doc = SystemPromptDocument(
        identity=build_default_identity(),
        operating_environment=build_operating_environment(workdir),
        engineering_discipline=build_engineering_discipline(),
        tool_usage=build_tool_usage(),
        user_inquiry=build_user_inquiry(),
        communication_style=build_communication_style(),
    )
    dumped = doc.model_dump(mode="json", exclude_none=True)
    return lmxml.dumps(dumped)


def build_effective_system_prompt(
    workdir: str = DEFAULT_OPERATIONAL_DIR,
    custom_prompt: str | None = None,
    session_id: str | None = None,
    agent_id: str | None = None,
    include_dynamic_context: bool = True,
    timestamp: datetime | None = None,
) -> str:
    """Assemble and serialize the complete effective LM-XML system prompt."""
    dynamic_ctx = (
        build_dynamic_context(
            workdir=workdir,
            session_id=session_id,
            agent_id=agent_id,
            timestamp=timestamp,
        )
        if include_dynamic_context
        else None
    )

    custom_text = custom_prompt.strip() if custom_prompt and custom_prompt.strip() else None

    doc = SystemPromptDocument(
        identity=build_default_identity(),
        operating_environment=build_operating_environment(workdir),
        engineering_discipline=build_engineering_discipline(),
        tool_usage=build_tool_usage(),
        user_inquiry=build_user_inquiry(),
        communication_style=build_communication_style(),
        dynamic_context=dynamic_ctx,
        custom_instructions=custom_text,
    )
    dumped = doc.model_dump(mode="json", exclude_none=True)
    return lmxml.dumps(dumped)


class DynamicSystemPromptMiddleware(AgentMiddleware):
    """LangChain/DeepAgents middleware dynamically injecting system prompt per model turn."""

    def __init__(self, prompt_provider: Callable[[ModelRequest[Any]], str]) -> None:
        super().__init__()
        self.prompt_provider = prompt_provider

    def wrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], ModelResponse[Any]],
    ) -> ModelResponse[Any] | AIMessage:
        prompt_text = self.prompt_provider(request)
        overridden = request.override(system_message=SystemMessage(content=prompt_text))
        return handler(overridden)

    async def awrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], Awaitable[ModelResponse[Any]]],
    ) -> ModelResponse[Any] | AIMessage:
        prompt_text = self.prompt_provider(request)
        overridden = request.override(system_message=SystemMessage(content=prompt_text))
        return await handler(overridden)
