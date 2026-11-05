"""Dynamic, structured XML system prompt engineering and runtime middleware via lmxml."""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import lmxml
from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, SystemMessage
from pydantic import BaseModel, Field

from seamus.domain.modes import (
    ModeName,
    PlanPhase,
    get_mode_descriptor,
    normalize_mode_and_phase,
    resolve_available_harness_tools,
    resolve_mount_policy,
)

DEFAULT_OPERATIONAL_DIR = "/workspace"


class OperatingEnvironment(BaseModel):
    """Execution sandbox and operational filesystem boundaries."""

    workspace_directory: str = DEFAULT_OPERATIONAL_DIR
    workspace_access: str = "read-write"
    notes_directory: str | None = None
    notes_access: str | None = None
    artifacts_directory: str = "/artifacts"
    artifacts_access: str = "read-only"
    filesystem_persistence: str
    execution_sandbox: str


class PlanDocumentSpec(BaseModel):
    """Specification for authoring the Markdown Plan artifact in Plan/Make phase."""

    overview: str
    required_sections: list[str] = Field(default_factory=list)
    authoring_rules: list[str] = Field(default_factory=list)


class ActivePlanPromptContext(BaseModel):
    """Session-local Plan artifact pointer and handoff context."""

    plan_id: str
    plan_title: str
    plan_artifact_directory: str
    plan_path: str
    notes_directory: str = "/workspace/notes"
    instructions: str


class OperationalModeSection(BaseModel):
    """Structured mode and phase context injected into the system prompt."""

    mode_name: str
    mode_slug: str
    mode_description: str
    phase_name: str | None = None
    phase_slug: str | None = None
    phase_description: str | None = None
    architecture_and_continuity: list[str] = Field(default_factory=list)
    phase_objectives: list[str] = Field(default_factory=list)
    phase_workflow: list[str] = Field(default_factory=list)
    plan_document_specification: PlanDocumentSpec | None = None
    active_plan_context: ActivePlanPromptContext | None = None
    transition_and_discard_rules: list[str] = Field(default_factory=list)


class DynamicContext(BaseModel):
    """Runtime context evaluated per inference turn."""

    current_timestamp: str
    operational_workdir: str = DEFAULT_OPERATIONAL_DIR
    operational_mode: str = ModeName.CHAT.value
    operational_phase: str | None = None
    active_plan_id: str | None = None
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
    operational_mode: OperationalModeSection
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


def build_operating_environment(
    workdir: str = DEFAULT_OPERATIONAL_DIR,
    mode: str = ModeName.CHAT.value,
    phase: str | None = None,
) -> OperatingEnvironment:
    """Return the filesystem persistence and sandbox execution boundary model."""
    resolved_mode, resolved_phase = normalize_mode_and_phase(mode, phase)
    mount_policy = resolve_mount_policy(resolved_mode, resolved_phase)
    workspace_access = "read-only" if mount_policy.workspace_readonly else "read-write"
    notes_dir = "/workspace/notes" if mount_policy.notes_mounted else None
    notes_access = (
        ("read-only" if mount_policy.notes_readonly else "read-write")
        if mount_policy.notes_mounted
        else None
    )

    if mount_policy.workspace_readonly:
        persistence = (
            "You run inside an isolated sandbox container.\n"
            f"Your Git-tracked operational directory at `{workdir}` is currently mounted "
            "READ-ONLY for this phase, with the exception of `/workspace/notes`.\n"
            + (
                (
                    "Your persistent session notes directory at `/workspace/notes` is mounted "
                    "READ-WRITE. Record and organize all requirements, architectural findings, "
                    "and user decisions inside `/workspace/notes` so subsequent phases can "
                    "read them.\n"
                )
                if notes_access == "read-write"
                else (
                    "Your session notes directory at `/workspace/notes` is mounted READ-ONLY "
                    "for reference.\n"
                )
            )
            + "Renderable Adaptive Cards artifacts are mounted READ-ONLY at `/artifacts`.\n"
            f"Anything outside `{workdir}` and `/artifacts` (such as `/tmp` or `/root`) "
            "is transient and ephemeral, and will be discarded when the sandbox restarts."
        )
    else:
        persistence = (
            "You run inside an isolated sandbox container.\n"
            f"Your Git-tracked operational directory is mounted READ-WRITE at `{workdir}`.\n"
            "All persistent project work, repositories, created files, and deliverables "
            f"MUST be located within `{workdir}`.\n"
            + (
                "Your session notes from earlier planning phases are located at `/workspace/notes` "
                "and approved plan artifacts are mounted READ-ONLY at `/artifacts/plans/`.\n"
                if notes_dir
                else ""
            )
            + f"Anything outside `{workdir}` (such as `/tmp`, `/root`, or system directories) "
            "is transient and ephemeral, and will be discarded when the sandbox restarts."
        )

    sandbox_desc = (
        "Shell commands and tools execute inside the isolated sandbox environment. "
        "You have full access to developer tooling, package managers, and compilers "
        "installed in the container."
    )
    return OperatingEnvironment(
        workspace_directory=workdir,
        workspace_access=workspace_access,
        notes_directory=notes_dir,
        notes_access=notes_access,
        artifacts_directory="/artifacts",
        artifacts_access="read-only",
        filesystem_persistence=persistence,
        execution_sandbox=sandbox_desc,
    )


def build_plan_document_specification() -> PlanDocumentSpec:
    """Return structured Markdown specification for authoring plans in Plan/Make phase."""
    return PlanDocumentSpec(
        overview=(
            "The implementation plan is a clean, self-contained GitHub-Flavored Markdown "
            "document rendered in a dedicated Plan tab with a Proceed button. It serves as "
            "the authoritative blueprint for the Execute phase, which runs in a fresh thread "
            "with zero prior chat history."
        ),
        required_sections=[
            (
                "Context & Goal: Concisely state the problem being solved, user requirements "
                "synthesized from notes and findings in `/workspace`, and the intended outcome."
            ),
            (
                "Key Decisions & Constraints: Document resolved architectural choices, agreed "
                "trade-offs, and invariants established during the Discuss phase."
            ),
            (
                "Proposed Changes: Group changes by subsystem or component. For every file to "
                "create, modify, or delete, cite its exact path (`path/to/file`), the functions, "
                "classes, or interfaces involved, and existing utilities to reuse."
            ),
            (
                "Verification Plan: Specify exact automated test commands, linter/type-check "
                "invocations, and concrete test scenarios that Execute must run."
            ),
        ],
        authoring_rules=[
            (
                "Ground every file path, symbol name, and data flow in actual inspection of "
                "`/workspace` and the requirement notes gathered during Discuss."
            ),
            (
                "Keep the plan surgical and high-signal: describe interfaces, contracts, and "
                "key logic clearly without dumping complete multi-hundred-line source files."
            ),
            (
                "Ensure the plan is completely self-sufficient so an engineer waking up in the "
                "Execute thread with no conversation history can execute it end-to-end."
            ),
        ],
    )


def build_operational_mode_section(
    mode: str = ModeName.CHAT.value,
    phase: str | None = None,
    *,
    active_plan_id: str | None = None,
    active_plan_title: str | None = None,
) -> OperationalModeSection:
    """Construct the structured OperationalModeSection for the given mode and phase."""
    resolved_mode, resolved_phase = normalize_mode_and_phase(mode, phase)
    mode_desc = get_mode_descriptor(resolved_mode)
    phase_desc = mode_desc.get_phase(resolved_phase)

    if resolved_mode == ModeName.CHAT.value or phase_desc is None:
        return OperationalModeSection(
            mode_name=mode_desc.title,
            mode_slug=mode_desc.name,
            mode_description=mode_desc.description,
            phase_objectives=[
                (
                    "Collaborate directly with the user to answer questions, explore the codebase, "
                    "and implement requested changes in `/workspace`."
                ),
                (
                    "Use `ask` when you are genuinely blocked on a user preference or requirement "
                    "that cannot be inferred from the codebase."
                ),
            ],
            phase_workflow=[
                "Inspect relevant files in `/workspace` before proposing or applying edits.",
                "Implement minimal, well-tested changes and verify them with project checks.",
            ],
        )

    architecture_and_continuity = [
        (
            "Plan mode is divided into three sequential phases: Discuss (`plan/discuss`) -> "
            "Make (`plan/make`) -> Execute (`plan/execute`)."
        ),
        (
            "Each phase runs in its own isolated thread with a completely fresh message history "
            "(zero prior chat messages carry over across phases)."
        ),
        (
            "Cross-phase continuity relies strictly on disk state: notes, specifications, "
            "and requirements recorded in `/workspace` during Discuss (read-only in Make, "
            "executed in Execute) and the session-local Plan artifact under "
            "`/artifacts/plans/<plan_id>/` (authored in Make, executed in Execute)."
        ),
    ]

    active_plan_ctx: ActivePlanPromptContext | None = None
    if active_plan_id:
        title_str = active_plan_title or "Plan"
        plan_dir = f"/artifacts/plans/{active_plan_id}"
        plan_path = f"{plan_dir}/plan.md"
        active_plan_ctx = ActivePlanPromptContext(
            plan_id=active_plan_id,
            plan_title=title_str,
            plan_artifact_directory=plan_dir,
            plan_path=plan_path,
            notes_directory="/workspace",
            instructions=(
                f"Active session plan '{title_str}' (id: `{active_plan_id}`) is stored at "
                f"`{plan_path}`. Read `{plan_path}` and `/workspace` "
                "to inspect the full plan and background notes."
            ),
        )

    if phase_desc.name == PlanPhase.DISCUSS.value:
        return OperationalModeSection(
            mode_name=mode_desc.title,
            mode_slug=mode_desc.name,
            mode_description=mode_desc.description,
            phase_name=phase_desc.title,
            phase_slug=phase_desc.name,
            phase_description=phase_desc.description,
            architecture_and_continuity=architecture_and_continuity,
            phase_objectives=[
                (
                    "Explore the codebase in `/workspace` (mounted read-write) to understand "
                    "existing architecture, dependencies, conventions, and constraints."
                ),
                (
                    "Clarify ambiguities, requirements, user preferences, and design trade-offs "
                    "using blocking questionnaires (`ask`), non-blocking tabbed forms (`form`), "
                    "or conversational discussion."
                ),
                (
                    "Record and organize all findings, specifications, constraints, and "
                    "requirements in the workspace. You are free to organize your notes, "
                    "research, and documentation in any directory you choose within `/workspace`."
                ),
                (
                    "CRITICAL BOUNDARY: Do NOT follow user implementation instructions or write "
                    "code to implement the requested feature/fix during this phase. Do NOT "
                    "author the actual Plan artifact during Discuss. Your sole mission in "
                    "Discuss is to collect and record all necessary requirements, context, and "
                    "technical details."
                ),
            ],
            phase_workflow=[
                (
                    "1. Read and search `/workspace` to locate relevant code, existing "
                    "abstractions, affected files, and potential edge cases."
                ),
                (
                    "2. Proactively ask questions and clarify requirements whenever details or "
                    "trade-offs are uncertain. Use `ask` for blocking choices, `form` for "
                    "multi-question surveys, or conversational prose."
                ),
                (
                    "3. Document all collected requirements, user decisions, affected file paths, "
                    "and architectural notes in `/workspace` (using any directory structure of "
                    "your choice). The subsequent Make phase will wake up in a new thread with "
                    "NO chat history and will rely entirely on disk state in `/workspace`."
                ),
                (
                    "4. Once all requirements, technical details, and constraints are collected "
                    "and documented—and NEVER before—call `plan()` to transition the session into "
                    "the Make phase."
                ),
            ],
            transition_and_discard_rules=[
                (
                    "Call `plan()` ONLY after you have thoroughly collected all requirements, "
                    "verified codebase details, and recorded your findings in `/workspace`. "
                    "Calling `plan()` closes the Discuss thread, spawns a new Make thread, and "
                    "wakes the agent to author the Plan artifact."
                ),
                (
                    "Do NOT attempt to author the Plan artifact (via `make_plan`) or implement "
                    "feature code during Discuss; `make_plan` is only available in Make phase."
                ),
                (
                    "Call `discard()` ONLY when explicitly instructed by the user to abandon or "
                    "reset the current planning effort."
                ),
            ],
        )

    if phase_desc.name == PlanPhase.MAKE.value:
        return OperationalModeSection(
            mode_name=mode_desc.title,
            mode_slug=mode_desc.name,
            mode_description=mode_desc.description,
            phase_name=phase_desc.title,
            phase_slug=phase_desc.name,
            phase_description=phase_desc.description,
            architecture_and_continuity=architecture_and_continuity,
            phase_objectives=[
                (
                    "Read the recorded requirement notes, specifications, and codebase findings "
                    "in `/workspace` (mounted read-only) and verify any remaining technical "
                    "details in `/workspace`."
                ),
                (
                    "Author a comprehensive, surgical Markdown implementation plan using "
                    "`make_plan(content, name)` (or refine the existing session plan using "
                    "`update_plan(content)` and `edit_plan(old_string, new_string)`)."
                ),
            ],
            phase_workflow=[
                (
                    "1. Start by reviewing the requirement notes and findings in `/workspace` to "
                    "recover all requirements, decisions, and context gathered during Discuss."
                ),
                (
                    "2. Inspect `/workspace` as needed to confirm exact file paths, signatures, "
                    "and test patterns."
                ),
                (
                    "3. Call `make_plan(content=..., name=...)` to publish the Plan artifact tab. "
                    "Once `make_plan` is called, `make_plan` is replaced by `update_plan` (full "
                    "Markdown overwrite) and `edit_plan` (targeted string replacement) for "
                    "subsequent refinements."
                ),
                (
                    "4. After creating or updating the plan, briefly inform the user that the "
                    "plan is ready in its tab and await either their feedback in chat or their "
                    "approval via the **Proceed** button."
                ),
            ],
            plan_document_specification=build_plan_document_specification(),
            active_plan_context=active_plan_ctx,
            transition_and_discard_rules=[
                (
                    "There is NO tool to transition from Make to Execute. The user transitions "
                    "the session to Execute by clicking the **Proceed** button on the Plan tab."
                ),
                (
                    "Do NOT repeat the full Markdown plan text in your chat response—the plan is "
                    "rendered directly in the Plan tab."
                ),
                (
                    "Call `discard()` ONLY when explicitly instructed by the user to discard the "
                    "plan and return to a fresh Discuss thread."
                ),
            ],
        )

    # PlanPhase.EXECUTE
    return OperationalModeSection(
        mode_name=mode_desc.title,
        mode_slug=mode_desc.name,
        mode_description=mode_desc.description,
        phase_name=phase_desc.title,
        phase_slug=phase_desc.name,
        phase_description=phase_desc.description,
        architecture_and_continuity=architecture_and_continuity,
        phase_objectives=[
            (
                "Read the approved implementation plan from `/artifacts/plans/` and supporting "
                "notes and specifications in `/workspace`."
            ),
            (
                "Execute the plan systematically in `/workspace` (now mounted read-write) and "
                "run all verification checks specified in the plan."
            ),
        ],
        phase_workflow=[
            (
                "1. Immediately read the active plan artifact (pointed to in "
                "`active_plan_context` or under `/artifacts/plans/`) and inspect supporting "
                "notes in `/workspace` if additional context is needed."
            ),
            (
                "2. Implement each planned change surgically in `/workspace`, following existing "
                "codebase conventions and invariants."
            ),
            (
                "3. Run the test suite, linters, and type checks specified in the plan's "
                "Verification Plan section until all checks pass."
            ),
            (
                "4. Present a concise summary of the completed implementation and verification "
                "results so the user can review and accept the Sync PR."
            ),
        ],
        active_plan_context=active_plan_ctx,
        transition_and_discard_rules=[
            (
                "When the user accepts the Sync PR in the Changes tab, the active plan artifact "
                "is automatically closed, changes are merged, and a new Discuss thread opens."
            ),
            (
                "Call `discard()` ONLY when explicitly instructed by the user to abort execution, "
                "discard the active plan, and return to Discuss."
            ),
        ],
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


def build_user_inquiry(
    mode: str = ModeName.CHAT.value,
    phase: str | None = None,
) -> UserInquiry | None:
    """Return mode- and phase-aware guidelines for user inquiry tools, or None when omitted."""
    resolved_mode, resolved_phase = normalize_mode_and_phase(mode, phase)
    available = resolve_available_harness_tools(resolved_mode, resolved_phase)

    if "ask" not in available and "form" not in available:
        return None

    tools_list: list[str] = []
    if "ask" in available:
        tools_list.append(
            "ask: Presents an embedded, blocking closed-choice questionnaire directly in the "
            "chat stream (`exposition=embedded`, `cadence=blocking`). Best for 1-4 focused "
            "questions that must be answered before proceeding."
        )
    if "form" in available:
        tools_list.append(
            "form: Presents a tabbed, non-blocking questionnaire in a dedicated tab to the "
            "right of Changes (`exposition=tabbed`, `cadence=nonblocking`). Best in Discuss "
            "phase when offering a structured multi-question survey while allowing the user to "
            "continue freestyle chat before or alongside submitting the form."
        )

    guidelines = (
        "When gathering requirements, design decisions, or clarifying choices from the user, "
        "use the available inquiry tools (`ask`"
        + (" or `form`, or freestyle conversation" if "form" in available else "")
        + ")."
    )

    return UserInquiry(
        guidelines=guidelines,
        available_tools=tools_list,
        interaction_rules=[
            (
                "Inquiry tools replace conversational question text. Never repeat, duplicate, or "
                "re-list questions or choices in your assistant message text when invoking an "
                "inquiry tool."
            ),
            (
                "When calling `ask`, output at most a single concise introductory sentence "
                "(e.g. 'Please select your preferred options below.') or emit no text at all, "
                "then immediately halt to await user submission."
            ),
            (
                "Multiple `ask` calls or multiple `form` calls in the same turn are automatically "
                "batched into a single questionnaire or form artifact."
            ),
            (
                "Consult the 'artifacts' skill at `/skills/bundled/artifacts/SKILL.md` for "
                "guidance on Adaptive Cards artifacts, schemas, and submission handling."
            ),
            (
                "Never call 'read_artifact_submission' in the same turn you call 'ask' or 'form'. "
                "The artifact must first be answered and submitted by the user before its "
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
    mode: str = ModeName.CHAT.value,
    phase: str | None = None,
    active_plan_id: str | None = None,
) -> DynamicContext:
    """Return runtime context evaluated for a specific model inference turn."""
    now = timestamp or datetime.now(UTC)
    resolved_mode, resolved_phase = normalize_mode_and_phase(mode, phase)
    return DynamicContext(
        current_timestamp=now.isoformat(),
        operational_workdir=workdir,
        operational_mode=resolved_mode,
        operational_phase=resolved_phase,
        active_plan_id=active_plan_id,
        session_id=session_id,
        agent_id=agent_id,
    )


def build_scaffold_prompt(
    workdir: str = DEFAULT_OPERATIONAL_DIR,
    mode: str = ModeName.CHAT.value,
    phase: str | None = None,
    *,
    active_plan_id: str | None = None,
    active_plan_title: str | None = None,
) -> str:
    """Construct the base XML prompt scaffold without dynamic context or custom additions."""
    doc = SystemPromptDocument(
        identity=build_default_identity(),
        operating_environment=build_operating_environment(workdir, mode=mode, phase=phase),
        operational_mode=build_operational_mode_section(
            mode=mode,
            phase=phase,
            active_plan_id=active_plan_id,
            active_plan_title=active_plan_title,
        ),
        engineering_discipline=build_engineering_discipline(),
        tool_usage=build_tool_usage(),
        user_inquiry=build_user_inquiry(mode=mode, phase=phase),
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
    mode: str = ModeName.CHAT.value,
    phase: str | None = None,
    active_plan_id: str | None = None,
    active_plan_title: str | None = None,
) -> str:
    """Assemble and serialize the complete effective LM-XML system prompt."""
    dynamic_ctx = (
        build_dynamic_context(
            workdir=workdir,
            session_id=session_id,
            agent_id=agent_id,
            timestamp=timestamp,
            mode=mode,
            phase=phase,
            active_plan_id=active_plan_id,
        )
        if include_dynamic_context
        else None
    )

    custom_text = custom_prompt.strip() if custom_prompt and custom_prompt.strip() else None

    doc = SystemPromptDocument(
        identity=build_default_identity(),
        operating_environment=build_operating_environment(workdir, mode=mode, phase=phase),
        operational_mode=build_operational_mode_section(
            mode=mode,
            phase=phase,
            active_plan_id=active_plan_id,
            active_plan_title=active_plan_title,
        ),
        engineering_discipline=build_engineering_discipline(),
        tool_usage=build_tool_usage(),
        user_inquiry=build_user_inquiry(mode=mode, phase=phase),
        communication_style=build_communication_style(),
        dynamic_context=dynamic_ctx,
        custom_instructions=custom_text,
    )
    dumped = doc.model_dump(mode="json", exclude_none=True)
    return lmxml.dumps(dumped)


class DynamicSystemPromptMiddleware(AgentMiddleware):
    """LangChain/DeepAgents middleware dynamically injecting prompt, tools, and trigger messages."""

    def __init__(
        self,
        prompt_provider: Callable[[ModelRequest[Any]], str],
        tools_provider: Callable[[ModelRequest[Any]], list[Any]] | None = None,
        messages_provider: Callable[[ModelRequest[Any]], list[Any] | None] | None = None,
        should_short_circuit: Callable[[ModelRequest[Any]], bool] | None = None,
    ) -> None:
        super().__init__()
        self.prompt_provider = prompt_provider
        self.tools_provider = tools_provider
        self.messages_provider = messages_provider
        self.should_short_circuit = should_short_circuit

    def _build_overridden_request(self, request: ModelRequest[Any]) -> ModelRequest[Any]:
        prompt_text = self.prompt_provider(request)
        overrides: dict[str, Any] = {
            "system_message": SystemMessage(content=prompt_text),
        }
        if self.tools_provider is not None:
            overrides["tools"] = self.tools_provider(request)
        if self.messages_provider is not None:
            override_msgs = self.messages_provider(request)
            if override_msgs is not None:
                overrides["messages"] = override_msgs
        return request.override(**overrides)

    def wrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], ModelResponse[Any]],
    ) -> ModelResponse[Any] | AIMessage:
        if self.should_short_circuit is not None and self.should_short_circuit(request):
            return ModelResponse([AIMessage(content="")])
        overridden = self._build_overridden_request(request)
        return handler(overridden)

    async def awrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], Awaitable[ModelResponse[Any]]],
    ) -> ModelResponse[Any] | AIMessage:
        if self.should_short_circuit is not None and self.should_short_circuit(request):
            return ModelResponse([AIMessage(content="")])
        overridden = self._build_overridden_request(request)
        return await handler(overridden)
