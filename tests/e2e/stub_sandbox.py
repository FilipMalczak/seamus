"""In-process stub of the OpenSandbox backend used by end-to-end tests.

The stub keeps the observable contract of :class:`seamus.harness.sandbox.SeamusOpenSandboxBackend`
while running entirely on the host filesystem:

* ``/workspace`` maps to the session's ``data/`` directory.
* ``/artifacts`` maps to the session's ``artifacts/`` directory and is read-only.
* ``/projects/<name>`` maps to the mounted external repository working copies.
* every other absolute path maps to a transient directory outside the workspace.

Shell execution is performed with the host shell in the mapped working directory.
This is *not* a security boundary; it exists so that end-to-end tests can observe
file writes, exit codes and mount policies without a live container.

Known simplifications (documented so tests do not over-claim):

* ``execute`` is refused wholesale while the workspace is mounted read-only,
  instead of allowing read-only commands and rejecting only the writes.
* ``upload_files``/``download_files`` copy bytes directly instead of streaming
  through the OpenSandbox API.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from deepagents.backends.protocol import (
    DeleteResult,
    EditResult,
    ExecuteResponse,
    FileDownloadResponse,
    FileInfo,
    FileUploadResponse,
    GlobResult,
    GrepMatch,
    GrepResult,
    LsResult,
    ReadResult,
    WriteResult,
)

TRANSIENT_DIR = "transient"


@dataclass
class StubSandboxSettings:
    """Minimal settings surface used by the runner and the terminal route."""

    workdir: str = "/workspace"
    timeout: int = 300
    sandbox_timeout: int = 3600
    image: str = "seamus-sandbox:stub"
    workspace_volume: str | None = None


@dataclass
class StubSandboxBackend:
    """Host-filesystem stand-in for the OpenSandbox backend."""

    agent_id: Any = None
    session_id: Any = None
    data_dir: Path = field(default_factory=Path)
    artifacts_dir: Path | None = None
    notes_dir: Path | None = None
    workspace_root: Path | None = None
    workspace_readonly: bool = False
    notes_mounted: bool = False
    notes_readonly: bool = True
    settings: StubSandboxSettings = field(default_factory=StubSandboxSettings)
    skill_directories: list[str] = field(default_factory=list)
    repositories: list[Any] = field(default_factory=list)
    sandbox: Any = None
    transient_dir: Path | None = None
    executed_commands: list[str] = field(default_factory=list)
    destroyed: bool = False

    def __post_init__(self) -> None:
        self.data_dir = Path(self.data_dir)
        self.artifacts_dir = Path(self.artifacts_dir) if self.artifacts_dir else None
        if self.transient_dir is None:
            self.transient_dir = self.data_dir.parent / TRANSIENT_DIR
        Path(self.transient_dir).mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @property
    def id(self) -> str:
        """Return a stable identifier for the stub sandbox."""
        return f"stub:{self.agent_id}:{self.session_id}"

    def destroy(self) -> None:
        """Mark the sandbox as destroyed (mirrors container teardown)."""
        self.destroyed = True

    def close(self) -> None:
        """No-op close hook mirroring the real backend."""

    def reconfigure_mounts(
        self,
        *,
        workspace_readonly: bool,
        notes_mounted: bool = False,
        notes_readonly: bool = True,
        repositories: list[Any] | None = None,
    ) -> None:
        """Update mount flags, mirroring the real backend's reconfiguration."""
        self.workspace_readonly = workspace_readonly
        self.notes_mounted = notes_mounted
        self.notes_readonly = notes_readonly
        if repositories is not None:
            self.repositories = list(repositories)

    def get_skill_sources(self, artifacts_implementation: Any = None) -> list[tuple[str, str]]:
        """Return skill sources ordered from lowest to highest priority."""
        sources: list[tuple[str, str]] = []
        for idx, _skill_dir in enumerate(self.skill_directories):
            sources.append((f"/skills/system/{idx}", f"System #{idx}"))
        if self.repositories:
            for repo in reversed(self.repositories):
                sources.append((f"/projects/{repo.id}/.skills", f"Project {repo.id} (.skills)"))
                sources.append((f"/projects/{repo.id}/skills", f"Project {repo.id}"))
        sources.append(("/workspace/.skills", "Session (.skills)"))
        sources.append(("/workspace/skills", "Session"))
        return sources

    # ------------------------------------------------------------------
    # Path mapping
    # ------------------------------------------------------------------

    def _projects_dir(self) -> Path:
        root = Path(self.workspace_root) if self.workspace_root else self.data_dir.parent
        return root / str(self.agent_id) / str(self.session_id) / "projects"

    def _resolve(self, virtual_path: str) -> Path:
        """Map an in-sandbox absolute path onto a host path."""
        path = virtual_path if virtual_path.startswith("/") else f"/{virtual_path}"
        if path == "/workspace" or path.startswith("/workspace/"):
            remainder = path[len("/workspace") :].lstrip("/")
            return self.data_dir / remainder if remainder else self.data_dir
        if path == "/artifacts" or path.startswith("/artifacts/"):
            if self.artifacts_dir is None:
                raise ValueError("artifacts are not mounted")
            remainder = path[len("/artifacts") :].lstrip("/")
            return self.artifacts_dir / remainder if remainder else self.artifacts_dir
        if path.startswith("/projects/"):
            remainder = path[len("/projects/") :]
            name, _, tail = remainder.partition("/")
            base = self._projects_dir() / name
            return base / tail if tail else base
        remainder = path.lstrip("/")
        base = Path(self.transient_dir) if self.transient_dir else self.data_dir
        return base / remainder if remainder else base

    def _virtual(self, host_path: Path) -> str:
        """Map a host path back onto its in-sandbox virtual path."""
        resolved = Path(host_path).resolve()
        for base, prefix in (
            (self.data_dir, "/workspace"),
            (self.artifacts_dir, "/artifacts"),
        ):
            if base is None:
                continue
            base = Path(base).resolve()
            if resolved == base:
                return prefix
            try:
                rel = resolved.relative_to(base)
            except ValueError:
                continue
            return f"{prefix}/{rel.as_posix()}"
        return str(resolved)

    def _is_workspace(self, host_path: Path) -> bool:
        try:
            Path(host_path).resolve().relative_to(self.data_dir.resolve())
        except ValueError:
            return False
        return True

    def _guard_write(self, host_path: Path) -> str | None:
        """Return an error message when the target path must not be written."""
        if self.workspace_readonly and self._is_workspace(host_path):
            return "Error: /workspace is mounted read-only in this phase."
        if self.artifacts_dir is not None:
            try:
                Path(host_path).resolve().relative_to(self.artifacts_dir.resolve())
            except ValueError:
                return None
            return "Error: /artifacts is mounted read-only."
        return None

    # ------------------------------------------------------------------
    # Filesystem protocol
    # ------------------------------------------------------------------

    def ls(self, path: str) -> LsResult:
        """List the direct children of a directory."""
        try:
            target = self._resolve(path)
        except ValueError as exc:
            return LsResult(error=str(exc))
        if not target.exists():
            return LsResult(error=f"Path '{path}': path_not_found")
        if not target.is_dir():
            return LsResult(error=f"Path '{path}': not_a_directory")
        entries: list[FileInfo] = []
        for child in sorted(target.iterdir(), key=lambda p: p.name):
            if child.name.startswith(".git"):
                continue
            is_dir = child.is_dir()
            entries.append(
                {
                    "path": self._virtual(child) + ("/" if is_dir else ""),
                    "is_dir": is_dir,
                    "size": 0 if is_dir else child.stat().st_size,
                }
            )
        return LsResult(entries=entries)

    async def als(self, path: str) -> LsResult:
        """Async variant of :meth:`ls`."""
        return self.ls(path)

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> ReadResult:
        """Read a text file, honouring line pagination."""
        try:
            target = self._resolve(file_path)
        except ValueError as exc:
            return ReadResult(error=str(exc))
        if not target.exists():
            return ReadResult(error=f"Path '{file_path}': path_not_found")
        try:
            content = target.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return ReadResult(error=f"Path '{file_path}': not a UTF-8 text file")
        lines = content.splitlines()
        total = len(lines)
        start = max(offset, 0)
        window = lines[start : start + limit] if limit > 0 else []
        body = "\n".join(window)
        return ReadResult(
            file_data={
                "content": body,
                "encoding": "utf-8",
                "created_at": "",
                "modified_at": "",
            },
            total_lines=total,
            start_line=start + 1 if window else None,
            end_line=start + len(window) if window else None,
            next_offset=start + len(window) if start + len(window) < total else None,
        )

    async def aread(self, file_path: str, offset: int = 0, limit: int = 2000) -> ReadResult:
        """Async variant of :meth:`read`."""
        return self.read(file_path, offset=offset, limit=limit)

    def write(self, file_path: str, content: str) -> WriteResult:
        """Write text content, honouring read-only mounts."""
        try:
            target = self._resolve(file_path)
        except ValueError as exc:
            return WriteResult(error=str(exc))
        error = self._guard_write(target)
        if error is not None:
            return WriteResult(error=error)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return WriteResult(path=file_path)

    async def awrite(self, file_path: str, content: str) -> WriteResult:
        """Async variant of :meth:`write`."""
        return self.write(file_path, content)

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        """Replace a substring inside a file."""
        try:
            target = self._resolve(file_path)
        except ValueError as exc:
            return EditResult(error=str(exc))
        if not target.exists():
            return EditResult(error=f"Path '{file_path}': path_not_found")
        error = self._guard_write(target)
        if error is not None:
            return EditResult(error=error)
        content = target.read_text(encoding="utf-8")
        occurrences = content.count(old_string)
        if occurrences == 0:
            return EditResult(error="String to replace not found in file.")
        updated = (
            content.replace(old_string, new_string)
            if replace_all
            else content.replace(old_string, new_string, 1)
        )
        target.write_text(updated, encoding="utf-8")
        return EditResult(path=file_path, occurrences=occurrences)

    async def aedit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        """Async variant of :meth:`edit`."""
        return self.edit(file_path, old_string, new_string, replace_all)

    def delete(self, file_path: str) -> DeleteResult:
        """Delete a file or directory."""
        try:
            target = self._resolve(file_path)
        except ValueError as exc:
            return DeleteResult(error=str(exc))
        if not target.exists():
            return DeleteResult(error=f"Path '{file_path}': path_not_found")
        error = self._guard_write(target)
        if error is not None:
            return DeleteResult(error=error)
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
        return DeleteResult(path=file_path)

    async def adelete(self, file_path: str) -> DeleteResult:
        """Async variant of :meth:`delete`."""
        return self.delete(file_path)

    def glob(self, pattern: str, path: str | None = None) -> GlobResult:
        """Find files matching a glob pattern under the given root."""
        root = self._resolve(path or "/workspace")
        if not root.is_dir():
            return GlobResult(error=f"Path '{path or '/workspace'}': path_not_found")
        matches: list[FileInfo] = []
        for candidate in sorted(root.rglob("*")):
            if not candidate.is_file():
                continue
            if candidate.match(pattern) or candidate.name == pattern:
                matches.append({"path": self._virtual(candidate), "is_dir": False})
        return GlobResult(matches=matches)

    async def aglob(self, pattern: str, path: str | None = None) -> GlobResult:
        """Async variant of :meth:`glob`."""
        return self.glob(pattern, path)

    def grep(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
        *,
        max_count: int | None = None,
        context_lines: int = 0,
    ) -> GrepResult:
        """Search files for a literal substring."""
        root = self._resolve(path or "/workspace")
        if not root.is_dir():
            return GrepResult(error=f"Path '{path or '/workspace'}': path_not_found")
        matches: list[GrepMatch] = []
        for candidate in sorted(root.rglob("*")):
            if not candidate.is_file():
                continue
            if glob and not candidate.match(glob):
                continue
            try:
                content = candidate.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for line_no, line in enumerate(content.splitlines(), 1):
                if pattern in line:
                    matches.append(
                        {"path": self._virtual(candidate), "line": line_no, "text": line}
                    )
                    if max_count is not None and len(matches) >= max_count:
                        return GrepResult(matches=matches)
        return GrepResult(matches=matches)

    async def agrep(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
        *,
        max_count: int | None = None,
        context_lines: int = 0,
    ) -> GrepResult:
        """Async variant of :meth:`grep`."""
        return self.grep(
            pattern,
            path,
            glob,
            max_count=max_count,
            context_lines=context_lines,
        )

    # ------------------------------------------------------------------
    # Sandbox protocol
    # ------------------------------------------------------------------

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        """Execute a shell command with the host shell."""
        self.executed_commands.append(command)
        if self.workspace_readonly:
            return ExecuteResponse(
                output="Error: /workspace is mounted read-only in this phase.",
                exit_code=1,
            )
        translated = self._translate_command(command)
        cwd = self._resolve("/workspace")
        completed = subprocess.run(  # noqa: S602 - test-only stub executing scripted commands
            translated,
            shell=True,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        output = completed.stdout + completed.stderr
        return ExecuteResponse(output=output, exit_code=completed.returncode)

    async def aexecute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        """Async variant of :meth:`execute`."""
        return self.execute(command, timeout=timeout)

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        """Store file contents directly on the host filesystem."""
        responses: list[FileUploadResponse] = []
        for path, content in files:
            try:
                target = self._resolve(path)
            except ValueError as exc:
                responses.append(FileUploadResponse(path=path, error=str(exc)))
                continue
            error = self._guard_write(target)
            if error is not None:
                responses.append(FileUploadResponse(path=path, error=error))
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            responses.append(FileUploadResponse(path=path))
        return responses

    async def aupload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        """Async variant of :meth:`upload_files`."""
        return self.upload_files(files)

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        """Read file contents directly from the host filesystem."""
        responses: list[FileDownloadResponse] = []
        for path in paths:
            try:
                target = self._resolve(path)
            except ValueError as exc:
                responses.append(FileDownloadResponse(path=path, error=str(exc)))
                continue
            if not target.exists():
                responses.append(FileDownloadResponse(path=path, error="path_not_found"))
                continue
            responses.append(FileDownloadResponse(path=path, content=target.read_bytes()))
        return responses

    async def adownload_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        """Async variant of :meth:`download_files`."""
        return self.download_files(paths)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _translate_command(self, command: str) -> str:
        """Rewrite in-sandbox absolute paths into host paths."""
        replacements = [
            ("/workspace", str(self.data_dir.resolve())),
        ]
        if self.artifacts_dir is not None:
            replacements.append(("/artifacts", str(self.artifacts_dir.resolve())))
        translated = command
        for virtual, host in replacements:
            translated = translated.replace(virtual, host)
        return translated
