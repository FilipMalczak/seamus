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


def test_client_merge_pull_request_manually_merged(test_settings: PersistenceSettings) -> None:
    client = GiteaClient(test_settings)
    mock_post = MagicMock()
    mock_post.status_code = 200

    with patch("httpx.Client.post", return_value=mock_post) as mock_post_call:
        res = client.merge_pull_request(
            "agent-123",
            1,
            do="manually-merged",
            delete_branch=False,
            merge_commit_id="abcdef123456",
        )
        assert res is True
        payload = mock_post_call.call_args.kwargs["json"]
        assert payload["Do"] == "manually-merged"
        assert payload["delete_branch_after_merge"] is False
        assert payload["merge_commit_id"] == "abcdef123456"


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


def test_client_get_or_create_org(test_settings: PersistenceSettings) -> None:
    client = GiteaClient(test_settings)
    mock_get = MagicMock()
    mock_get.status_code = 404
    mock_post = MagicMock()
    mock_post.status_code = 201
    mock_post.json.return_value = {"id": 1, "name": "mirrors"}

    with patch("httpx.Client.get", return_value=mock_get):
        with patch("httpx.Client.post", return_value=mock_post) as mock_post_call:
            res = client.get_or_create_org("mirrors")
            assert res["name"] == "mirrors"
            assert mock_post_call.call_args is not None
            assert mock_post_call.call_args.kwargs["json"]["username"] == "mirrors"


def test_client_list_orgs(test_settings: PersistenceSettings) -> None:
    client = GiteaClient(test_settings)
    mock_get = MagicMock()
    mock_get.status_code = 200
    mock_get.json.return_value = [{"name": "mirrors"}, {"name": "agent-123"}]

    with patch("httpx.Client.get", return_value=mock_get):
        orgs = client.list_orgs()
        assert len(orgs) == 2
        assert orgs[0]["name"] == "mirrors"


def test_client_list_org_repos(test_settings: PersistenceSettings) -> None:
    client = GiteaClient(test_settings)
    mock_get = MagicMock()
    mock_get.status_code = 200
    mock_get.json.return_value = [{"name": "agent"}, {"name": "session-1"}]

    with patch("httpx.Client.get", return_value=mock_get):
        repos = client.list_org_repos("agent-123")
        assert len(repos) == 2
        assert repos[0]["name"] == "agent"


def test_client_delete_org(test_settings: PersistenceSettings) -> None:
    client = GiteaClient(test_settings)
    mock_delete = MagicMock()
    mock_delete.status_code = 204

    with patch("httpx.Client.delete", return_value=mock_delete):
        assert client.delete_org("agent-123") is True


def test_client_migrate_repo_as_mirror(test_settings: PersistenceSettings) -> None:
    client = GiteaClient(test_settings)
    mock_post = MagicMock()
    mock_post.status_code = 201
    mock_post.json.return_value = {"id": 10, "name": "project-seamus-12345678"}

    with patch("httpx.Client.post", return_value=mock_post) as mock_post_call:
        res = client.migrate_repo_as_mirror(
            clone_addr="https://github.com/test/repo.git",
            repo_name="project-seamus-12345678",
            repo_owner="mirrors",
            mirror_interval="10m",
            auth_token="token123",
        )
        assert res["name"] == "project-seamus-12345678"
        payload = mock_post_call.call_args.kwargs["json"]
        assert payload["mirror"] is True
        assert payload["mirror_interval"] == "10m"
        assert payload["repo_owner"] == "mirrors"
        assert payload["auth_token"] == "token123"


def test_client_fork_repo(test_settings: PersistenceSettings) -> None:
    client = GiteaClient(test_settings)
    mock_post = MagicMock()
    mock_post.status_code = 202
    mock_post.json.return_value = {"id": 11, "name": "project-seamus-12345678-87654321"}

    with patch("httpx.Client.post", return_value=mock_post) as mock_post_call:
        res = client.fork_repo(
            source_owner="mirrors",
            source_repo="project-seamus-12345678",
            target_org="agent-abc",
            fork_name="project-seamus-12345678-87654321",
        )
        assert res["name"] == "project-seamus-12345678-87654321"
        payload = mock_post_call.call_args.kwargs["json"]
        assert payload["organization"] == "agent-abc"
        assert payload["name"] == "project-seamus-12345678-87654321"


def test_client_get_authenticated_clone_url_with_owner(test_settings: PersistenceSettings) -> None:
    client = GiteaClient(test_settings)
    url = client.get_authenticated_clone_url("project-1", owner="agent-xyz")
    assert url == "http://testuser:testpassword@test-gitea:3000/agent-xyz/project-1.git"


def test_client_rename_org_success(test_settings: PersistenceSettings) -> None:
    client = GiteaClient(test_settings)
    mock_post = MagicMock()
    mock_post.status_code = 204

    with patch("httpx.Client.post", return_value=mock_post) as mock_call:
        res = client.rename_org("agent-1234", "archived-agent-1234")
        assert res is True
        mock_call.assert_called_once()
        assert mock_call.call_args.args[0] == "http://test-gitea:3000/api/v1/orgs/agent-1234/rename"
        assert mock_call.call_args.kwargs["json"] == {"new_name": "archived-agent-1234"}


def test_client_rename_org_failure(test_settings: PersistenceSettings) -> None:
    client = GiteaClient(test_settings)
    mock_post = MagicMock()
    mock_post.status_code = 422
    mock_post.text = "Name already taken"

    with patch("httpx.Client.post", return_value=mock_post):
        with pytest.raises(GiteaAPIError, match="Failed to rename organization"):
            client.rename_org("agent-1234", "archived-agent-1234")


def test_client_archive_repo_success(test_settings: PersistenceSettings) -> None:
    client = GiteaClient(test_settings)
    mock_patch = MagicMock()
    mock_patch.status_code = 200

    with patch("httpx.Client.patch", return_value=mock_patch) as mock_call:
        res = client.archive_repo("session-1234", owner="agent-1234")
        assert res is True
        mock_call.assert_called_once()
        assert (
            mock_call.call_args.args[0]
            == "http://test-gitea:3000/api/v1/repos/agent-1234/session-1234"
        )
        assert mock_call.call_args.kwargs["json"] == {"archived": True}


def test_client_archive_repo_not_found(test_settings: PersistenceSettings) -> None:
    client = GiteaClient(test_settings)
    mock_patch = MagicMock()
    mock_patch.status_code = 404

    with patch("httpx.Client.patch", return_value=mock_patch):
        assert client.archive_repo("session-missing", owner="agent-1234") is False
