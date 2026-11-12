"""Domain definitions for operational modes, execution phases, and tool/mount policies."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from seamus.config.models import ArtifactsImplementation


class ModeName(StrEnum):
    """Canonical operational mode identifiers."""

    CHAT = "chat"
    PLAN = "plan"


class PlanPhase(StrEnum):
    """Canonical phases within Plan mode."""

    DISCUSS = "discuss"
    MAKE = "make"
    EXECUTE = "execute"


ARTIFACT_RELATED_TOOLS: frozenset[str] = frozenset(
    {"make_artifact", "make_questionnaire", "make_form", "make_plan", "update_plan", "edit_plan"}
)

ALL_HARNESS_TOOLS: frozenset[str] = frozenset(
    {
        "make_artifact",
        "make_questionnaire",
        "make_form",
        "make_plan",
        "update_plan",
        "edit_plan",
        "wait_for_click",
        "plan",
        "discard",
    }
)


class MountPolicy(BaseModel):
    """Filesystem volume mount permissions for a mode or phase."""

    model_config = ConfigDict(frozen=True)

    workspace_readonly: bool = False
    notes_mounted: bool = False
    notes_readonly: bool = True


class PhaseDescriptor(BaseModel):
    """Descriptor for an execution phase within a phased operational mode."""

    model_config = ConfigDict(frozen=True)

    name: str
    title: str
    description: str
    mount_policy: MountPolicy
    tools: tuple[str, ...] = ()


class ModeDescriptor(BaseModel):
    """Descriptor for a top-level operational mode."""

    model_config = ConfigDict(frozen=True)

    name: str
    title: str
    description: str
    mount_policy: MountPolicy
    tools: tuple[str, ...] = ()
    phases: tuple[PhaseDescriptor, ...] = ()
    default_phase: str | None = None

    def get_phase(self, phase_name: str | None) -> PhaseDescriptor | None:
        """Look up a phase descriptor by name."""
        if not self.phases:
            return None
        target = phase_name or self.default_phase
        for phase in self.phases:
            if phase.name == target:
                return phase
        return None


CHAT_MODE = ModeDescriptor(
    name=ModeName.CHAT.value,
    title="Chat",
    description=(
        "Direct conversational and coding mode with full read-write access to the workspace "
        "for answering questions, exploring code, and making immediate changes."
    ),
    mount_policy=MountPolicy(
        workspace_readonly=False,
        notes_mounted=False,
        notes_readonly=True,
    ),
    tools=("make_artifact", "make_questionnaire", "wait_for_click"),
    phases=(),
    default_phase=None,
)

PLAN_DISCUSS_PHASE = PhaseDescriptor(
    name=PlanPhase.DISCUSS.value,
    title="Discuss",
    description=(
        "Explore the workspace with read-write access, clarify requirements and trade-offs "
        "with the user via conversation, blocking questionnaires (`make_questionnaire`), or "
        "non-blocking forms (`make_form`), and record findings and notes across the workspace "
        "before calling `plan()`."
    ),
    mount_policy=MountPolicy(
        workspace_readonly=False,
        notes_mounted=False,
        notes_readonly=True,
    ),
    tools=("make_artifact", "make_questionnaire", "make_form", "plan", "discard", "wait_for_click"),
)

PLAN_MAKE_PHASE = PhaseDescriptor(
    name=PlanPhase.MAKE.value,
    title="Make",
    description=(
        "Synthesize the organized notes in `/workspace/notes` and inspect the read-only "
        "`/workspace` to author and refine the session's Markdown implementation plan artifact via "
        "`make_plan`, `update_plan`, and `edit_plan`, then await user approval via the "
        "plan's Proceed action."
    ),
    mount_policy=MountPolicy(
        workspace_readonly=True,
        notes_mounted=True,
        notes_readonly=True,
    ),
    tools=("make_plan", "update_plan", "edit_plan", "discard"),
)

PLAN_EXECUTE_PHASE = PhaseDescriptor(
    name=PlanPhase.EXECUTE.value,
    title="Execute",
    description=(
        "Implement and verify the approved plan from `/artifacts/plans/` and `/workspace/notes` "
        "with full read-write access to `/workspace`."
    ),
    mount_policy=MountPolicy(
        workspace_readonly=False,
        notes_mounted=True,
        notes_readonly=True,
    ),
    tools=("discard",),
)

PLAN_MODE = ModeDescriptor(
    name=ModeName.PLAN.value,
    title="Plan",
    description=(
        "Structured three-phase planning and execution workflow (Discuss -> Make -> Execute) "
        "with phase-isolated threads, flexible workspace exploration, read-only plan authoring, "
        "and dedicated Plan artifact handoffs."
    ),
    mount_policy=PLAN_DISCUSS_PHASE.mount_policy,
    tools=(),
    phases=(PLAN_DISCUSS_PHASE, PLAN_MAKE_PHASE, PLAN_EXECUTE_PHASE),
    default_phase=PlanPhase.DISCUSS.value,
)

MODES_REGISTRY: dict[str, ModeDescriptor] = {
    CHAT_MODE.name: CHAT_MODE,
    PLAN_MODE.name: PLAN_MODE,
}


def get_mode_descriptor(mode: str) -> ModeDescriptor:
    """Resolve a ModeDescriptor by name, defaulting to Plan mode if unknown."""
    return MODES_REGISTRY.get(mode, PLAN_MODE)


def normalize_mode_and_phase(mode: str | None, phase: str | None = None) -> tuple[str, str | None]:
    """Normalize a mode and optional phase into a valid canonical (mode, phase) pair."""
    resolved_mode_name = mode if mode in MODES_REGISTRY else ModeName.PLAN.value
    descriptor = MODES_REGISTRY[resolved_mode_name]
    if not descriptor.phases:
        return descriptor.name, None
    phase_desc = descriptor.get_phase(phase)
    resolved_phase = phase_desc.name if phase_desc is not None else descriptor.default_phase
    return descriptor.name, resolved_phase


def resolve_mount_policy(mode: str, phase: str | None = None) -> MountPolicy:
    """Return the effective MountPolicy for the given mode and phase."""
    descriptor = get_mode_descriptor(mode)
    phase_desc = descriptor.get_phase(phase)
    if phase_desc is not None:
        return phase_desc.mount_policy
    return descriptor.mount_policy


def resolve_available_harness_tools(
    mode: str,
    phase: str | None = None,
    *,
    has_active_plan: bool = False,
    artifacts_implementation: str | ArtifactsImplementation = ArtifactsImplementation.SEAMUS,
) -> set[str]:
    """Determine which harness/artifact tools are exposed for a given mode and phase."""
    descriptor = get_mode_descriptor(mode)
    phase_desc = descriptor.get_phase(phase)
    raw_tools = set(phase_desc.tools if phase_desc is not None else descriptor.tools)

    if artifacts_implementation in (ArtifactsImplementation.NONE, "none"):
        raw_tools.difference_update(ARTIFACT_RELATED_TOOLS)
        raw_tools.discard("wait_for_click")
        return raw_tools

    if descriptor.name == ModeName.PLAN.value and phase_desc is not None:
        if phase_desc.name == PlanPhase.MAKE.value:
            if has_active_plan:
                raw_tools.discard("make_plan")
            else:
                raw_tools.discard("update_plan")
                raw_tools.discard("edit_plan")

    if raw_tools & ARTIFACT_RELATED_TOOLS:
        raw_tools.add("wait_for_click")
    else:
        raw_tools.discard("wait_for_click")

    return raw_tools
