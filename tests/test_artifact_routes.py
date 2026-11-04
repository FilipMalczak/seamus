"""Integration tests for artifact REST API endpoints and blocking cadence."""

from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from seamus.config.models import AgentConfig, InferenceConfig
from seamus.harness.store import HarnessStore, reset_harness_store
from seamus.persistence import GitWorkspaceManager, reset_workspace_manager
from seamus.server.app import create_app


@pytest.mark.asyncio
async def test_artifact_rest_routes(tmp_path: Any, monkeypatch: Any) -> None:
    monkeypatch.setenv("SEAMUS_PERSISTENCE_ENABLED", "false")
    ws_mgr = GitWorkspaceManager()
    ws_mgr.workspace_root = tmp_path
    reset_workspace_manager(ws_mgr)

    store = HarnessStore()
    reset_harness_store(store)

    agent_config = AgentConfig(
        model_name="test-model",
        inference=InferenceConfig(api_key="test-key"),
    )
    agent = store.create_agent(config=agent_config, name="test-agent")
    session = store.create_session(
        agent_identifier=str(agent.id),
        config=agent_config,
        name="test-session",
    )
    agent_id = agent.id
    session_id = session.id

    artifacts_dir = ws_mgr.get_session_artifacts_dir(agent_id, session_id)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    from seamus.harness.artifacts import seed_default_artifacts

    seed_default_artifacts(artifacts_dir)

    # Create an artifact directory for testing
    q_dir = artifacts_dir / "questionnaires" / "q-123"
    q_dir.mkdir(parents=True, exist_ok=True)
    (q_dir / "updateComponents.json").write_text('{"components": []}', encoding="utf-8")

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. List artifacts
        list_res = await client.get(f"/api/v-alpha/agent/{agent_id}/session/{session_id}/artifact")
        assert list_res.status_code == 200
        arts = list_res.json()
        assert len(arts) == 1
        assert arts[0]["name"] == "q-123"
        assert arts[0]["is_closed"] is False
        assert arts[0]["manifest"]["cadence"] == "blocking"

        # 2. Get artifact detail
        get_res = await client.get(
            f"/api/v-alpha/agent/{agent_id}/session/{session_id}/artifact/questionnaires/q-123"
        )
        assert get_res.status_code == 200
        assert get_res.json()["name"] == "q-123"

        # 3. Sending chat input should return 409 Conflict due to blocking questionnaire!
        input_res = await client.post(
            f"/api/v-alpha/agent/{agent_id}/session/{session_id}/input",
            json={"text": "Hello agent!"},
        )
        assert input_res.status_code == 409
        assert "open blocking questionnaire" in input_res.json()["detail"]


@pytest.mark.asyncio
async def test_artifact_submit_closes_and_synthesizes_tool_call(
    tmp_path: Any, monkeypatch: Any
) -> None:
    monkeypatch.setenv("SEAMUS_PERSISTENCE_ENABLED", "false")
    ws_mgr = GitWorkspaceManager()
    ws_mgr.workspace_root = tmp_path
    reset_workspace_manager(ws_mgr)

    store = HarnessStore()
    reset_harness_store(store)

    agent_config = AgentConfig(
        model_name="test-model",
        inference=InferenceConfig(api_key="test-key"),
    )
    agent = store.create_agent(config=agent_config, name="test-agent")
    session = store.create_session(
        agent_identifier=str(agent.id),
        config=agent_config,
        name="test-session",
    )
    agent_id = agent.id
    session_id = session.id
    thread = session.get_open_thread()

    artifacts_dir = ws_mgr.get_session_artifacts_dir(agent_id, session_id)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    from seamus.harness.artifacts import seed_default_artifacts

    seed_default_artifacts(artifacts_dir)

    q_dir = artifacts_dir / "questionnaires" / "q-456"
    q_dir.mkdir(parents=True, exist_ok=True)
    (q_dir / "updateComponents.json").write_text('{"components": []}', encoding="utf-8")

    from seamus.harness.runner import get_runner_registry

    runner = get_runner_registry().get_runner(session, agent=agent)

    # Monkeypatch runner._run_loop so it doesn't try calling an LLM
    async def mock_run_loop(thread: Any, user_message: Any = None) -> None:
        pass

    monkeypatch.setattr(runner, "_run_loop", mock_run_loop)

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        submit_res = await client.post(
            f"/api/v-alpha/agent/{agent_id}/session/{session_id}/artifact/questionnaires/q-456/submit",
            json={"data": {"backgroundColor": "blue", "headerStyle": "bold"}},
        )
        assert submit_res.status_code == 202
        body = submit_res.json()
        assert body["status"] == "accepted"
        assert body["artifact_id"] == "q-456"

        # Check canonical data model was written
        data_model_file = q_dir / "updateDataModel.json"
        assert data_model_file.is_file()
        import json

        data_content = json.loads(data_model_file.read_text())
        assert data_content["updateDataModel"]["value"]["backgroundColor"] == "blue"

        # Check deleteSurface was written
        delete_file = q_dir / "deleteSurface.json"
        assert delete_file.is_file()

        # Check tool call events were recorded in thread
        tool_call_starts = [
            e
            for e in thread.events
            if getattr(e, "type", None) == "TOOL_CALL_START"
            or (isinstance(e, dict) and e.get("type") == "TOOL_CALL_START")
        ]
        assert len(tool_call_starts) >= 1
        assert (
            tool_call_starts[-1].get("tool_call_name") == "read_artifact_submission"
            if isinstance(tool_call_starts[-1], dict)
            else tool_call_starts[-1].tool_call_name == "read_artifact_submission"
        )
