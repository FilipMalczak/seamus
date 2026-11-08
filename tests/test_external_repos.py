"""Tests for external Git repository management, URL derivation, and dual-index checkpointing."""

import subprocess
from pathlib import Path
from uuid import uuid4

import pytest

from seamus.config.models import AgentConfig, ExternalRepositoryConfig
from seamus.persistence.config import PersistenceSettings
from seamus.persistence.external_repo import (
    ExternalRepositoryManager,
    calculate_mount_paths,
    canonicalize_git_url,
    derive_project_id,
    derive_repository_mount_name,
)


def test_derive_repository_mount_name() -> None:
    assert derive_repository_mount_name("https://github.com/FilipMalczak/seamus.git") == "seamus"
    assert derive_repository_mount_name("https://github.com/FilipMalczak/seamus/") == "seamus"
    assert derive_repository_mount_name("https://github.com/example/payments-api") == "payments-api"
    assert derive_repository_mount_name("git@github.com:example/service.git") == "service"
    assert derive_repository_mount_name("https://example.com/a/b/c/") == "c"
    assert derive_repository_mount_name("../escape/attempt") == "attempt"
    assert derive_repository_mount_name("") == "repo"


def test_calculate_mount_paths_unique() -> None:
    repos = [
        ExternalRepositoryConfig(id="1", url="https://github.com/FilipMalczak/seamus.git"),
        ExternalRepositoryConfig(id="2", url="https://github.com/example/payments-api"),
    ]
    mapping = calculate_mount_paths(repos)
    assert mapping["1"] == "seamus"
    assert mapping["2"] == "payments-api"


def test_calculate_mount_paths_collision_numeric_suffixes() -> None:
    repos = [
        ExternalRepositoryConfig(id="a", url="https://github.com/team-a/core.git"),
        ExternalRepositoryConfig(id="b", url="https://github.com/team-b/core.git"),
        ExternalRepositoryConfig(id="c", url="https://github.com/team-c/core.git"),
        ExternalRepositoryConfig(id="d", url="https://github.com/other/unique.git"),
    ]
    mapping = calculate_mount_paths(repos)
    assert mapping["a"] == "core_0"
    assert mapping["b"] == "core_1"
    assert mapping["c"] == "core_2"
    assert mapping["d"] == "unique"


def test_canonicalize_git_url_and_project_id() -> None:
    url1 = "https://github.com/FilipMalczak/seamus.git"
    url2 = "https://github.com/filipmalczak/seamus/"
    assert canonicalize_git_url(url1) == "https://github.com/filipmalczak/seamus"
    assert canonicalize_git_url(url2) == "https://github.com/filipmalczak/seamus"
    assert derive_project_id(url1) == derive_project_id(url2)


def test_external_repository_config_validation() -> None:
    with pytest.raises(ValueError, match="Git repository URL cannot be empty"):
        ExternalRepositoryConfig(url="")

    with pytest.raises(ValueError, match="Branch name cannot be empty"):
        ExternalRepositoryConfig(url="https://example.com/repo", branch="")

    with pytest.raises(ValueError, match="Invalid git branch name"):
        ExternalRepositoryConfig(url="https://example.com/repo", branch="bad branch")

    with pytest.raises(ValueError, match="Invalid git branch name"):
        ExternalRepositoryConfig(url="https://example.com/repo", branch="-starts-with-dash")

    # Disallowed version in user secret expressions
    with pytest.raises(ValueError, match="disallowed in user configurations"):
        ExternalRepositoryConfig(
            url="https://example.com/repo",
            credentials="${secret(path='/git/creds', version=2)}",
        )

    # Valid secret expression
    cfg = ExternalRepositoryConfig(
        url="https://example.com/repo",
        credentials="${secret('/git/creds')}",
    )
    assert cfg.credentials == "${secret('/git/creds')}"


def test_agent_config_repositories_copy_with_overrides() -> None:
    repo1 = ExternalRepositoryConfig(id="r1", url="https://github.com/example/r1.git")
    repo2 = ExternalRepositoryConfig(id="r2", url="https://github.com/example/r2.git")

    base = AgentConfig(repositories=[repo1])
    copied = base.copy_with_overrides()
    assert len(copied.repositories) == 1
    assert copied.repositories[0].id == "r1"

    overridden = base.copy_with_overrides(AgentConfig(repositories=[repo2]))
    assert len(overridden.repositories) == 1
    assert overridden.repositories[0].id == "r2"


def test_dual_index_checkpoint_and_restoration(tmp_path: Path) -> None:
    ws_root = tmp_path / "workspaces"
    settings = PersistenceSettings(workspace_dir=ws_root, enabled=False)
    manager = ExternalRepositoryManager(workspace_root=ws_root, settings=settings)

    agent_id = uuid4()
    session_id = uuid4()
    repo_cfg = ExternalRepositoryConfig(
        id="att-1",
        url="https://github.com/example/my-project.git",
        branch="main",
    )
    mount_name = "my-project"

    # 1. Provision working copy
    repo_dir = manager.provision_session_working_copy(
        agent_id=agent_id,
        session_id=session_id,
        repo_config=repo_cfg,
        mount_name=mount_name,
    )
    assert (repo_dir / ".git").exists()
    assert (repo_dir / "README.md").exists()

    # 2. Add a .gitignore file
    (repo_dir / ".gitignore").write_text("*.log\nnode_modules/\n", encoding="utf-8")
    subprocess.run(["git", "add", ".gitignore"], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "-m", "Add .gitignore"], cwd=repo_dir, check=True)

    # 3. Simulate agent making modifications:
    # - Stage file "staged.txt" in ordinary index
    (repo_dir / "staged.txt").write_text("Staged content", encoding="utf-8")
    subprocess.run(["git", "add", "staged.txt"], cwd=repo_dir, check=True)

    # - Modify "README.md" without staging (unstaged working tree edit)
    (repo_dir / "README.md").write_text("# Updated Title\n", encoding="utf-8")

    # - Create untracked non-ignored file "untracked.py"
    (repo_dir / "untracked.py").write_text("print('hello')\n", encoding="utf-8")

    # - Create ignored file "debug.log"
    (repo_dir / "debug.log").write_text("ignore me", encoding="utf-8")

    # Check git status before checkpoint
    status_before = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo_dir, capture_output=True, text=True, check=True
    ).stdout

    assert "A  staged.txt" in status_before
    assert " M README.md" in status_before
    assert "?? untracked.py" in status_before
    assert "debug.log" not in status_before

    # 4. Take dual-index checkpoint
    record = manager.checkpoint_working_copy(
        agent_id=agent_id,
        session_id=session_id,
        repo_config=repo_cfg,
        mount_name=mount_name,
        checkpoint_id="cp-test-1",
    )

    assert record.mount_name == mount_name
    assert record.attachment_id == "att-1"
    assert record.checkpoint_sha
    assert record.snapshot_tree
    assert record.staged_tree
    assert record.semantic_head
    assert record.gitea_repo_name == f"project-{derive_project_id(repo_cfg.url)}"

    # 5. VERIFY AGENT INDEX UNTOUCHED INVARIANT:
    # git status after checkpoint MUST BE 100% IDENTICAL to before checkpoint!
    status_after = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo_dir, capture_output=True, text=True, check=True
    ).stdout
    assert status_after == status_before

    # 6. Verify checkpoint tree contains staged, modified, and untracked files (no ignored files)
    tree_ls = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", record.snapshot_tree],
        cwd=repo_dir,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()

    assert "staged.txt" in tree_ls
    assert "README.md" in tree_ls
    assert "untracked.py" in tree_ls
    assert "debug.log" not in tree_ls

    # 7. Test historical state restoration
    # Wipe the working tree modifications
    subprocess.run(["git", "reset", "--hard", "HEAD"], cwd=repo_dir, check=True)
    subprocess.run(["git", "clean", "-fdx"], cwd=repo_dir, check=True)

    status_clean = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo_dir, capture_output=True, text=True, check=True
    ).stdout
    assert status_clean == ""

    # Restore from record
    manager.restore_working_copy_checkpoint(agent_id, session_id, record)

    # Verify status after restoration matches original state
    status_restored = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo_dir, capture_output=True, text=True, check=True
    ).stdout
    assert "A  staged.txt" in status_restored
    assert " M README.md" in status_restored
    assert "?? untracked.py" in status_restored
    assert (repo_dir / "staged.txt").read_text(encoding="utf-8") == "Staged content"
    assert (repo_dir / "README.md").read_text(encoding="utf-8") == "# Updated Title\n"
    assert (repo_dir / "untracked.py").read_text(encoding="utf-8") == "print('hello')\n"
