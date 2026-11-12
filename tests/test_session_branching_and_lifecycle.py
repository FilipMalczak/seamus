"""Tests for session branching, provenance tracking, and lifecycle states."""

from uuid import uuid4

import pytest
from ag_ui.core.events import (
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
)
from fastapi.testclient import TestClient

from seamus.config.models import AgentConfig, InferenceConfig
from seamus.domain.artifacts import SYNTHETIC_MESSAGE_INDICATOR
from seamus.domain.entities import AgentStatus, Session, SessionStatus
from seamus.harness.runner import (
    RunnerRegistry,
    SessionAgentRunner,
    SessionBusyError,
    reset_runner_registry,
)
from seamus.harness.store import HarnessStore, reset_harness_store
from seamus.server.app import create_app


def make_complete_config() -> AgentConfig:
    return AgentConfig(
        inference=InferenceConfig(api_key="valid-key"),
        model_name="test-model",
    )


def test_session_lifecycle_entity_transitions() -> None:
    config = make_complete_config()
    session = Session(
        agent_id=uuid4(),
        config=config,
    )
    assert session.status == SessionStatus.ACTIVE
    assert session.is_active is True

    # Initial open thread
    thread = session.create_thread()
    assert thread.is_open is True
    assert thread.status == AgentStatus.AWAITING_USER

    # Fail session
    session.fail()
    assert session.status.value == SessionStatus.FAILED.value
    assert session.is_active is False
    assert thread.is_open is False
    assert thread.status == AgentStatus.ERROR

    # Cannot create new thread in non-active session
    with pytest.raises(ValueError, match="Cannot create thread"):
        session.create_thread()

    # get_open_thread returns latest thread if terminal
    assert session.get_open_thread().id == thread.id

    # Test kill transition
    session2 = Session(agent_id=uuid4(), config=config)
    t2 = session2.create_thread()
    session2.kill()
    assert session2.status == SessionStatus.KILLED
    assert session2.is_active is False
    assert t2.is_open is False


def test_harness_store_kill_session() -> None:
    store = HarnessStore()
    config = make_complete_config()
    store.create_agent(config=config, name="agent-kill-test")
    session = store.create_session(agent_identifier="agent-kill-test", name="session-to-kill")

    assert session.status == SessionStatus.ACTIVE
    killed_session = store.kill_session("agent-kill-test", "session-to-kill")
    assert killed_session.status == SessionStatus.KILLED
    assert killed_session.is_active is False


def test_harness_store_branch_session_and_provenance() -> None:
    store = HarnessStore()
    config = make_complete_config()
    store.create_agent(config=config, name="branch-agent")
    s1 = store.create_session(agent_identifier="branch-agent", name="parent-session")

    # Add 2 turns to open thread:
    # Turn 1: user msg 1 -> assistant msg 1
    # Turn 2: user msg 2 -> assistant msg 2
    t1 = s1.get_open_thread()
    u1_id = "user-msg-1"
    a1_id = "asst-msg-1"
    u2_id = "user-msg-2"
    a2_id = "asst-msg-2"

    t1.append_event(TextMessageStartEvent(message_id=u1_id, role="user"))
    t1.append_event(TextMessageContentEvent(message_id=u1_id, delta="Hello"))
    t1.append_event(TextMessageEndEvent(message_id=u1_id))
    t1.append_event({"type": "RUN_STARTED"})
    t1.append_event(TextMessageStartEvent(message_id=a1_id, role="assistant"))
    t1.append_event(TextMessageContentEvent(message_id=a1_id, delta="Hi there!"))
    t1.append_event(TextMessageEndEvent(message_id=a1_id))
    t1.append_event({"type": "RUN_FINISHED"})

    t1.append_event(TextMessageStartEvent(message_id=u2_id, role="user"))
    t1.append_event(TextMessageContentEvent(message_id=u2_id, delta="How are you?"))
    t1.append_event(TextMessageEndEvent(message_id=u2_id))
    t1.append_event({"type": "RUN_STARTED"})
    t1.append_event(TextMessageStartEvent(message_id=a2_id, role="assistant"))
    t1.append_event(TextMessageContentEvent(message_id=a2_id, delta="Doing great!"))
    t1.append_event(TextMessageEndEvent(message_id=a2_id))
    t1.append_event({"type": "RUN_FINISHED"})

    assert len(t1.events) == 16

    # Branch off turn 1 (asst-msg-1)
    s2 = store.branch_session(
        agent_identifier="branch-agent",
        session_identifier="parent-session",
        message_id=a1_id,
        name="branched-s2",
    )

    assert s2.name == "branched-s2"
    assert s2.status == SessionStatus.ACTIVE
    assert s2.provenance is not None
    assert s2.provenance.parent_session_id == s1.id
    assert s2.provenance.parent_message_id == a1_id
    assert s2.provenance.parent_session_name == "parent-session"

    # S1 remains ACTIVE and unchanged
    assert s1.status == SessionStatus.ACTIVE
    assert len(s1.get_open_thread().events) == 16

    # S2 has only events from Turn 1 (8 events)
    t2 = s2.get_open_thread()
    assert t2.is_open is True
    assert t2.status == AgentStatus.AWAITING_USER
    assert len(t2.events) == 8
    event_message_ids = [
        getattr(ev, "message_id", None) or (ev.get("message_id") if isinstance(ev, dict) else None)
        for ev in t2.events
    ]
    assert u1_id in event_message_ids
    assert a1_id in event_message_ids
    assert u2_id not in event_message_ids
    assert a2_id not in event_message_ids

    # S1 can now be KILLED or FAILED, and we can still branch off it!
    s1.kill()
    assert s1.status.value == SessionStatus.KILLED.value

    s3 = store.branch_session(
        agent_identifier="branch-agent",
        session_identifier="parent-session",
        message_id=a1_id,
        name="branched-from-killed",
    )
    assert s3.status == SessionStatus.ACTIVE
    assert s3.provenance is not None
    assert s3.provenance.parent_session_id == s1.id

    # Reject branching from user message
    with pytest.raises(ValueError, match="Assistant message 'user-msg-1' not found"):
        store.branch_session(
            agent_identifier="branch-agent",
            session_identifier="parent-session",
            message_id=u1_id,
        )

    # Reject branching from non-existent message
    with pytest.raises(ValueError, match="not found"):
        store.branch_session(
            agent_identifier="branch-agent",
            session_identifier="parent-session",
            message_id="non-existent-msg",
        )


@pytest.mark.asyncio
async def test_runner_blocks_input_to_terminal_session() -> None:
    config = make_complete_config()
    session = Session(agent_id=uuid4(), config=config)
    session.kill()

    runner = SessionAgentRunner(session=session)
    assert runner.is_awaiting_user() is False

    with pytest.raises(SessionBusyError, match="not active"):
        await runner.dispatch_user_input("test input")


def test_api_kill_and_branch_endpoints() -> None:
    store = HarnessStore()
    reset_harness_store(store)
    reset_runner_registry(RunnerRegistry())

    config = make_complete_config()
    store.create_agent(config=config, name="api-agent")
    session = store.create_session(agent_identifier="api-agent", name="api-session")

    # Add assistant message to open thread
    t = session.get_open_thread()
    asst_id = "api-asst-msg"
    t.append_event(TextMessageStartEvent(message_id=asst_id, role="assistant"))
    t.append_event(TextMessageContentEvent(message_id=asst_id, delta="Answer"))
    t.append_event(TextMessageEndEvent(message_id=asst_id))
    t.append_event({"type": "RUN_FINISHED"})

    app = create_app()
    client = TestClient(app)

    # Branch session via API
    branch_res = client.post(
        "/api/v-alpha/agent/api-agent/session/api-session/branch",
        json={"message_id": asst_id, "name": "api-branched"},
    )
    assert branch_res.status_code == 201
    branch_data = branch_res.json()
    assert branch_data["name"] == "api-branched"
    assert branch_data["status"] == "ACTIVE"
    assert branch_data["provenance"]["parent_message_id"] == asst_id
    assert branch_data["provenance"]["parent_session_name"] == "api-session"

    # Kill session via API
    kill_res = client.post("/api/v-alpha/agent/api-agent/session/api-session/kill")
    assert kill_res.status_code == 200
    kill_data = kill_res.json()
    assert kill_data["status"] == "KILLED"

    # Attempting to post user input to killed session returns 409 Conflict
    input_res = client.post(
        "/api/v-alpha/agent/api-agent/session/api-session/input",
        json={"text": "Hello"},
    )
    assert input_res.status_code == 409
    assert "not active" in input_res.json()["detail"]


def test_branch_with_synthetic_and_tool_call_ids() -> None:
    store = HarnessStore()
    config = make_complete_config()
    store.create_agent(config=config, name="robust-branch-agent")
    s = store.create_session(agent_identifier="robust-branch-agent", name="parent-session")
    t = s.get_open_thread()

    # User message
    t.append_event(TextMessageStartEvent(message_id="user-1", role="user"))
    t.append_event(TextMessageContentEvent(message_id="user-1", delta="Please run tool"))
    t.append_event(TextMessageEndEvent(message_id="user-1"))
    t.append_event({"type": "RUN_STARTED", "timestamp": "2026-11-01T20:00:00Z"})
    # Assistant turn with tool call and text response
    t.append_event(
        {
            "type": "TOOL_CALL_START",
            "tool_call_id": "call-abc-123",
            "tool_call_name": "execute",
            "parent_message_id": "parent-turn-msg",
            "timestamp": "2026-11-01T20:00:01Z",
        }
    )
    t.append_event(
        {
            "type": "TOOL_CALL_RESULT",
            "tool_call_id": "call-abc-123",
            "content": "output",
            "timestamp": 1793565450000,
        }
    )
    t.append_event(
        TextMessageStartEvent(
            message_id="asst-text-1",
            role="assistant",
            timestamp=1793565451000,
        )
    )
    t.append_event(TextMessageContentEvent(message_id="asst-text-1", delta="Done!"))
    t.append_event(TextMessageEndEvent(message_id="asst-text-1"))
    t.append_event({"type": "RUN_FINISHED", "timestamp": "2026-11-01T20:00:04Z"})

    # 1. Branch by tool call id
    s_by_tool = store.branch_session(
        agent_identifier="robust-branch-agent",
        session_identifier="parent-session",
        message_id="call-abc-123",
        name="branch-by-tool",
    )
    assert s_by_tool.provenance is not None
    assert s_by_tool.provenance.parent_message_id == "call-abc-123"
    assert len(s_by_tool.get_open_thread().events) == 10

    # 2. Branch by turn index "asst-0"
    s_by_index = store.branch_session(
        agent_identifier="robust-branch-agent",
        session_identifier="parent-session",
        message_id="asst-0",
        name="branch-by-index",
    )
    assert s_by_index.provenance is not None
    assert len(s_by_index.get_open_thread().events) == 10

    # 3. Branch by synthetic client timestamp ID e.g. "asst-1793565453328"
    s_by_synthetic = store.branch_session(
        agent_identifier="robust-branch-agent",
        session_identifier="parent-session",
        message_id="asst-1793565453328",
        name="branch-by-synthetic",
    )
    assert s_by_synthetic.provenance is not None
    assert s_by_synthetic.provenance.parent_message_id in ("call-abc-123", "asst-text-1")
    assert len(s_by_synthetic.get_open_thread().events) == 10


def test_multi_level_branching_lineage_s1_s2_s3() -> None:
    store = HarnessStore()
    config = make_complete_config()
    store.create_agent(config=config, name="chain-agent")

    # 1. S1 with Turn 1
    s1 = store.create_session(agent_identifier="chain-agent", name="session-s1")
    t1 = s1.get_open_thread()
    t1.append_event(TextMessageStartEvent(message_id="user-1", role="user"))
    t1.append_event(TextMessageContentEvent(message_id="user-1", delta="Msg 1"))
    t1.append_event(TextMessageEndEvent(message_id="user-1"))
    t1.append_event({"type": "RUN_STARTED"})
    t1.append_event(TextMessageStartEvent(message_id="asst-1", role="assistant"))
    t1.append_event(TextMessageContentEvent(message_id="asst-1", delta="Reply 1"))
    t1.append_event(TextMessageEndEvent(message_id="asst-1"))
    t1.append_event({"type": "RUN_FINISHED"})

    # 2. S2 branched from S1 at asst-1
    s2 = store.branch_session(
        agent_identifier="chain-agent",
        session_identifier="session-s1",
        message_id="asst-1",
        name="session-s2",
    )
    assert s2.provenance is not None
    assert s2.provenance.parent_session_id == s1.id
    assert s2.provenance.parent_message_id == "asst-1"
    assert len(s2.lineage) == 1
    assert s2.lineage[0].parent_session_id == s1.id
    assert s2.lineage[0].parent_message_id == "asst-1"

    # 3. In S2, user writes a message and assistant responds (Turn 2)
    t2 = s2.get_open_thread()
    t2.append_event(TextMessageStartEvent(message_id="user-2", role="user"))
    t2.append_event(TextMessageContentEvent(message_id="user-2", delta="Msg 2"))
    t2.append_event(TextMessageEndEvent(message_id="user-2"))
    t2.append_event({"type": "RUN_STARTED"})
    t2.append_event(TextMessageStartEvent(message_id="asst-2", role="assistant"))
    t2.append_event(TextMessageContentEvent(message_id="asst-2", delta="Reply 2"))
    t2.append_event(TextMessageEndEvent(message_id="asst-2"))
    t2.append_event({"type": "RUN_FINISHED"})

    # 4. S3 branched from S2 at asst-2
    s3 = store.branch_session(
        agent_identifier="chain-agent",
        session_identifier="session-s2",
        message_id="asst-2",
        name="session-s3",
    )
    assert s3.provenance is not None
    assert s3.provenance.parent_session_id == s2.id
    assert s3.provenance.parent_message_id == "asst-2"

    # Lineage on S3 must contain both S1 (before Turn 2) and S2 (after Turn 2)
    assert len(s3.lineage) == 2
    assert s3.lineage[0].parent_session_id == s1.id
    assert s3.lineage[0].parent_message_id == "asst-1"
    assert s3.lineage[0].parent_session_name == "session-s1"
    assert s3.lineage[1].parent_session_id == s2.id
    assert s3.lineage[1].parent_message_id == "asst-2"
    assert s3.lineage[1].parent_session_name == "session-s2"


def test_kill_session_mid_tool_cleans_up_and_errors() -> None:
    config = make_complete_config()
    session = Session(agent_id=uuid4(), config=config)
    thread = session.get_open_thread()
    thread.status = AgentStatus.EXECUTING_TOOL
    thread.append_event({"type": "RUN_STARTED"})
    thread.append_event(
        {
            "type": "TOOL_CALL_START",
            "tool_call_id": "call-mid-tool-1",
            "tool_call_name": "bash",
        }
    )
    thread.append_event(
        {
            "type": "TOOL_CALL_ARGS",
            "tool_call_id": "call-mid-tool-1",
            "args": '{"cmd":"sleep 10"}',
        }
    )
    thread.append_event({"type": "TOOL_CALL_END", "tool_call_id": "call-mid-tool-1"})

    runner = SessionAgentRunner(session=session, agent=object())
    runner.kill()

    assert session.status == SessionStatus.KILLED
    assert session.is_active is False
    assert thread.status == AgentStatus.ERROR

    # Check that tool call result was emitted with is_error=True
    tool_results = [
        ev
        for ev in thread.events
        if (getattr(ev, "type", None) or (ev.get("type") if isinstance(ev, dict) else None))
        == "TOOL_CALL_RESULT"
    ]
    assert len(tool_results) == 1
    assert tool_results[0]["tool_call_id"] == "call-mid-tool-1"
    assert tool_results[0]["is_error"] is True

    # Check that RUN_ERROR was emitted
    run_errors = [
        ev
        for ev in thread.events
        if (getattr(ev, "type", None) or (ev.get("type") if isinstance(ev, dict) else None))
        == "RUN_ERROR"
    ]
    assert len(run_errors) == 1


def test_kill_session_while_thinking_cleans_up_and_errors() -> None:
    config = make_complete_config()
    session = Session(agent_id=uuid4(), config=config)
    thread = session.get_open_thread()
    thread.status = AgentStatus.AWAITING_LLM
    thread.append_event({"type": "RUN_STARTED"})
    thread.append_event({"type": "REASONING_START", "message_id": "r-1"})

    runner = SessionAgentRunner(session=session, agent=object())
    runner.kill()

    assert session.status == SessionStatus.KILLED
    assert session.is_active is False
    assert thread.status == AgentStatus.ERROR

    # Check that RUN_ERROR was emitted
    run_errors = [
        ev
        for ev in thread.events
        if (getattr(ev, "type", None) or (ev.get("type") if isinstance(ev, dict) else None))
        == "RUN_ERROR"
    ]
    assert len(run_errors) == 1


def test_branch_after_tools_slices_at_tool_result() -> None:
    store = HarnessStore()
    config = make_complete_config()
    store.create_agent(config=config, name="tool-branch-agent")
    s1 = store.create_session(agent_identifier="tool-branch-agent", name="parent-session")
    t1 = s1.get_open_thread()

    # User message
    t1.append_event(TextMessageStartEvent(message_id="user-1", role="user"))
    t1.append_event(TextMessageContentEvent(message_id="user-1", delta="Run ls"))
    t1.append_event(TextMessageEndEvent(message_id="user-1"))

    # Assistant turn with tool execution
    t1.append_event({"type": "RUN_STARTED"})
    t1.append_event({"type": "TOOL_CALL_START", "tool_call_id": "tc-101", "tool_call_name": "bash"})
    t1.append_event({"type": "TOOL_CALL_ARGS", "tool_call_id": "tc-101", "args": '{"cmd":"ls"}'})
    t1.append_event({"type": "TOOL_CALL_END", "tool_call_id": "tc-101"})
    t1.append_event(
        {
            "type": "TOOL_CALL_RESULT",
            "tool_call_id": "tc-101",
            "content": "file1.txt\nfile2.txt",
        }
    )

    # Post-tool assistant text generation (which should be excluded when retrying inference)
    t1.append_event(TextMessageStartEvent(message_id="asst-text-1", role="assistant"))
    t1.append_event(
        TextMessageContentEvent(
            message_id="asst-text-1",
            delta="Here are the files: file1.txt, file2.txt",
        )
    )
    t1.append_event(TextMessageEndEvent(message_id="asst-text-1"))
    t1.append_event({"type": "RUN_FINISHED"})

    # 1. Normal branch off asst-text-1 preserves all 12 events
    s_normal = store.branch_session(
        agent_identifier="tool-branch-agent",
        session_identifier="parent-session",
        message_id="asst-text-1",
        retry_inference=False,
    )
    assert len(s_normal.get_open_thread().events) == 12
    assert s_normal.get_open_thread().status == AgentStatus.AWAITING_USER

    # 2. Branch after tool with retry_inference=True slices right after TOOL_CALL_RESULT (8 events)
    s_retry = store.branch_session(
        agent_identifier="tool-branch-agent",
        session_identifier="parent-session",
        message_id="asst-text-1",
        retry_inference=True,
    )
    retry_events = s_retry.get_open_thread().events
    assert len(retry_events) == 8
    # Last event in sliced history is the TOOL_CALL_RESULT
    last_ev = retry_events[-1]
    assert (getattr(last_ev, "type", None) or last_ev.get("type")) == "TOOL_CALL_RESULT"
    assert s_retry.get_open_thread().status == AgentStatus.AWAITING_LLM


def test_branch_after_tools_raises_when_no_tool_calls() -> None:
    store = HarnessStore()
    config = make_complete_config()
    store.create_agent(config=config, name="no-tool-agent")
    s1 = store.create_session(agent_identifier="no-tool-agent", name="parent-session")
    t1 = s1.get_open_thread()

    t1.append_event(TextMessageStartEvent(message_id="user-1", role="user"))
    t1.append_event(TextMessageContentEvent(message_id="user-1", delta="Hi"))
    t1.append_event(TextMessageEndEvent(message_id="user-1"))
    t1.append_event({"type": "RUN_STARTED"})
    t1.append_event(TextMessageStartEvent(message_id="asst-1", role="assistant"))
    t1.append_event(TextMessageContentEvent(message_id="asst-1", delta="Hello!"))
    t1.append_event(TextMessageEndEvent(message_id="asst-1"))
    t1.append_event({"type": "RUN_FINISHED"})

    with pytest.raises(ValueError, match="does not contain completed tool calls"):
        store.branch_session(
            agent_identifier="no-tool-agent",
            session_identifier="parent-session",
            message_id="asst-1",
            retry_inference=True,
        )


def test_api_branch_with_retry_inference(monkeypatch: pytest.MonkeyPatch) -> None:
    store = HarnessStore()
    reset_harness_store(store)
    reset_runner_registry()
    config = make_complete_config()
    store.create_agent(config=config, name="api-agent")
    s = store.create_session("api-agent", name="api-parent")
    t = s.get_open_thread()

    t.append_event(TextMessageStartEvent(message_id="u1", role="user"))
    t.append_event(TextMessageContentEvent(message_id="u1", delta="Test"))
    t.append_event(TextMessageEndEvent(message_id="u1"))
    t.append_event({"type": "RUN_STARTED"})
    t.append_event({"type": "TOOL_CALL_START", "tool_call_id": "tc-1", "tool_call_name": "tool"})
    t.append_event({"type": "TOOL_CALL_RESULT", "tool_call_id": "tc-1", "content": "output"})
    t.append_event(TextMessageStartEvent(message_id="a1", role="assistant"))
    t.append_event(TextMessageContentEvent(message_id="a1", delta="Done"))
    t.append_event(TextMessageEndEvent(message_id="a1"))
    t.append_event({"type": "RUN_FINISHED"})

    app = create_app()
    client = TestClient(app)

    res = client.post(
        f"/api/v-alpha/agent/api-agent/session/{s.id}/branch",
        json={"message_id": "a1", "retry_inference": True},
    )
    assert res.status_code == 201
    data = res.json()
    assert data["provenance"]["parent_message_id"] == "a1"
    from seamus.domain.resolution import resolve_session

    agent = store.resolve_agent("api-agent")
    branch_sess = resolve_session(agent, data["id"])
    # Sliced initial history had 6 events, and runner immediately resumed inference
    # adding retried response events
    events = branch_sess.get_open_thread().events
    assert len(events) >= 6
    assert (getattr(events[5], "type", None) or events[5].get("type")) == "TOOL_CALL_RESULT"


def test_granular_branch_before_and_after_user_and_system_events() -> None:
    store = HarnessStore()
    config = make_complete_config()
    store.create_agent(config=config, name="user-branch-agent")
    s = store.create_session("user-branch-agent", name="parent")
    t = s.get_open_thread()

    # User message 1
    t.append_event(TextMessageStartEvent(message_id="u1", role="user"))
    t.append_event(TextMessageContentEvent(message_id="u1", delta="First user message"))
    t.append_event(TextMessageEndEvent(message_id="u1"))
    t.append_event({"type": "RUN_STARTED"})
    t.append_event(TextMessageStartEvent(message_id="a1", role="assistant"))
    t.append_event(TextMessageContentEvent(message_id="a1", delta="First answer"))
    t.append_event(TextMessageEndEvent(message_id="a1"))
    t.append_event({"type": "RUN_FINISHED"})

    # Synthetic system event
    synthetic_delta = f"{SYNTHETIC_MESSAGE_INDICATOR} User clicked 'approve' on artifact 'plan-1'"
    t.append_event(TextMessageStartEvent(message_id="sys1", role="user"))
    t.append_event(TextMessageContentEvent(message_id="sys1", delta=synthetic_delta))
    t.append_event(TextMessageEndEvent(message_id="sys1"))
    t.append_event({"type": "RUN_STARTED"})
    t.append_event(TextMessageStartEvent(message_id="a2", role="assistant"))
    t.append_event(TextMessageContentEvent(message_id="a2", delta="Second answer"))
    t.append_event(TextMessageEndEvent(message_id="a2"))
    t.append_event({"type": "RUN_FINISHED"})

    # 1. Branch BEFORE user message u1:
    # Gets back to waiting for user message; branch from point where it wasn't sent yet
    s_u1_before = store.branch_session(
        agent_identifier="user-branch-agent",
        session_identifier="parent",
        target_id="u1",
        position="before",
    )
    t_u1_b = s_u1_before.get_open_thread()
    assert t_u1_b.status == AgentStatus.AWAITING_USER
    assert len(t_u1_b.events) == 0

    # 2. Branch AFTER user message u1:
    # Starts from inference on that user message
    s_u1_after = store.branch_session(
        agent_identifier="user-branch-agent",
        session_identifier="parent",
        target_id="u1",
        position="after",
    )
    t_u1_a = s_u1_after.get_open_thread()
    assert t_u1_a.status == AgentStatus.AWAITING_LLM
    assert len(t_u1_a.events) == 3  # Start, content, end for u1

    # 3. Branch BEFORE system event sys1:
    # Gets back to waiting for user message before synthetic event was sent (has u1 + a1)
    s_sys_before = store.branch_session(
        agent_identifier="user-branch-agent",
        session_identifier="parent",
        target_id="sys1",
        position="before",
    )
    t_sys_b = s_sys_before.get_open_thread()
    assert t_sys_b.status == AgentStatus.AWAITING_USER
    assert len(t_sys_b.events) == 8  # 3 user events + 5 assistant events from turn 1

    # 4. Branch AFTER system event sys1:
    # Starts from inference on that synthetic event
    s_sys_after = store.branch_session(
        agent_identifier="user-branch-agent",
        session_identifier="parent",
        target_id="sys1",
        position="after",
    )
    t_sys_a = s_sys_after.get_open_thread()
    assert t_sys_a.status == AgentStatus.AWAITING_LLM
    assert len(t_sys_a.events) == 11  # 8 from turn 1 + 3 events for sys1


def test_granular_branch_before_and_after_tool_calls_and_reasoning() -> None:
    store = HarnessStore()
    config = make_complete_config()
    store.create_agent(config=config, name="tool-reason-agent")
    s = store.create_session("tool-reason-agent", name="parent")
    t = s.get_open_thread()

    t.append_event(TextMessageStartEvent(message_id="u1", role="user"))
    t.append_event(TextMessageContentEvent(message_id="u1", delta="Execute command"))
    t.append_event(TextMessageEndEvent(message_id="u1"))
    t.append_event({"type": "RUN_STARTED"})

    # Reasoning block
    t.append_event({"type": "REASONING_START", "message_id": "r1"})
    t.append_event(
        {"type": "REASONING_MESSAGE_CONTENT", "message_id": "r1", "delta": "Thinking..."}
    )
    t.append_event({"type": "REASONING_END", "message_id": "r1"})

    # Tool call
    t.append_event({"type": "TOOL_CALL_START", "tool_call_id": "call-1", "tool_call_name": "bash"})
    t.append_event({"type": "TOOL_CALL_ARGS", "tool_call_id": "call-1", "args": '{"command":"ls"}'})
    t.append_event({"type": "TOOL_CALL_END", "tool_call_id": "call-1"})
    t.append_event({"type": "TOOL_CALL_RESULT", "tool_call_id": "call-1", "content": "file.txt"})

    # Assistant message
    t.append_event(TextMessageStartEvent(message_id="a1", role="assistant"))
    t.append_event(TextMessageContentEvent(message_id="a1", delta="Done listing"))
    t.append_event(TextMessageEndEvent(message_id="a1"))
    t.append_event({"type": "RUN_FINISHED"})

    # 1. Branch BEFORE tool call:
    # Slices before TOOL_CALL_RESULT so tool can re-execute in new session
    s_tc_before = store.branch_session(
        agent_identifier="tool-reason-agent",
        session_identifier="parent",
        target_id="call-1",
        position="before",
    )
    t_tc_b = s_tc_before.get_open_thread()
    assert t_tc_b.status == AgentStatus.AWAITING_LLM
    # Sliced events include: u1(3) + RUN_STARTED(1) + reasoning(3) + tool calls(3) = 10 events
    assert len(t_tc_b.events) == 10
    last_ev_b = t_tc_b.events[-1]
    assert (getattr(last_ev_b, "type", None) or last_ev_b.get("type")) == "TOOL_CALL_END"

    # 2. Branch AFTER tool call:
    # Slices after TOOL_CALL_RESULT so result is preserved and inference continues
    s_tc_after = store.branch_session(
        agent_identifier="tool-reason-agent",
        session_identifier="parent",
        target_id="call-1",
        position="after",
    )
    t_tc_a = s_tc_after.get_open_thread()
    assert t_tc_a.status == AgentStatus.AWAITING_LLM
    # Sliced events include through TOOL_CALL_RESULT = 11 events
    assert len(t_tc_a.events) == 11
    last_ev_a = t_tc_a.events[-1]
    assert (getattr(last_ev_a, "type", None) or last_ev_a.get("type")) == "TOOL_CALL_RESULT"

    # 3. Branch BEFORE reasoning:
    s_r_before = store.branch_session(
        agent_identifier="tool-reason-agent",
        session_identifier="parent",
        target_id="r1",
        position="before",
    )
    t_r_b = s_r_before.get_open_thread()
    assert t_r_b.status == AgentStatus.AWAITING_LLM
    # Slices before REASONING_START: u1(3) + RUN_STARTED(1) = 4 events
    assert len(t_r_b.events) == 4

    # 4. Branch AFTER reasoning:
    s_r_after = store.branch_session(
        agent_identifier="tool-reason-agent",
        session_identifier="parent",
        target_id="r1",
        position="after",
    )
    t_r_a = s_r_after.get_open_thread()
    assert t_r_a.status == AgentStatus.AWAITING_LLM
    # Slices after REASONING_END: 4 + 3 = 7 events
    assert len(t_r_a.events) == 7

    # 5. Branch BEFORE bot message a1:
    s_a_before = store.branch_session(
        agent_identifier="tool-reason-agent",
        session_identifier="parent",
        target_id="a1",
        position="before",
    )
    t_a_b = s_a_before.get_open_thread()
    assert t_a_b.status == AgentStatus.AWAITING_LLM
    # Slices before TextMessageStartEvent for a1: 11 events
    assert len(t_a_b.events) == 11

    # 6. Branch AFTER bot message a1 (end of turn):
    s_a_after = store.branch_session(
        agent_identifier="tool-reason-agent",
        session_identifier="parent",
        target_id="a1",
        position="after",
    )
    t_a_a = s_a_after.get_open_thread()
    assert t_a_a.status == AgentStatus.AWAITING_USER
    # Full turn: 15 events
    assert len(t_a_a.events) == 15


def test_api_granular_branching() -> None:
    store = HarnessStore()
    reset_harness_store(store)
    reset_runner_registry()
    config = make_complete_config()
    store.create_agent(config=config, name="api-granular-agent")
    s = store.create_session("api-granular-agent", name="api-parent")
    t = s.get_open_thread()

    t.append_event(TextMessageStartEvent(message_id="u1", role="user"))
    t.append_event(TextMessageContentEvent(message_id="u1", delta="Prompt 1"))
    t.append_event(TextMessageEndEvent(message_id="u1"))
    t.append_event({"type": "RUN_STARTED"})
    t.append_event(TextMessageStartEvent(message_id="a1", role="assistant"))
    t.append_event(TextMessageContentEvent(message_id="a1", delta="Response 1"))
    t.append_event(TextMessageEndEvent(message_id="a1"))
    t.append_event({"type": "RUN_FINISHED"})

    app = create_app()
    client = TestClient(app)

    # Branch before user message via API
    res_b = client.post(
        f"/api/v-alpha/agent/api-granular-agent/session/{s.id}/branch",
        json={"target_id": "u1", "position": "before", "item_type": "user_message"},
    )
    assert res_b.status_code == 201
    data_b = res_b.json()
    assert data_b["provenance"]["parent_message_id"] == "u1"

    # Branch after assistant message via API
    res_a = client.post(
        f"/api/v-alpha/agent/api-granular-agent/session/{s.id}/branch",
        json={"target_id": "a1", "position": "after", "item_type": "bot_message"},
    )
    assert res_a.status_code == 201
    data_a = res_a.json()
    assert data_a["provenance"]["parent_message_id"] == "a1"
    assert data_a["provenance"]["branch_position"] == "after"


def test_tool_grouping_branching() -> None:
    store = HarnessStore()
    config = make_complete_config()
    store.create_agent(config=config, name="tool-group-agent")
    s = store.create_session("tool-group-agent", name="parent")
    t = s.get_open_thread()

    # User message
    t.append_event(TextMessageStartEvent(message_id="u1", role="user"))
    t.append_event(TextMessageContentEvent(message_id="u1", delta="Run tools"))
    t.append_event(TextMessageEndEvent(message_id="u1"))
    t.append_event({"type": "RUN_STARTED"})

    # Tool group: two tool calls in single inference
    # 1. tc1 call
    t.append_event({"type": "TOOL_CALL_START", "tool_call_id": "tc1", "tool_call_name": "tool_a"})
    t.append_event({"type": "TOOL_CALL_ARGS", "tool_call_id": "tc1", "args": "{}"})
    t.append_event({"type": "TOOL_CALL_END", "tool_call_id": "tc1"})
    # 2. tc2 call
    t.append_event({"type": "TOOL_CALL_START", "tool_call_id": "tc2", "tool_call_name": "tool_b"})
    t.append_event({"type": "TOOL_CALL_ARGS", "tool_call_id": "tc2", "args": "{}"})
    t.append_event({"type": "TOOL_CALL_END", "tool_call_id": "tc2"})
    # Results
    t.append_event({"type": "TOOL_CALL_RESULT", "tool_call_id": "tc1", "content": "res1"})
    t.append_event({"type": "TOOL_CALL_RESULT", "tool_call_id": "tc2", "content": "res2"})
    t.append_event({"type": "RUN_FINISHED"})

    # Branch BEFORE tc2 in group: restarts ALL tools in the group
    s_b = store.branch_session(
        agent_identifier="tool-group-agent",
        session_identifier="parent",
        target_id="tc2",
        position="before",
    )
    t_b = s_b.get_open_thread()
    assert t_b.status == AgentStatus.AWAITING_LLM
    # Events should include u1 (3) + RUN_STARTED (1)
    # + tc1 start/args/end (3) + tc2 start/args/end (3) = 10 events
    assert len(t_b.events) == 10
    ev_types = [getattr(e, "type", None) or e.get("type") for e in t_b.events]
    assert "TOOL_CALL_RESULT" not in ev_types
    assert s_b.provenance is not None
    assert s_b.provenance.branch_position == "before"

    # Branch AFTER tc1 in group: includes ALL tool results in the group
    s_a = store.branch_session(
        agent_identifier="tool-group-agent",
        session_identifier="parent",
        target_id="tc1",
        position="after",
    )
    t_a = s_a.get_open_thread()
    assert t_a.status == AgentStatus.AWAITING_LLM
    # Slices after tc2 result: 10 + 2 results = 12 events
    assert len(t_a.events) == 12
    a_types = [getattr(e, "type", None) or e.get("type") for e in t_a.events]
    assert a_types.count("TOOL_CALL_RESULT") == 2
    assert s_a.provenance is not None
    assert s_a.provenance.branch_position == "after"


def test_branching_preserves_mode_and_phase() -> None:
    store = HarnessStore()
    config = make_complete_config()
    store.create_agent(config=config, name="mode-agent")
    s = store.create_session("mode-agent", name="parent")
    t = s.get_open_thread()
    t.mode = "plan"
    t.phase = "make"

    t.append_event(TextMessageStartEvent(message_id="u1", role="user"))
    t.append_event(TextMessageContentEvent(message_id="u1", delta="Hello"))
    t.append_event(TextMessageEndEvent(message_id="u1"))

    child = store.branch_session(
        agent_identifier="mode-agent",
        session_identifier="parent",
        target_id="u1",
        position="after",
    )
    assert child.config.mode == "plan"
    child_thread = child.get_open_thread()
    assert child_thread.mode == "plan"
    assert child_thread.phase == "make"
