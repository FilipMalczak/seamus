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
