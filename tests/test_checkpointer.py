"""Unit tests for GitCheckpointSaver and automated checkpoint data commit triggers."""

from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import empty_checkpoint

from seamus.persistence.checkpointer import GitCheckpointSaver, extract_readable_messages
from seamus.persistence.config import PersistenceSettings
from seamus.persistence.workspace import GitWorkspaceManager


def test_git_checkpoint_saver_put_triggers_commit() -> None:
    agent_id = uuid4()
    session_id = uuid4()
    thread_id = uuid4()

    mock_ws = MagicMock()
    mock_ws.load_all_thread_checkpoints.return_value = []

    saver = GitCheckpointSaver(
        agent_id=agent_id,
        session_id=session_id,
        workspace_manager=mock_ws,
    )

    config: RunnableConfig = {"configurable": {"thread_id": thread_id.hex, "checkpoint_ns": ""}}
    checkpoint = empty_checkpoint()

    res = saver.put(config, checkpoint, {}, {})
    assert res["configurable"]["thread_id"] == thread_id.hex

    mock_ws.commit_checkpoint_changes.assert_called_once_with(
        agent_id=agent_id,
        session_id=session_id,
        thread_id=thread_id,
        checkpoint_id=checkpoint["id"],
    )


@pytest.mark.asyncio
async def test_git_checkpoint_saver_aput_triggers_commit() -> None:
    agent_id = uuid4()
    session_id = uuid4()
    thread_id = uuid4()

    mock_ws = MagicMock()
    mock_ws.load_all_thread_checkpoints.return_value = []

    saver = GitCheckpointSaver(
        agent_id=agent_id,
        session_id=session_id,
        workspace_manager=mock_ws,
    )

    config: RunnableConfig = {"configurable": {"thread_id": thread_id.hex, "checkpoint_ns": ""}}
    checkpoint = empty_checkpoint()

    res = await saver.aput(config, checkpoint, {}, {})
    assert res["configurable"]["thread_id"] == thread_id.hex

    mock_ws.commit_checkpoint_changes.assert_called_once_with(
        agent_id=agent_id,
        session_id=session_id,
        thread_id=thread_id,
        checkpoint_id=checkpoint["id"],
    )


def test_git_checkpoint_saver_disk_reload(tmp_path: Path) -> None:
    agent_id = uuid4()
    session_id = uuid4()
    thread_id = uuid4()

    settings = PersistenceSettings(workspace_dir=tmp_path / "ws", enabled=False)
    ws_mgr = GitWorkspaceManager(settings=settings)

    # Initial saver saves checkpoint
    saver1 = GitCheckpointSaver(
        agent_id=agent_id,
        session_id=session_id,
        workspace_manager=ws_mgr,
    )

    config: RunnableConfig = {"configurable": {"thread_id": thread_id.hex, "checkpoint_ns": ""}}
    cp = empty_checkpoint()
    cp["id"] = "cp-test-1"
    cp["channel_values"] = {"messages": [HumanMessage(content="Hello world")]}
    cp["channel_versions"] = {"messages": 1}

    res_cfg = saver1.put(config, cp, {"source": "input", "step": 1, "parents": {}}, {"messages": 1})
    saver1.put_writes(res_cfg, [("messages", HumanMessage(content="Hello world"))], "task-1")

    # Verify state files created on disk
    thread_dir = ws_mgr.get_thread_state_dir(agent_id, session_id, thread_id)
    assert (thread_dir / "checkpoints.json").exists()
    assert (thread_dir / "messages.json").exists()

    # Second saver loads state from disk
    saver2 = GitCheckpointSaver(
        agent_id=agent_id,
        session_id=session_id,
        workspace_manager=ws_mgr,
    )

    tuple_out = saver2.get_tuple(config)
    assert tuple_out is not None
    assert tuple_out.checkpoint["id"] == "cp-test-1"
    assert tuple_out.checkpoint["channel_values"]["messages"][0].content == "Hello world"
    assert len(tuple_out.pending_writes or []) == 1


def test_extract_readable_messages() -> None:
    msgs = [
        HumanMessage(content="Hello", id="1"),
        AIMessage(
            content="Run command",
            id="2",
            tool_calls=[{"name": "bash", "args": {"cmd": "ls"}, "id": "tc1", "type": "tool_call"}],
        ),
    ]
    cp = empty_checkpoint()
    cp["channel_values"] = {"messages": msgs}
    extracted = extract_readable_messages(cp)
    assert len(extracted) == 2
    assert extracted[0]["role"] == "human"
    assert extracted[0]["content"] == "Hello"
    assert extracted[1]["role"] == "ai"
    assert extracted[1]["tool_calls"][0]["name"] == "bash"
