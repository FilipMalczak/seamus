"""Git repository lock file detection, concurrency serialization, and stale lock recovery."""

import logging
import os
import re
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# Mutex protecting the registry of repository-specific re-entrant locks
_REPO_LOCKS_MUTEX = threading.Lock()
_REPO_LOCKS: dict[Path, threading.RLock] = {}

LOCK_ERROR_PATTERN = re.compile(
    r"unable to create ['\"]([^'\"]+?\.lock)['\"]: file exists",
    re.IGNORECASE,
)
GENERIC_LOCK_FILE_PATTERN = re.compile(
    r"['\"]([^'\"]+?\.lock)['\"]",
    re.IGNORECASE,
)


def get_repo_lock(repo_dir: Path) -> threading.RLock:
    """Return a process-wide re-entrant lock for the given repository path.

    Serializes mutating Git operations across threads within the backend process to
    prevent internal lock collisions.
    """
    resolved = repo_dir.resolve()
    with _REPO_LOCKS_MUTEX:
        lock = _REPO_LOCKS.get(resolved)
        if lock is None:
            lock = threading.RLock()
            _REPO_LOCKS[resolved] = lock
        return lock


def is_git_process_running_in_repo(repo_dir: Path) -> bool:
    """Check if any active git process is currently running with cwd in the given repository.

    Inspects Linux /proc entries to determine if a running process named 'git'
    has its working directory or target path inside repo_dir.
    """
    try:
        proc_dir = Path("/proc")
        if not proc_dir.is_dir():
            return False

        resolved_repo = repo_dir.resolve()
        for pid_entry in proc_dir.iterdir():
            if not pid_entry.name.isdigit():
                continue
            try:
                # Check comm or cmdline
                comm_file = pid_entry / "comm"
                is_git = False
                if comm_file.exists():
                    comm = comm_file.read_text(encoding="utf-8", errors="ignore").strip()
                    if comm == "git":
                        is_git = True
                if not is_git:
                    cmdline_file = pid_entry / "cmdline"
                    if cmdline_file.exists():
                        cmdline = cmdline_file.read_bytes().decode("utf-8", errors="ignore")
                        if (
                            cmdline.startswith("git\x00")
                            or cmdline.startswith("git ")
                            or "/git" in cmdline.split("\x00")[0]
                        ):
                            is_git = True

                if not is_git:
                    continue

                cwd_link = pid_entry / "cwd"
                if cwd_link.is_symlink():
                    target = Path(os.readlink(cwd_link)).resolve()
                    if (
                        target == resolved_repo
                        or resolved_repo in target.parents
                        or target in resolved_repo.parents
                    ):
                        return True
            except (OSError, PermissionError):
                continue
    except Exception as exc:
        logger.debug("Failed to inspect /proc for active git processes: %s", exc)
        return False

    return False


def extract_lock_paths_from_stderr(stderr: str) -> list[Path]:
    """Extract paths of lock files mentioned in Git error messages."""
    paths: list[Path] = []
    if not stderr:
        return paths

    # First try the specific "unable to create '...lock': File exists" pattern
    for match in LOCK_ERROR_PATTERN.finditer(stderr):
        p = Path(match.group(1))
        if p not in paths:
            paths.append(p)

    # Fallback to generic quoted .lock paths
    if not paths:
        for match in GENERIC_LOCK_FILE_PATTERN.finditer(stderr):
            p = Path(match.group(1))
            if p not in paths:
                paths.append(p)

    return paths


def clean_stale_locks(
    repo_dir: Path,
    force: bool = False,
    max_age_seconds: float = 0.0,
) -> list[Path]:
    """Find and remove stale .lock files in the given Git repository.

    Parameters
    ----------
    repo_dir : Path
        Working tree or repository directory.
    force : bool
        If True, skips process checking and immediately deletes any matching lock files.
    max_age_seconds : float
        If greater than 0, only removes lock files modified at least max_age_seconds ago.

    Returns
    -------
    list[Path]
        List of deleted lock file paths.
    """
    git_dir = repo_dir / ".git"
    target_dirs: list[Path] = []
    if git_dir.is_dir():
        target_dirs.append(git_dir)
    elif (repo_dir / "HEAD").is_file():
        # Bare repository
        target_dirs.append(repo_dir)

    indexes_dir = repo_dir / ".seamus_indexes"
    if indexes_dir.is_dir():
        target_dirs.append(indexes_dir)

    if not target_dirs:
        return []

    # If not forcing, check if git is actively running in this repo
    if not force and is_git_process_running_in_repo(repo_dir):
        logger.debug("Active git process detected in %s; skipping lock cleanup", repo_dir)
        return []

    now = time.time()
    removed: list[Path] = []

    for target_dir in target_dirs:
        try:
            for lock_file in target_dir.glob("**/*.lock"):
                if not lock_file.is_file():
                    continue
                try:
                    if max_age_seconds > 0.0:
                        mtime = lock_file.stat().st_mtime
                        if (now - mtime) < max_age_seconds:
                            continue
                    lock_file.unlink(missing_ok=True)
                    logger.warning("Removed stale git lock file: %s", lock_file)
                    removed.append(lock_file)
                except OSError as exc:
                    logger.warning("Failed to remove stale lock file %s: %s", lock_file, exc)
        except Exception as exc:
            logger.warning("Error searching for lock files in %s: %s", target_dir, exc)

    return removed


def sweep_workspace_stale_locks(root_dir: Path) -> int:
    """Recursively search root_dir for all Git repositories and remove all stale lock files.

    Used at backend and manager initialization to clean up locks left by crashes or killed hosts.
    """
    if not root_dir.exists():
        return 0

    total_removed = 0
    try:
        for git_dir in root_dir.glob("**/.git"):
            if git_dir.is_dir():
                removed = clean_stale_locks(git_dir.parent, force=True)
                total_removed += len(removed)
    except Exception as exc:
        logger.warning("Error sweeping workspace for stale git locks in %s: %s", root_dir, exc)

    if total_removed > 0:
        logger.info("Swept and removed %d stale git lock files across %s", total_removed, root_dir)

    return total_removed

