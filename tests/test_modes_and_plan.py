"""Comprehensive tests for operational modes, plan mode phases, and artifacts tools."""

from pathlib import Path

import pytest

from seamus.config.models import AgentConfig, InferenceConfig, InferenceFormat
from seamus.domain.modes import (
    ModeName,
    get_mode_descriptor,
    normalize_mode_and_phase,
    resolve_available_harness_tools,
    resolve_mount_policy,
)
from seamus.harness.artifacts import PlanBuilder
from seamus.harness.prompt import (
    build_scaffold_prompt,
)
from seamus.harness.runner import SessionAgentRunner
from seamus.harness.store import HarnessStore


def make_config() -> AgentConfig:
    return AgentConfig(
        inference=InferenceConfig(
            format=InferenceFormat.OPENAI,
            base_url="https://api.openai.com/v1",
            api_key="test-key",
        ),
        model_name="gpt-4o",
    )


def test_modes_domain_registration_and_normalization() -> None:
    chat_desc = get_mode_descriptor("chat")
    assert chat_desc.name == "chat"
    assert "ask" in chat_desc.tools

    plan_desc = get_mode_descriptor("plan")
    assert plan_desc.name == "plan"
    assert len(plan_desc.phases) == 3

    # Normalization defaults
    m, p = normalize_mode_and_phase("chat", None)
    assert m == "chat" and p is None

    m, p = normalize_mode_and_phase("plan", None)
    assert m == "plan" and p == "discuss"

    m, p = normalize_mode_and_phase("plan", "make")
    assert m == "plan" and p == "make"

    m, p = normalize_mode_and_phase("plan", "execute")
    assert m == "plan" and p == "execute"

    # Unknown mode safely falls back to Chat
    unknown_m, unknown_p = normalize_mode_and_phase("unknown_mode")
    assert unknown_m == "chat" and unknown_p is None


def test_mount_policy_resolution() -> None:
    # Chat: RW workspace, no notes
    chat_mp = resolve_mount_policy("chat", None)
    assert chat_mp.workspace_readonly is False
    assert chat_mp.notes_mounted is False

    # Plan/Discuss: RO workspace, RW notes
    disc_mp = resolve_mount_policy("plan", "discuss")
    assert disc_mp.workspace_readonly is True
    assert disc_mp.notes_mounted is True
    assert disc_mp.notes_readonly is False

    # Plan/Make: RO workspace, RO notes
    make_mp = resolve_mount_policy("plan", "make")
    assert make_mp.workspace_readonly is True
    assert make_mp.notes_mounted is True
    assert make_mp.notes_readonly is True

    # Plan/Execute: RW workspace, RO notes
    exec_mp = resolve_mount_policy("plan", "execute")
    assert exec_mp.workspace_readonly is False
    assert exec_mp.notes_mounted is True
    assert exec_mp.notes_readonly is True


def test_available_harness_tools_resolution() -> None:
    # Chat
    chat_tools = resolve_available_harness_tools("chat")
    assert "ask" in chat_tools
    assert "read_artifact_submission" in chat_tools
    assert "plan" not in chat_tools
    assert "make_plan" not in chat_tools
    assert "discard" not in chat_tools

    # Plan/Discuss
    disc_tools = resolve_available_harness_tools("plan", "discuss")
    assert "ask" in disc_tools
    assert "form" in disc_tools
    assert "plan" in disc_tools
    assert "discard" in disc_tools
    assert "read_artifact_submission" in disc_tools
    assert "make_plan" not in disc_tools

    # Plan/Make without active plan: make_plan is exposed, update/edit are not
    make_no_plan = resolve_available_harness_tools("plan", "make", has_active_plan=False)
    assert "make_plan" in make_no_plan
    assert "update_plan" not in make_no_plan
    assert "edit_plan" not in make_no_plan
    assert "discard" in make_no_plan
    assert "read_artifact_submission" in make_no_plan

    # Plan/Make with active plan: make_plan disappears, update/edit appear
    make_with_plan = resolve_available_harness_tools("plan", "make", has_active_plan=True)
    assert "make_plan" not in make_with_plan
    assert "update_plan" in make_with_plan
    assert "edit_plan" in make_with_plan
    assert "discard" in make_with_plan

    # Plan/Execute: no special inquiry or plan authoring tools, only discard
    exec_tools = resolve_available_harness_tools("plan", "execute")
    assert "discard" in exec_tools
    assert "ask" not in exec_tools
    assert "form" not in exec_tools
    assert "plan" not in exec_tools
    assert "make_plan" not in exec_tools
    assert "read_artifact_submission" not in exec_tools


def test_plan_builder_lifecycle(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir()

    # Create plan
    plan_path = PlanBuilder.create_plan(
        artifacts_dir,
        "test-plan",
        content="# Initial Plan\n\n- Step 1",
        title="Custom Architecture Plan",
    )
    assert plan_path.exists()
    assert (plan_path / "manifest.json").exists()
    assert (plan_path / "updateDataModel.json").exists()

    # Read plan
    read_content, title = PlanBuilder.read_plan(artifacts_dir, "test-plan")
    assert read_content == "# Initial Plan\n\n- Step 1"
    assert title == "Custom Architecture Plan"

    # Update plan
    PlanBuilder.update_plan(artifacts_dir, "test-plan", "# Updated Plan\n\n- Step 1\n- Step 2")
    updated_content, _ = PlanBuilder.read_plan(artifacts_dir, "test-plan")
    assert updated_content == "# Updated Plan\n\n- Step 1\n- Step 2"

    # Edit plan
    PlanBuilder.edit_plan(artifacts_dir, "test-plan", "- Step 2", "- Step 2 (verified)")
    edited_content, _ = PlanBuilder.read_plan(artifacts_dir, "test-plan")
    assert "- Step 2 (verified)" in edited_content

    # Approve plan (strips proceed button)
    PlanBuilder.approve_plan(artifacts_dir, "test-plan")
    data_content = (plan_path / "updateDataModel.json").read_text(encoding="utf-8")
    assert '"approved": true' in data_content

    # Close plan (writes deleteSurface.json)
    assert PlanBuilder.close_plan(artifacts_dir, "test-plan") is True
    assert (plan_path / "deleteSurface.json").exists()


def test_system_prompt_lmxml_composition() -> None:
    # Verify scaffold prompt includes mode section
    scaffold_chat = build_scaffold_prompt("/workspace", mode="chat")
    assert "<operational_mode>" in scaffold_chat
    assert "<mode_slug>chat</mode_slug>" in scaffold_chat

    scaffold_disc = build_scaffold_prompt("/workspace", mode="plan", phase="discuss")
    assert "<operational_mode>" in scaffold_disc
    assert "<mode_slug>plan</mode_slug>" in scaffold_disc
    assert "<phase_slug>discuss</phase_slug>" in scaffold_disc

    scaffold_make = build_scaffold_prompt("/workspace", mode="plan", phase="make")
    assert "<operational_mode>" in scaffold_make
    assert "<phase_slug>make</phase_slug>" in scaffold_make
    assert "<plan_document_specification>" in scaffold_make

    scaffold_exec = build_scaffold_prompt(
        "/workspace",
        mode="plan",
        phase="execute",
        active_plan_id="my-plan-id",
        active_plan_title="Engine Overhaul",
    )
    assert "<operational_mode>" in scaffold_exec
    assert "<phase_slug>execute</phase_slug>" in scaffold_exec
    assert "<active_plan_context>" in scaffold_exec
    assert "my-plan-id" in scaffold_exec
    assert "Engine Overhaul" in scaffold_exec


@pytest.mark.asyncio
async def test_session_mode_switch_and_phase_transitions() -> None:
    store = HarnessStore()
    config = make_config()
    agent = store.create_agent(config=config, name="agent-modes")
    session = store.create_session(agent_identifier=str(agent.id), name="session-modes")

    runner = SessionAgentRunner(session=session)

    # Initial state is chat
    open_thread = session.get_open_thread()
    assert open_thread.mode == "chat"
    assert open_thread.phase is None
    assert open_thread.mode_label == "chat"

    # Switch session mode to plan via store with empty initial thread (reuses empty thread)
    updated_session = store.switch_session_mode(
        str(agent.id),
        str(session.id),
        mode=ModeName.PLAN.value,
    )
    new_thread = updated_session.get_open_thread()
    assert new_thread.mode == "plan"
    assert new_thread.phase == "discuss"
    assert new_thread.mode_label == "plan/discuss"
    assert new_thread.id == open_thread.id
    assert open_thread.is_open

    # Simulate messages in thread so it becomes non-empty
    new_thread.append_event({"type": "TEXT_MESSAGE_CHUNK", "delta": "Discussing..."})
    assert not new_thread.is_empty

    # Calling plan tool in runner queues discuss -> make
    res = runner.handle_plan()
    assert "Transitioning session to Plan/Make phase" in res
    assert runner._pending_phase_transition == ("plan", "make", True)

    # Execute transition to make
    mode, phase, auto_wake = runner._pending_phase_transition
    runner._pending_phase_transition = None
    make_thread = await runner.transition_to_phase(mode, phase, auto_wake=auto_wake)
    assert make_thread.phase == "make"

    # Calling make_plan sets active_plan_id and tab title
    plan_res = runner.handle_make_plan(
        content="# Plan\n\nRefactor",
        name="Backend Refactor",
    )
    assert "Created plan" in plan_res
    assert session.active_plan_id is not None

    # Discarding resets to discuss and clears active plan
    discard_res = runner.handle_discard()
    assert "Discarded active plan" in discard_res
    assert session.active_plan_id is None
    assert runner._pending_phase_transition == ("plan", "discuss", False)

    # Execute transition to discuss
    mode, phase, auto_wake = runner._pending_phase_transition
    runner._pending_phase_transition = None
    disc_thread = await runner.transition_to_phase(mode, phase, auto_wake=auto_wake)
    assert disc_thread.phase == "discuss"
