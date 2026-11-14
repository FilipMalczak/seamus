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
    from seamus.harness.artifacts import ArtifactBuilder

    ArtifactBuilder.create_artifact(
        artifacts_dir=artifacts_dir,
        family="questionnaires",
        uuid="q-123",
        manifest={
            "name": "q-123",
            "exposition": "embedded",
            "blocking": True,
            "commentable": False,
            "buttons": [
                {
                    "id": "submit",
                    "mode": "set",
                    "clicks": 1,
                    "unblocking": True,
                    "closing": True,
                }
            ],
        },
        components=[
            {"id": "col", "component": "Column", "children": ["submit"]},
            {"id": "submit", "component": "Button", "title": "Submit"},
        ],
    )

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. List artifacts
        list_res = await client.get(f"/api/v-alpha/agent/{agent_id}/session/{session_id}/artifact")
        assert list_res.status_code == 200
        arts = list_res.json()
        assert len(arts) == 1
        assert arts[0]["name"] == "q-123"
        assert arts[0]["is_closed"] is False
        assert arts[0]["manifest"]["blocking"] is True

        # 2. Get artifact detail
        get_res = await client.get(
            f"/api/v-alpha/agent/{agent_id}/session/{session_id}/artifact/questionnaires/q-123"
        )
        assert get_res.status_code == 200
        assert get_res.json()["name"] == "q-123"

        # 3. Sending chat input should return 409 Conflict due to blocking artifact!
        input_res = await client.post(
            f"/api/v-alpha/agent/{agent_id}/session/{session_id}/input",
            json={"text": "Hello agent!"},
        )
        assert input_res.status_code == 409
        assert "open blocking" in input_res.json()["detail"]


@pytest.mark.asyncio
async def test_artifact_click_closes_and_updates_state(tmp_path: Any, monkeypatch: Any) -> None:
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
    from seamus.harness.artifacts import ArtifactBuilder, seed_default_artifacts

    seed_default_artifacts(artifacts_dir)

    ArtifactBuilder.create_artifact(
        artifacts_dir=artifacts_dir,
        family="questionnaires",
        uuid="q-456",
        manifest={
            "name": "q-456",
            "exposition": "embedded",
            "blocking": True,
            "commentable": False,
            "buttons": [
                {
                    "id": "submit",
                    "mode": "set",
                    "clicks": 1,
                    "unblocking": True,
                    "closing": True,
                }
            ],
        },
        components=[
            {"id": "col", "component": "Column", "children": ["submit"]},
            {"id": "submit", "component": "Button", "title": "Submit"},
        ],
    )

    from seamus.harness.runner import get_runner_registry

    runner = get_runner_registry().get_runner(session, agent=agent)

    # Monkeypatch runner._run_loop so it doesn't try calling an LLM
    async def mock_run_loop(thread: Any, user_message: Any = None) -> None:
        pass

    monkeypatch.setattr(runner, "_run_loop", mock_run_loop)

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Test click via family/uuid route
        click_res = await client.post(
            f"/api/v-alpha/agent/{agent_id}/session/{session_id}/artifact/questionnaires/q-456/click",
            json={
                "button_id": "submit",
                "context": {"backgroundColor": "blue", "headerStyle": "bold"},
            },
        )
        assert click_res.status_code == 200
        body = click_res.json()
        assert body["artifact_id"] == "q-456"
        assert body["button_id"] == "submit"
        assert body["context"] == {"backgroundColor": "blue", "headerStyle": "bold"}
        assert "timestamp" in body

        # Check interaction file was written
        q_dir = artifacts_dir / "questionnaires" / "q-456"
        interaction_file = q_dir / "interactions" / "submit.jsonl"
        assert interaction_file.is_file()
        import json

        lines = [line for line in interaction_file.read_text().strip().splitlines() if line]
        assert len(lines) == 1
        data_content = json.loads(lines[0])
        assert data_content["context"]["backgroundColor"] == "blue"

        # Check closed marker was written
        marker_file = q_dir / "closed.marker"
        assert marker_file.is_file()

        # Check state file was updated
        state_file = q_dir / "state.json"
        state_data = json.loads(state_file.read_text())
        assert state_data["clicksLeft"]["submit"] == 0
        assert state_data["last_event"]["context"]["backgroundColor"] == "blue"


@pytest.mark.asyncio
async def test_artifact_routes_corrupted_manifest_deleted_dir_and_quota_exhausted(
    tmp_path: Any, monkeypatch: Any
) -> None:
    """I-L-006, E-E-002, E-E-006: Corrupted manifest, deleted dir, and exhausted quota."""
    import shutil

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
    agent = store.create_agent(config=agent_config, name="test-agent-err")
    session = store.create_session(
        agent_identifier=str(agent.id),
        config=agent_config,
        name="test-session-err",
    )

    from seamus.harness.artifacts import ArtifactBuilder

    artifacts_dir = ws_mgr.get_session_artifacts_dir(agent.id, session.id)
    ArtifactBuilder.create_artifact(
        artifacts_dir=artifacts_dir,
        family="custom",
        uuid="single-click",
        manifest={
            "name": "Single Click",
            "exposition": "embedded",
            "blocking": False,
            "buttons": [{"id": "once", "clicks": 1}],
        },
        components=[
            {"id": "root", "component": "Column", "children": ["once"]},
            {"id": "once", "component": "Button", "child": "lbl"},
            {"id": "lbl", "component": "Text", "text": "Once"},
        ],
    )

    # Corrupted manifest.json
    bad_dir = artifacts_dir / "custom" / "corrupt-art"
    bad_dir.mkdir(parents=True, exist_ok=True)
    (bad_dir / "body.json").write_text("[]", encoding="utf-8")
    (bad_dir / "manifest.json").write_text("{ bad json", encoding="utf-8")

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # I-L-006: Corrupted manifest returns 400
        bad_res = await client.get(
            f"/api/v-alpha/agent/{agent.id}/session/{session.id}/artifact/custom/corrupt-art"
        )
        assert bad_res.status_code == 400

        # E-E-006: First click succeeds; immediate second click rejected with 400
        ok_click = await client.post(
            f"/api/v-alpha/agent/{agent.id}/session/{session.id}/artifact/custom/single-click/click",
            json={"button_id": "once"},
        )
        assert ok_click.status_code == 200
        dup_click = await client.post(
            f"/api/v-alpha/agent/{agent.id}/session/{session.id}/artifact/custom/single-click/click",
            json={"button_id": "once"},
        )
        assert dup_click.status_code == 400

        # E-E-002: Delete directory on disk -> 404 by UUID, 400 by family/UUID
        shutil.rmtree(artifacts_dir / "custom" / "single-click")
        gone_by_uuid = await client.post(
            f"/api/v-alpha/agent/{agent.id}/session/{session.id}/artifact/single-click/click",
            json={"button_id": "once"},
        )
        assert gone_by_uuid.status_code == 404
        gone_by_family = await client.post(
            f"/api/v-alpha/agent/{agent.id}/session/{session.id}/artifact/custom/single-click/click",
            json={"button_id": "once"},
        )
        assert gone_by_family.status_code == 400


@pytest.mark.asyncio
async def test_artifact_routes_session_isolation(tmp_path: Any, monkeypatch: Any) -> None:
    """E-F-004: Two sessions maintain isolated artifact lists and states."""
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
    agent = store.create_agent(config=agent_config, name="iso-agent")
    s1 = store.create_session(agent_identifier=str(agent.id), config=agent_config, name="s1")
    s2 = store.create_session(agent_identifier=str(agent.id), config=agent_config, name="s2")

    from seamus.harness.artifacts import ArtifactBuilder

    ArtifactBuilder.create_artifact(
        artifacts_dir=ws_mgr.get_session_artifacts_dir(agent.id, s1.id),
        family="custom",
        uuid="art-s1",
        manifest={"name": "S1 Art"},
        components=[{"id": "root", "component": "Text", "text": "S1"}],
    )
    ArtifactBuilder.create_artifact(
        artifacts_dir=ws_mgr.get_session_artifacts_dir(agent.id, s2.id),
        family="custom",
        uuid="art-s2",
        manifest={"name": "S2 Art"},
        components=[{"id": "root", "component": "Text", "text": "S2"}],
    )

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        l1 = await client.get(f"/api/v-alpha/agent/{agent.id}/session/{s1.id}/artifact")
        l2 = await client.get(f"/api/v-alpha/agent/{agent.id}/session/{s2.id}/artifact")
        assert [a["uuid"] for a in l1.json()] == ["art-s1"]
        assert [a["uuid"] for a in l2.json()] == ["art-s2"]

        cross = await client.get(
            f"/api/v-alpha/agent/{agent.id}/session/{s1.id}/artifact/custom/art-s2"
        )
        assert cross.status_code == 404
