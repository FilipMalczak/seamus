"""Dynamic, structured XML system prompt engineering and runtime middleware via lmxml."""

import logging
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import lmxml
from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, SystemMessage
from pydantic import BaseModel, Field

from seamus.config.models import ArtifactsImplementation, ExternalRepositoryConfig
from seamus.domain.modes import (
    ModeName,
    PlanPhase,
    get_mode_descriptor,
    normalize_mode_and_phase,
    resolve_available_harness_tools,
    resolve_mount_policy,
)
from seamus.persistence.external_repo import calculate_mount_paths

logger = logging.getLogger(__name__)

DEFAULT_OPERATIONAL_DIR = "/workspace"
DEFAULT_RULES_PATTERNS: list[str] = ["AGENTS.md", ".seamus/rules/**"]


class OperatingEnvironment(BaseModel):
    """Execution sandbox and operational filesystem boundaries."""

    workspace_directory: str = DEFAULT_OPERATIONAL_DIR
    workspace_access: str = "read-write"
    projects_directory: str = "/projects"
    projects_access: str = "read-write"
    notes_directory: str | None = None
    notes_access: str | None = None
    artifacts_directory: str | None = "/artifacts"
    artifacts_access: str | None = "read-only"
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


class DiscoveredContextItem(BaseModel):
    """File path and contents discovered from workspace and mounted external repositories."""

    path: str
    content: str


class AvailableSkillPromptItem(BaseModel):
    """Metadata for an available skill rendered in LM-XML."""

    name: str
    description: str


class ActiveSkillPromptItem(BaseModel):
    """Active skill body rendered in LM-XML without XML attributes."""

    name: str
    instructions: str


def build_default_skills_guidelines() -> list[str]:
    """Default progressive disclosure guidelines for native skills in LM-XML."""
    return [
        "Skills provide specialized workflows and domain expertise.",
        "Check available skills to see if one matches your current task.",
        (
            "Call `load_skill(name=...)` to load its full instructions and associated "
            "tools into your system prompt."
        ),
        (
            "Call `unload_skill(name=...)` once the specific skill workflow is completed "
            "to conserve context tokens."
        ),
    ]


class SkillsPromptDocument(BaseModel):
    """Structured skills catalog and loaded instructions rendered in LM-XML."""

    available_skills: list[AvailableSkillPromptItem]
    active_skills: list[ActiveSkillPromptItem] | None = None
    guidelines: list[str] = Field(default_factory=build_default_skills_guidelines)


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
    discovered_context: list[DiscoveredContextItem] | None = None
    skills: SkillsPromptDocument | None = None
    plan: str | None = None
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
    artifacts_implementation: ArtifactsImplementation = ArtifactsImplementation.SEAMUS,
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
    artifacts_enabled = artifacts_implementation != ArtifactsImplementation.NONE

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
            + (
                "Renderable A2UI artifacts are mounted READ-ONLY at `/artifacts`.\n"
                f"Anything outside `{workdir}` and `/artifacts` (such as `/tmp` or `/root`) "
                "is transient and ephemeral, and will be discarded when the sandbox restarts."
                if artifacts_enabled
                else f"Anything outside `{workdir}` (such as `/tmp` or `/root`) "
                "is transient and ephemeral, and will be discarded when the sandbox restarts."
            )
        )
    else:
        persistence = (
            "You run inside an isolated sandbox container.\n"
            f"Your Git-tracked operational directory is mounted READ-WRITE at `{workdir}`.\n"
            "All persistent project work, repositories, created files, and deliverables "
            f"MUST be located within `{workdir}`.\n"
            + (
                (
                    "Your session notes from earlier planning phases are located at "
                    "`/workspace/notes` and approved plan artifacts are mounted "
                    "READ-ONLY at `/artifacts/plans/`.\n"
                    if artifacts_enabled
                    else (
                        "Your session notes from earlier planning phases are located at "
                        "`/workspace/notes`.\n"
                    )
                )
                if notes_dir
                else ""
            )
            + f"Anything outside `{workdir}` (such as `/tmp`, `/root`, or system directories) "
            "is transient and ephemeral, and will be discarded when the sandbox restarts."
        )

    persistence += (
        f"\nYour operational directory `{workdir}` is governed by Git persistence. "
        "The repository contains a `.gitignore` file that determines which files and directories "
        "are tracked and persisted across commits and session branches. Untracked and ignored "
        "files (such as caches, build artifacts, and virtual environments) remain ephemeral "
        "within the sandbox container.\n"
        "Mounted external Git repositories are located under `/projects/<name>/`. "
        "Directory roles: `/workspace` is your personal scratchpad for session notes, plans, and "
        "temporary scripts. When mounted external repositories exist under `/projects/<name>/`, "
        "`/projects/<name>/` is the canonical working directory for project codebase inspection, "
        "edits, builds, and commits. Do NOT create or modify project codebase files directly "
        "in `/workspace` when working on a mounted repository.\n"
        "Each mounted project is an independent, fully functional Git repository with its own "
        "`.git/`. You can execute standard Git commands (`git status`, `git diff`, `git add`, "
        "`git commit`, `git log`, `git branch`, `git switch`) directly inside `/projects/<name>`. "
        "Automatic persistence snapshots capture both staged and working-tree changes according "
        "to the project's `.gitignore` rules."
    )

    sandbox_desc = (
        "Shell commands and tools execute inside the isolated sandbox environment. "
        "You have full access to developer tooling, package managers, and compilers "
        "installed in the container."
    )
    return OperatingEnvironment(
        workspace_directory=workdir,
        workspace_access=workspace_access,
        projects_directory="/projects",
        projects_access="read-write",
        notes_directory=notes_dir,
        notes_access=notes_access,
        artifacts_directory="/artifacts" if artifacts_enabled else None,
        artifacts_access="read-only" if artifacts_enabled else None,
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
    artifacts_implementation: ArtifactsImplementation = ArtifactsImplementation.SEAMUS,
) -> OperationalModeSection:
    """Construct the structured OperationalModeSection for the given mode and phase."""
    resolved_mode, resolved_phase = normalize_mode_and_phase(mode, phase)
    mode_desc = get_mode_descriptor(resolved_mode)
    phase_desc = mode_desc.get_phase(resolved_phase)
    artifacts_enabled = artifacts_implementation != ArtifactsImplementation.NONE

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
                    if artifacts_enabled
                    else (
                        "Ask the user directly when you are genuinely blocked on a user preference "
                        "or requirement that cannot be inferred from the codebase."
                    )
                ),
            ],
            phase_workflow=[
                "Inspect relevant files in `/workspace` before proposing or applying edits.",
                "Implement minimal, well-tested changes and verify them with project checks.",
            ],
        )

    cross_phase_continuity = (
        "Cross-phase continuity relies strictly on disk state: notes, specifications, "
        "and requirements recorded in `/workspace` during Discuss (read-only in Make, "
        "executed in Execute) and the session-local Plan artifact under "
        "`/artifacts/plans/<plan_id>/` (authored in Make, executed in Execute)."
        if artifacts_enabled
        else "Cross-phase continuity relies strictly on disk state: notes, specifications, "
        "and requirements recorded in `/workspace` during Discuss (read-only in Make, "
        "executed in Execute)."
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
        cross_phase_continuity,
    ]

    active_plan_ctx: ActivePlanPromptContext | None = None
    if active_plan_id and artifacts_enabled:
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

    phase_description = (
        phase_desc.description
        if artifacts_enabled
        else (
            "Explore the workspace with read-write access, clarify requirements and trade-offs "
            "with the user via conversation, and record findings and notes across the workspace "
            "before calling `plan()`."
            if phase_desc.name == PlanPhase.DISCUSS.value
            else (
                "Synthesize the organized notes in `/workspace/notes` and inspect the read-only "
                "`/workspace` to author and refine the session's Markdown implementation plan, "
                "then await user approval."
                if phase_desc.name == PlanPhase.MAKE.value
                else (
                    "Implement and verify the approved plan with full read-write access to "
                    "`/workspace`."
                    if phase_desc.name == PlanPhase.EXECUTE.value
                    else phase_desc.description
                )
            )
        )
    )

    if phase_desc.name == PlanPhase.DISCUSS.value:
        discuss_objectives = [
            (
                "Explore the codebase in `/workspace` (mounted read-write) to understand "
                "existing architecture, dependencies, conventions, and constraints."
            ),
            (
                "Clarify ambiguities, requirements, user preferences, and design trade-offs "
                "using blocking questionnaires (`ask`), non-blocking tabbed forms (`form`), "
                "or conversational discussion."
                if artifacts_enabled
                else "Clarify ambiguities, requirements, user preferences, and design trade-offs "
                "using conversational discussion."
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
                if artifacts_enabled
                else "CRITICAL BOUNDARY: Do NOT follow user implementation instructions or write "
                "code to implement the requested feature/fix during this phase. Do NOT "
                "author the implementation plan during Discuss. Your sole mission in "
                "Discuss is to collect and record all necessary requirements, context, and "
                "technical details."
            ),
        ]
        discuss_workflow = [
            (
                "1. Read and search `/workspace` to locate relevant code, existing "
                "abstractions, affected files, and potential edge cases."
            ),
            (
                "2. Proactively ask questions and clarify requirements whenever details or "
                "trade-offs are uncertain. Use `make_questionnaire` for blocking choices, "
                "`make_form` for multi-question surveys, or conversational prose."
                if artifacts_enabled
                else "2. Proactively ask questions and clarify requirements whenever details or "
                "trade-offs are uncertain using conversational prose."
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
        ]
        discuss_rules = [
            (
                "Call `plan()` ONLY after you have thoroughly collected all requirements, "
                "verified codebase details, and recorded your findings in `/workspace`. "
                "Calling `plan()` closes the Discuss thread, spawns a new Make thread, and "
                "wakes the agent to author the Plan artifact."
                if artifacts_enabled
                else "Call `plan()` ONLY after you have thoroughly collected all requirements, "
                "verified codebase details, and recorded your findings in `/workspace`. "
                "Calling `plan()` closes the Discuss thread, spawns a new Make thread, and "
                "wakes the agent to author the plan."
            ),
            (
                "Do NOT attempt to author the Plan artifact (via `make_plan`) or implement "
                "feature code during Discuss; `make_plan` is only available in Make phase."
                if artifacts_enabled
                else "Do NOT attempt to author the plan or implement feature code during Discuss."
            ),
            (
                "Call `discard()` ONLY when explicitly instructed by the user to abandon or "
                "reset the current planning effort."
            ),
        ]
        return OperationalModeSection(
            mode_name=mode_desc.title,
            mode_slug=mode_desc.name,
            mode_description=mode_desc.description,
            phase_name=phase_desc.title,
            phase_slug=phase_desc.name,
            phase_description=phase_description,
            architecture_and_continuity=architecture_and_continuity,
            phase_objectives=discuss_objectives,
            phase_workflow=discuss_workflow,
            transition_and_discard_rules=discuss_rules,
        )

    if phase_desc.name == PlanPhase.MAKE.value:
        make_objectives = [
            (
                "Read the recorded requirement notes, specifications, and codebase findings "
                "in `/workspace` (mounted read-only) and verify any remaining technical "
                "details in `/workspace`."
            ),
            (
                "Author a comprehensive, surgical Markdown implementation plan using "
                "`make_plan(content, name)` (or refine the existing session plan using "
                "`update_plan(content)` and `edit_plan(old_string, new_string)`)."
                if artifacts_enabled
                else (
                    "Author a comprehensive, surgical Markdown implementation plan in `/workspace`."
                )
            ),
        ]
        make_workflow = [
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
                if artifacts_enabled
                else "3. Document your comprehensive Markdown implementation plan in `/workspace`."
            ),
            (
                "4. After creating or updating the plan, briefly inform the user that the "
                "plan is ready in its tab and await either their feedback in chat or their "
                "approval via the **Proceed** button."
                if artifacts_enabled
                else "4. After creating or updating the plan, briefly inform the user that the "
                "plan is ready and await their feedback or approval in chat."
            ),
        ]
        make_rules = [
            (
                "There is NO tool to transition from Make to Execute. The user transitions "
                "the session to Execute by clicking the **Proceed** button on the Plan tab."
                if artifacts_enabled
                else "There is NO tool to transition from Make to Execute. Await user instructions "
                "to proceed to execution."
            ),
            (
                "Do NOT repeat the full Markdown plan text in your chat response—the plan is "
                "rendered directly in the Plan tab."
                if artifacts_enabled
                else "Present a concise summary of the plan in chat while persisting the full "
                "document in `/workspace`."
            ),
            (
                "Call `discard()` ONLY when explicitly instructed by the user to discard the "
                "plan and return to a fresh Discuss thread."
            ),
        ]
        return OperationalModeSection(
            mode_name=mode_desc.title,
            mode_slug=mode_desc.name,
            mode_description=mode_desc.description,
            phase_name=phase_desc.title,
            phase_slug=phase_desc.name,
            phase_description=phase_description,
            architecture_and_continuity=architecture_and_continuity,
            phase_objectives=make_objectives,
            phase_workflow=make_workflow,
            plan_document_specification=build_plan_document_specification(),
            active_plan_context=active_plan_ctx if artifacts_enabled else None,
            transition_and_discard_rules=make_rules,
        )

    # PlanPhase.EXECUTE
    execute_objectives = [
        (
            "Read the approved implementation plan from `/artifacts/plans/` and supporting "
            "notes and specifications in `/workspace`."
            if artifacts_enabled
            else "Read the approved implementation plan and supporting notes and specifications "
            "in `/workspace`."
        ),
        (
            "Execute the plan systematically in `/workspace` (now mounted read-write) and "
            "run all verification checks specified in the plan."
        ),
    ]
    execute_workflow = [
        (
            "1. Immediately read the active plan artifact (pointed to in "
            "`active_plan_context` or under `/artifacts/plans/`) and inspect supporting "
            "notes in `/workspace` if additional context is needed."
            if artifacts_enabled
            else "1. Immediately read the plan and inspect supporting notes in `/workspace` "
            "if additional context is needed."
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
    ]
    execute_rules = [
        (
            "When the user accepts the Sync PR in the Changes tab, the active plan artifact "
            "is automatically closed, changes are merged, and a new Discuss thread opens."
            if artifacts_enabled
            else "When the user accepts the Sync PR in the Changes tab, changes are merged, "
            "and a new Discuss thread opens."
        ),
        (
            "Call `discard()` ONLY when explicitly instructed by the user to abort execution, "
            "discard the active plan, and return to Discuss."
        ),
    ]
    return OperationalModeSection(
        mode_name=mode_desc.title,
        mode_slug=mode_desc.name,
        mode_description=mode_desc.description,
        phase_name=phase_desc.title,
        phase_slug=phase_desc.name,
        phase_description=phase_description,
        architecture_and_continuity=architecture_and_continuity,
        phase_objectives=execute_objectives,
        phase_workflow=execute_workflow,
        active_plan_context=active_plan_ctx if artifacts_enabled else None,
        transition_and_discard_rules=execute_rules,
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
        (
            "Task planning and execution: When task planning tools ('create_todo_item', "
            "'edit_todo_item', 'delete_todo_item') are available, use them to maintain your "
            "hierarchical task plan. Reference items strictly by their 4-hex 'id', "
            "never by their advisory 'path'. Mark tasks as [WIP] when starting work and [DONE] "
            "when verified. Tasks can be moved and reordered using 'edit_todo_item' with "
            "'new_parent' and 'new_position'. Note the auto-state rules: closing a parent "
            "(DONE or ABANDONED) auto-closes WIP children with the parent's status and "
            "auto-abandons PENDING children; adding or reopening an item under a DONE parent "
            "auto-reverts the parent (and any completed ancestors) to WIP; use "
            "'new_status=\"abandoned\"' for dropped or skipped tasks (DONE tasks cannot be "
            "abandoned)."
        ),
    ]


def build_user_inquiry(
    mode: str = ModeName.CHAT.value,
    phase: str | None = None,
    artifacts_implementation: ArtifactsImplementation = ArtifactsImplementation.SEAMUS,
) -> UserInquiry | None:
    """Return mode- and phase-aware guidelines for user inquiry tools, or None when omitted."""
    if artifacts_implementation == ArtifactsImplementation.NONE:
        return None
    resolved_mode, resolved_phase = normalize_mode_and_phase(mode, phase)
    available = resolve_available_harness_tools(
        resolved_mode,
        resolved_phase,
        artifacts_implementation=artifacts_implementation,
    )

    if (
        "make_questionnaire" not in available
        and "make_form" not in available
        and "make_artifact" not in available
    ):
        return None

    tools_list: list[str] = []
    if "make_questionnaire" in available:
        tools_list.append(
            "make_questionnaire: Creates an embedded, blocking closed-choice questionnaire "
            "directly in the chat stream (`exposition=embedded`, `blocking=True`). Best for "
            "focused questions that must be answered before proceeding."
        )
    if "make_form" in available:
        tools_list.append(
            "make_form: Creates a tabbed, non-blocking questionnaire form in a dedicated tab "
            "to the right of Changes (`exposition=tabbed`, `blocking=False`). Best in Discuss "
            "phase when offering a structured multi-question survey while allowing the user to "
            "continue freestyle chat before or alongside submitting the form."
        )
    if "make_artifact" in available:
        tools_list.append(
            "make_artifact: Core atomic artifact builder creating custom A2UI components under "
            "`/artifacts/<family>/<uuid>/` with custom manifest and body definitions. Button "
            "clicks automatically capture a snapshot of all input widgets into append-only JSONL "
            "event logs and state.json."
        )
    if "wait_for_click" in available:
        tools_list.append(
            "wait_for_click: Suspends agent execution within the current turn until the user "
            "clicks a button on the specified artifact. Returns the clicked button ID, event name, "
            "input data snapshot, and static context."
        )

    guidelines = (
        "When gathering requirements, design decisions, or clarifying choices from the user, "
        "use the available inquiry tools (`make_questionnaire`"
        + (" or `make_form`, or freestyle conversation" if "make_form" in available else "")
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
                "When calling `make_questionnaire`, output at most a single concise introductory "
                "sentence (e.g. 'Please select your preferred options below.') or emit no text at "
                "all, then immediately call `wait_for_click` or halt to await user submission."
            ),
            (
                "When `write_in=True` is enabled on questions, do NOT include explicit 'Other' or "
                "'Custom' choice options; the UI automatically provides an unselected freeform "
                "write-in text field."
            ),
            (
                "When defining custom artifacts or buttons, dynamic context pointers "
                "(`{'path': ...}`) are disallowed and dropped; the harness automatically "
                "captures a complete snapshot of all interactive input widgets across the "
                "surface in `event.data`. Buttons may define static context values "
                "(e.g. `{'approved': true}`) in `action.event.context`."
            ),
            (
                "Button interactions are recorded chronologically into append-only JSONL "
                "event logs at `/artifacts/<family>/<uuid>/interactions/<button_id>.jsonl` "
                "and the latest snapshot is saved in `state.json` under `last_event`."
            ),
            (
                "For questionnaires and forms, user answers are automatically compiled into "
                "`/artifacts/<family>/<uuid>/answers.md` in clean, human-readable Markdown. "
                "Inspect `answers.md` to review the user's responses."
            ),
            (
                "Consult the 'artifacts' skill at `/skills/bundled/artifacts/SKILL.md` and "
                "'a2ui_components' skill at `/skills/bundled/a2ui_components/SKILL.md` for "
                "guidance on A2UI basic catalog components, manifest schemas, and button "
                "interactions."
            ),
            (
                "When an interaction event unblocks the conversation or notifies an idle agent "
                "after a turn completes, Seamus injects a synthetic user turn beginning with "
                "`<SYNTHETIC MESSAGE INDICATOR>`. Treat the content as an event notification."
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
    artifacts_implementation: ArtifactsImplementation = ArtifactsImplementation.SEAMUS,
) -> str:
    """Construct the base XML prompt scaffold without dynamic context or custom additions."""
    doc = SystemPromptDocument(
        identity=build_default_identity(),
        operating_environment=build_operating_environment(
            workdir,
            mode=mode,
            phase=phase,
            artifacts_implementation=artifacts_implementation,
        ),
        operational_mode=build_operational_mode_section(
            mode=mode,
            phase=phase,
            active_plan_id=active_plan_id,
            active_plan_title=active_plan_title,
            artifacts_implementation=artifacts_implementation,
        ),
        engineering_discipline=build_engineering_discipline(),
        tool_usage=build_tool_usage(),
        user_inquiry=build_user_inquiry(
            mode=mode,
            phase=phase,
            artifacts_implementation=artifacts_implementation,
        ),
        communication_style=build_communication_style(),
    )
    dumped = doc.model_dump(mode="json", exclude_none=True)
    return lmxml.dumps(dumped)


def _match_pattern_files(base_dir: Path, pattern: str) -> list[Path]:
    """Find all regular files matching pattern under base_dir, sorted alphabetically.

    Supports recursive wildcards (e.g. .seamus/rules/**), exact relative paths,
    and excludes .git directories.
    """
    norm = pattern.strip().lstrip("/")
    if not norm:
        return []

    # Map trailing /** to /**/* to match all files recursively
    if norm.endswith("/**"):
        glob_pat = norm[:-3] + "/**/*"
    elif norm == "**":
        glob_pat = "**/*"
    else:
        glob_pat = norm

    results: list[Path] = []
    # Fast path for non-wildcard patterns
    if not any(char in glob_pat for char in "*?[]"):
        target = base_dir / norm
        if target.is_file():
            rel = target.relative_to(base_dir).as_posix()
            if not (rel == ".git" or rel.startswith(".git/")):
                results.append(target)
        return results

    try:
        for p in base_dir.glob(glob_pat):
            if p.is_file():
                rel = p.relative_to(base_dir).as_posix()
                if not (rel == ".git" or rel.startswith(".git/")):
                    results.append(p)
    except Exception as exc:
        logger.debug("Error evaluating glob pattern %r against %s: %s", pattern, base_dir, exc)

    return sorted(results, key=lambda p: p.relative_to(base_dir).as_posix())


def discover_context_files(
    workspace_data_dir: Path,
    repositories: Sequence[ExternalRepositoryConfig] | None = None,
    projects_dir: Path | None = None,
    rules_patterns: Sequence[str] | None = None,
    max_file_size_bytes: int = 1_000_000,
) -> list[DiscoveredContextItem]:
    """Discover and read context/rule files from workspace and mounted external repositories.

    Search order:
    1. /workspace (workspace_data_dir)
    2. /projects/{mount_name} for each repository in repositories in order

    Within each root:
    - Evaluated in the order of rules_patterns.
    - Matches for wildcards (e.g. rules/**) are sorted alphabetically.
    - Files are deduplicated preserving the earliest match.
    - Files exceeding max_file_size_bytes or unparseable binary files are skipped.
    """
    patterns = list(rules_patterns) if rules_patterns is not None else DEFAULT_RULES_PATTERNS
    if not patterns:
        return []

    roots: list[tuple[Path, str]] = []
    if workspace_data_dir.is_dir():
        roots.append((workspace_data_dir, "/workspace"))

    if repositories and projects_dir:
        mount_paths = calculate_mount_paths(list(repositories))
        for repo in repositories:
            mount_name = mount_paths.get(repo.id, "repo")
            host_repo_dir = projects_dir / mount_name
            if host_repo_dir.is_dir():
                roots.append((host_repo_dir, f"/projects/{mount_name}"))

    seen_sandbox_paths: set[str] = set()
    discovered: list[DiscoveredContextItem] = []

    for host_root, sandbox_root in roots:
        for pattern in patterns:
            matched_files = _match_pattern_files(host_root, pattern)
            for file_path in matched_files:
                rel = file_path.relative_to(host_root).as_posix()
                sandbox_path = f"{sandbox_root}/{rel}"
                if sandbox_path in seen_sandbox_paths:
                    continue
                seen_sandbox_paths.add(sandbox_path)

                try:
                    stat = file_path.stat()
                    if stat.st_size > max_file_size_bytes:
                        logger.warning(
                            "Skipping context file %s (%d bytes exceeds limit %d)",
                            sandbox_path,
                            stat.st_size,
                            max_file_size_bytes,
                        )
                        continue
                except OSError:
                    continue

                try:
                    content = file_path.read_text(encoding="utf-8").strip()
                except (UnicodeDecodeError, OSError) as exc:
                    logger.warning(
                        "Skipping unreadable or binary context file %s: %s",
                        sandbox_path,
                        exc,
                    )
                    continue

                discovered.append(
                    DiscoveredContextItem(
                        path=sandbox_path,
                        content=content,
                    )
                )

    return discovered


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
    discovered_context: Sequence[DiscoveredContextItem] | None = None,
    skills: SkillsPromptDocument | None = None,
    plan: str | None = None,
    artifacts_implementation: ArtifactsImplementation = ArtifactsImplementation.SEAMUS,
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
    plan_text = plan.strip() if plan and plan.strip() else None

    doc = SystemPromptDocument(
        identity=build_default_identity(),
        operating_environment=build_operating_environment(
            workdir,
            mode=mode,
            phase=phase,
            artifacts_implementation=artifacts_implementation,
        ),
        operational_mode=build_operational_mode_section(
            mode=mode,
            phase=phase,
            active_plan_id=active_plan_id,
            active_plan_title=active_plan_title,
            artifacts_implementation=artifacts_implementation,
        ),
        engineering_discipline=build_engineering_discipline(),
        tool_usage=build_tool_usage(),
        user_inquiry=build_user_inquiry(
            mode=mode,
            phase=phase,
            artifacts_implementation=artifacts_implementation,
        ),
        communication_style=build_communication_style(),
        dynamic_context=dynamic_ctx,
        discovered_context=list(discovered_context) if discovered_context else None,
        skills=skills,
        plan=plan_text,
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
