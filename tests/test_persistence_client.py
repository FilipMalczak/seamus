"""Unit tests for GiteaClient API operations and error handling."""

from unittest.mock import MagicMock, patch

import pytest

from seamus.persistence.client import GiteaAPIError, GiteaClient
from seamus.persistence.config import PersistenceSettings


@pytest.fixture
def test_settings() -> PersistenceSettings:
    return PersistenceSettings(
        gitea_url="http://test-gitea:3000",
        gitea_external_url="http://localhost:3001",
        gitea_admin_user="testuser",
        gitea_admin_password="testpassword",
        gitea_admin_email="test@test.local",
        enabled=True,
    )


def test_client_is_healthy_success(test_settings: PersistenceSettings) -> None:
    client = GiteaClient(test_settings)
    mock_response = MagicMock()
    mock_response.status_code = 200

    with patch("httpx.Client.get", return_value=mock_response):
        assert client.is_healthy() is True


def test_client_is_healthy_failure(test_settings: PersistenceSettings) -> None:
    client = GiteaClient(test_settings)
    with patch("httpx.Client.get", side_effect=Exception("Connection refused")):
        assert client.is_healthy() is False


def test_client_ensure_admin_user(test_settings: PersistenceSettings) -> None:
    client = GiteaClient(test_settings)
    mock_response = MagicMock()
    mock_response.status_code = 200

    with patch("httpx.Client.get", return_value=mock_response):
        assert client.ensure_admin_user() is True


def test_client_get_or_create_repo_existing(test_settings: PersistenceSettings) -> None:
    client = GiteaClient(test_settings)
    mock_get = MagicMock()
    mock_get.status_code = 200
    mock_get.json.return_value = {"id": 1, "name": "agent-123"}

    with patch("httpx.Client.get", return_value=mock_get):
        res = client.get_or_create_repo("agent-123")
        assert res["name"] == "agent-123"


def test_client_get_or_create_repo_created(test_settings: PersistenceSettings) -> None:
    client = GiteaClient(test_settings)
    mock_get = MagicMock()
    mock_get.status_code = 404

    mock_post = MagicMock()
    mock_post.status_code = 201
    mock_post.json.return_value = {"id": 2, "name": "agent-new"}

    with patch("httpx.Client.get", return_value=mock_get):
        with patch("httpx.Client.post", return_value=mock_post) as mock_post_call:
            res = client.get_or_create_repo("agent-new")
            assert res["name"] == "agent-new"
            assert mock_post_call.call_args is not None
            create_payload = mock_post_call.call_args.kwargs["json"]
            assert create_payload["private"] is False


def test_client_get_or_create_repo_error(test_settings: PersistenceSettings) -> None:
    client = GiteaClient(test_settings)
    mock_get = MagicMock()
    mock_get.status_code = 500
    mock_get.text = "Internal error"

    with patch("httpx.Client.get", return_value=mock_get):
        with pytest.raises(GiteaAPIError):
            client.get_or_create_repo("agent-err")


def test_client_list_user_repos(test_settings: PersistenceSettings) -> None:
    client = GiteaClient(test_settings)
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [{"name": "agent-1"}, {"name": "agent-2"}]

    with patch("httpx.Client.get", return_value=mock_response):
        repos = client.list_user_repos()
        assert len(repos) == 2
        assert repos[0]["name"] == "agent-1"


def test_client_list_branches(test_settings: PersistenceSettings) -> None:
    client = GiteaClient(test_settings)
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [{"name": "main"}, {"name": "session/123"}]

    with patch("httpx.Client.get", return_value=mock_response):
        branches = client.list_branches("agent-1")
        assert branches == ["main", "session/123"]


def test_client_get_file_content(test_settings: PersistenceSettings) -> None:
    client = GiteaClient(test_settings)
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = '{"key": "value"}'

    with patch("httpx.Client.get", return_value=mock_response):
        content = client.get_file_content("agent-1", "main", "config/config.json")
        assert content == '{"key": "value"}'


def test_client_get_authenticated_clone_url(test_settings: PersistenceSettings) -> None:
    client = GiteaClient(test_settings)
    url = client.get_authenticated_clone_url("agent-123")
    assert url == "http://testuser:testpassword@test-gitea:3000/testuser/agent-123.git"


def test_client_create_pull_request(test_settings: PersistenceSettings) -> None:
    client = GiteaClient(test_settings)
    mock_post = MagicMock()
    mock_post.status_code = 201
    mock_post.json.return_value = {"id": 1, "number": 42, "title": "Sync PR"}

    with patch("httpx.Client.post", return_value=mock_post) as mock_post_call:
        res = client.create_pull_request(
            repo_name="agent-123",
            title="Sync PR",
            head="session/abc",
            base="main",
            body="Automated sync",
        )
        assert res["number"] == 42
        payload = mock_post_call.call_args.kwargs["json"]
        assert payload["head"] == "session/abc"
        assert payload["base"] == "main"


def test_client_get_pull_request(test_settings: PersistenceSettings) -> None:
    client = GiteaClient(test_settings)
    mock_get = MagicMock()
    mock_get.status_code = 200
    mock_get.json.return_value = {"number": 42, "mergeable": True}

    with patch("httpx.Client.get", return_value=mock_get):
        res = client.get_pull_request("agent-123", 42)
        assert res["number"] == 42
        assert res["mergeable"] is True


def test_client_list_pull_requests(test_settings: PersistenceSettings) -> None:
    client = GiteaClient(test_settings)
    mock_get = MagicMock()
    mock_get.status_code = 200
    mock_get.json.return_value = [{"number": 1, "head": {"ref": "session/abc"}}]

    with patch("httpx.Client.get", return_value=mock_get):
        res = client.list_pull_requests("agent-123", state="open")
        assert len(res) == 1
        assert res[0]["number"] == 1


def test_client_approve_pull_request_success(test_settings: PersistenceSettings) -> None:
    client = GiteaClient(test_settings)
    mock_post = MagicMock()
    mock_post.status_code = 200
    mock_post.json.return_value = {"state": "APPROVED"}

    with patch("httpx.Client.post", return_value=mock_post):
        res = client.approve_pull_request("agent-123", 1)
        assert res is not None
        assert res["state"] == "APPROVED"


def test_client_approve_pull_request_self_rejected(test_settings: PersistenceSettings) -> None:
    client = GiteaClient(test_settings)
    mock_post = MagicMock()
    mock_post.status_code = 422
    mock_post.text = "approve your own pull is not allowed"

    with patch("httpx.Client.post", return_value=mock_post):
        res = client.approve_pull_request("agent-123", 1)
        assert res is None


def test_client_merge_pull_request(test_settings: PersistenceSettings) -> None:
    client = GiteaClient(test_settings)
    mock_post = MagicMock()
    mock_post.status_code = 200

    with patch("httpx.Client.post", return_value=mock_post) as mock_post_call:
        res = client.merge_pull_request("agent-123", 1, do="merge", delete_branch=False)
        assert res is True
        payload = mock_post_call.call_args.kwargs["json"]
        assert payload["Do"] == "merge"
        assert payload["delete_branch_after_merge"] is False


def test_client_get_pull_request_diff(test_settings: PersistenceSettings) -> None:
    client = GiteaClient(test_settings)
    mock_get = MagicMock()
    mock_get.status_code = 200
    mock_get.text = "diff --git a/test b/test\n+line"

    with patch("httpx.Client.get", return_value=mock_get):
        diff = client.get_pull_request_diff("agent-123", 1)
        assert diff == "diff --git a/test b/test\n+line"


def test_client_get_pull_request_diff_404(test_settings: PersistenceSettings) -> None:
    client = GiteaClient(test_settings)
    mock_get = MagicMock()
    mock_get.status_code = 404

    with patch("httpx.Client.get", return_value=mock_get):
        diff = client.get_pull_request_diff("agent-123", 1)
        assert diff == ""
