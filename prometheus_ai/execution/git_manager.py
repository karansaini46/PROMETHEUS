"""Git worktree manager and repository inspection engine."""

import hashlib
import logging
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from prometheus_ai.execution.guards import (
    DEFAULT_MAX_FILE_READ_BYTES,
    DEFAULT_MAX_OUTPUT_BYTES,
    DEFAULT_MAX_RECURSION_DEPTH,
    DEFAULT_MAX_SEARCH_RESULTS,
    PatchValidationError,
    ResourceLimitExceededError,
    SecurityException,
    is_protected_file,
    sanitize_untrusted_output,
    validate_safe_path,
)

logger = logging.getLogger(__name__)

# Common non-text file extensions to skip during file listing and search
BINARY_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".ico",
        ".svg",
        ".pdf",
        ".zip",
        ".tar",
        ".gz",
        ".tgz",
        ".bz2",
        ".7z",
        ".exe",
        ".dll",
        ".so",
        ".dylib",
        ".bin",
        ".pyc",
        ".pyo",
        ".pyd",
        ".db",
        ".sqlite",
        ".sqlite3",
        ".parquet",
        ".arrow",
        ".wasm",
    }
)

IGNORE_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "dist",
        "build",
        ".egg-info",
    }
)


@dataclass
class RepositoryMetadata:
    """Registered repository metadata descriptor."""

    repo_id: str
    name: str
    root_path: str
    default_branch: str
    head_commit: str
    is_clean: bool
    remotes: dict[str, str] = field(default_factory=dict)


@dataclass
class WorktreeMetadata:
    """Isolated Git worktree descriptor."""

    worktree_id: str
    repo_path: str
    worktree_path: str
    branch_name: str
    base_commit: str


@dataclass
class GitStatusResult:
    """Status summary of modified, added, deleted, untracked files."""

    is_clean: bool
    modified: list[str]
    untracked: list[str]
    staged: list[str]
    deleted: list[str]
    raw_status: str


@dataclass
class GitDiffResult:
    """Git diff outcome."""

    diff: str
    truncated: bool
    files_changed: list[str]


@dataclass
class PatchResult:
    """Patch application outcome."""

    success: bool
    applied_files: list[str]
    error_message: str | None = None


class GitManager:
    """Manages local git repositories, worktree creation, and safe git operations."""

    def __init__(self, worktree_base_dir: str | Path | None = None) -> None:
        if worktree_base_dir:
            self.worktree_base_dir = Path(worktree_base_dir).resolve()
        else:
            self.worktree_base_dir = Path(tempfile.gettempdir()) / "prometheus_worktrees"
        self.worktree_base_dir.mkdir(parents=True, exist_ok=True)
        self._registered_repos: dict[str, RepositoryMetadata] = {}
        self._active_worktrees: dict[str, WorktreeMetadata] = {}

    def _run_git(
        self,
        args: list[str],
        cwd: Path | str,
        timeout: int = 30,
        env: dict[str, str] | None = None,
    ) -> tuple[int, str, str]:
        """Execute a git command securely without shell interpolation and with hooks disabled."""
        base_env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_ALLOW_PROTOCOL": "file:http:https",
        }
        if env:
            base_env.update(env)

        # Enforce disabling git hooks on every invocation
        cmd = ["git", "-c", "core.hooksPath=/dev/null", *args]

        try:
            res = subprocess.run(
                cmd,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=timeout,
                shell=False,  # strictly disallow shell
                env=base_env,
            )
            return res.returncode, res.stdout, res.stderr
        except subprocess.TimeoutExpired as err:
            raise ResourceLimitExceededError(
                f"Git operation timed out ({timeout}s): {args}"
            ) from err
        except Exception as err:
            raise SecurityException(f"Failed to execute git command {args}: {err}") from err

    def register_repository(
        self,
        repo_path: str | Path,
        name: str | None = None,
    ) -> RepositoryMetadata:
        """Register and validate a local git repository."""
        resolved = Path(repo_path).resolve()
        if not resolved.exists() or not resolved.is_dir():
            raise FileNotFoundError(f"Repository directory does not exist: {repo_path}")

        # Verify it's a valid git repository
        ret, out, err = self._run_git(["rev-parse", "--is-inside-work-tree"], cwd=resolved)
        if ret != 0 or out.strip() != "true":
            raise SecurityException(f"Path is not a valid git work tree: {repo_path} ({err})")

        # Disable hooks in repository config
        self._run_git(["config", "core.hooksPath", "/dev/null"], cwd=resolved)

        # Retrieve default branch
        ret, out, _ = self._run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=resolved)
        default_branch = out.strip() if ret == 0 else "main"

        # Retrieve HEAD commit
        ret, out, _ = self._run_git(["rev-parse", "HEAD"], cwd=resolved)
        head_commit = out.strip() if ret == 0 else "unknown"

        # Check clean status
        status = self.inspect_git_status(resolved)
        is_clean = status.is_clean

        # Retrieve remotes
        remotes: dict[str, str] = {}
        ret, out, _ = self._run_git(["remote", "-v"], cwd=resolved)
        if ret == 0:
            for line in out.splitlines():
                parts = line.split()
                if len(parts) >= 2 and parts[0] not in remotes:
                    remotes[parts[0]] = parts[1]

        repo_name = name or resolved.name
        repo_id = hashlib.sha256(str(resolved).encode("utf-8")).hexdigest()[:12]

        metadata = RepositoryMetadata(
            repo_id=repo_id,
            name=repo_name,
            root_path=str(resolved),
            default_branch=default_branch,
            head_commit=head_commit,
            is_clean=is_clean,
            remotes=remotes,
        )
        self._registered_repos[repo_id] = metadata
        return metadata

    def create_worktree(
        self,
        repo_path: str | Path,
        base_commit: str = "HEAD",
        branch_name: str | None = None,
    ) -> WorktreeMetadata:
        """Create an isolated Git worktree for safe experimentation and test runs."""
        resolved_repo = Path(repo_path).resolve()
        worktree_id = f"wt-{uuid.uuid4().hex[:10]}"
        worktree_dir = self.worktree_base_dir / worktree_id
        target_branch = branch_name or f"prometheus-agent/{worktree_id}"

        # Ensure base commit is valid
        ret, commit_hash, err = self._run_git(["rev-parse", base_commit], cwd=resolved_repo)
        if ret != 0:
            raise SecurityException(f"Invalid base commit ref '{base_commit}': {err.strip()}")
        commit_hash = commit_hash.strip()

        # Create the worktree
        ret, _out, err = self._run_git(
            ["worktree", "add", "-b", target_branch, str(worktree_dir), commit_hash],
            cwd=resolved_repo,
        )
        if ret != 0:
            raise SecurityException(f"Failed to create git worktree: {err.strip()}")

        # Ensure hooks are disabled in the worktree
        self._run_git(["config", "core.hooksPath", "/dev/null"], cwd=worktree_dir)

        metadata = WorktreeMetadata(
            worktree_id=worktree_id,
            repo_path=str(resolved_repo),
            worktree_path=str(worktree_dir),
            branch_name=target_branch,
            base_commit=commit_hash,
        )
        self._active_worktrees[worktree_id] = metadata
        return metadata

    def cleanup_worktree(self, worktree_path: str | Path, force: bool = True) -> bool:
        """Remove and prune an isolated worktree."""
        target = Path(worktree_path).resolve()
        # Find matching tracked worktree
        worktree_id = None
        repo_path = None
        for wid, meta in list(self._active_worktrees.items()):
            if Path(meta.worktree_path).resolve() == target:
                worktree_id = wid
                repo_path = Path(meta.repo_path)
                break

        removed_cleanly = True
        if repo_path and repo_path.exists():
            args = ["worktree", "remove"]
            if force:
                args.append("--force")
            args.append(str(target))
            ret, _, _ = self._run_git(args, cwd=repo_path)
            self._run_git(["worktree", "prune"], cwd=repo_path)
            if ret != 0:
                removed_cleanly = False

        # If directory still exists, remove it manually
        if target.exists():
            try:
                shutil.rmtree(target, ignore_errors=True)
            except Exception as err:
                logger.warning("Error deleting worktree directory %s: %s", target, err)
                removed_cleanly = False

        if worktree_id:
            self._active_worktrees.pop(worktree_id, None)

        return removed_cleanly

    def cleanup_all_worktrees(self) -> list[str]:
        """Tear down all tracked active and abandoned worktrees."""
        cleaned = []
        for wid, meta in list(self._active_worktrees.items()):
            self.cleanup_worktree(meta.worktree_path, force=True)
            cleaned.append(wid)
        return cleaned

    def inspect_git_status(self, repo_or_worktree_path: str | Path) -> GitStatusResult:
        """Inspect working tree status using porcelain format."""
        target = Path(repo_or_worktree_path).resolve()
        ret, out, err = self._run_git(["status", "--porcelain=v1"], cwd=target)
        if ret != 0:
            raise SecurityException(f"Failed to inspect git status: {err.strip()}")

        modified: list[str] = []
        untracked: list[str] = []
        staged: list[str] = []
        deleted: list[str] = []

        for line in out.splitlines():
            if not line:
                continue
            index_status = line[0]
            worktree_status = line[1]
            file_path = line[3:].strip()

            if index_status in ("M", "A", "R", "D", "C"):
                staged.append(file_path)
            if worktree_status == "M":
                modified.append(file_path)
            elif worktree_status == "D":
                deleted.append(file_path)
            elif index_status == "?" and worktree_status == "?":
                untracked.append(file_path)

        is_clean = (
            len(modified) == 0 and len(untracked) == 0 and len(staged) == 0 and len(deleted) == 0
        )

        return GitStatusResult(
            is_clean=is_clean,
            modified=modified,
            untracked=untracked,
            staged=staged,
            deleted=deleted,
            raw_status=out,
        )

    def inspect_git_diff(
        self,
        repo_or_worktree_path: str | Path,
        base_ref: str | None = None,
        cached: bool = False,
        max_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
    ) -> GitDiffResult:
        """Inspect unified diff with bounds protection."""
        target = Path(repo_or_worktree_path).resolve()
        args = ["diff", "--no-color"]
        if cached:
            args.append("--cached")
        if base_ref:
            args.append(base_ref)

        ret, out, err = self._run_git(args, cwd=target)
        if ret != 0:
            raise SecurityException(f"Failed to inspect git diff: {err.strip()}")

        sanitized_diff, truncated = sanitize_untrusted_output(out, max_bytes=max_bytes)

        # Extract list of changed files
        files_changed = []
        for line in out.splitlines():
            if line.startswith("diff --git a/"):
                parts = line.split()
                if len(parts) >= 4:
                    fname = parts[2][2:]  # strip 'a/'
                    files_changed.append(fname)

        return GitDiffResult(
            diff=sanitized_diff,
            truncated=truncated,
            files_changed=files_changed,
        )

    def apply_patch(
        self,
        worktree_path: str | Path,
        patch_content: str,
        check_only: bool = False,
    ) -> PatchResult:
        """Validate and apply a proposed unified diff patch to a worktree.

        Performs strict path security checks to prevent path traversal via diff headers.
        """
        target = Path(worktree_path).resolve()
        if not target.exists():
            raise FileNotFoundError(f"Worktree path does not exist: {worktree_path}")

        # 1. Parse and validate diff target paths
        applied_files: list[str] = []
        lines = patch_content.splitlines()

        for line in lines:
            target_file = None
            if line.startswith("+++ b/"):
                target_file = line[6:].strip()
            elif line.startswith("--- a/"):
                target_file = line[6:].strip()

            if target_file and target_file != "/dev/null":
                # Check for path traversal or absolute path injection
                if target_file.startswith("/") or target_file.startswith("\\"):
                    raise PatchValidationError(
                        f"Patch contains illegal absolute path: {target_file}"
                    )
                if ".." in Path(target_file).parts:
                    raise PatchValidationError(f"Patch contains directory traversal: {target_file}")
                # Verify it stays strictly within worktree
                validate_safe_path(
                    target, target_file, allow_nonexistent=True, check_protected=True
                )
                if target_file not in applied_files:
                    applied_files.append(target_file)

        # 2. Write patch to temporary file inside worktree_base_dir
        with tempfile.NamedTemporaryFile("w", suffix=".patch", delete=False) as pf:
            patch_file_path = pf.name
            pf.write(patch_content)

        try:
            # 3. Dry-run test patch
            ret, out, err = self._run_git(
                ["apply", "--check", "--verbose", patch_file_path],
                cwd=target,
            )
            if ret != 0:
                return PatchResult(
                    success=False,
                    applied_files=[],
                    error_message=f"Patch check failed: {err.strip() or out.strip()}",
                )

            if check_only:
                return PatchResult(
                    success=True,
                    applied_files=applied_files,
                )

            # 4. Apply patch cleanly
            ret, out, err = self._run_git(
                ["apply", "--whitespace=nowarn", patch_file_path],
                cwd=target,
            )
            if ret != 0:
                return PatchResult(
                    success=False,
                    applied_files=[],
                    error_message=f"Patch apply failed: {err.strip() or out.strip()}",
                )

            return PatchResult(
                success=True,
                applied_files=applied_files,
            )

        finally:
            if os.path.exists(patch_file_path):
                try:
                    os.unlink(patch_file_path)
                except Exception:
                    pass

    def list_permitted_files(
        self,
        repo_or_worktree_path: str | Path,
        subpath: str = "",
        max_files: int = 500,
        max_depth: int = DEFAULT_MAX_RECURSION_DEPTH,
    ) -> list[str]:
        """List permitted source files respecting security boundaries and filters."""
        base_root = Path(repo_or_worktree_path).resolve()
        target_dir = validate_safe_path(base_root, subpath, check_protected=True)

        permitted_files: list[str] = []
        start_depth = len(target_dir.parts)

        for root, dirs, files in os.walk(target_dir):
            current_path = Path(root)
            depth = len(current_path.parts) - start_depth

            if depth > max_depth:
                dirs.clear()  # Stop recursing deeper
                continue

            # In-place filter directories to avoid traversing into ignored / protected dirs
            dirs[:] = [
                d
                for d in dirs
                if d not in IGNORE_DIRS
                and not is_protected_file(current_path / d)
                and not (current_path / d).is_symlink()
            ]

            for file_name in sorted(files):
                if len(permitted_files) >= max_files:
                    return permitted_files

                file_path = current_path / file_name

                # Skip symlinks that escape boundary
                if file_path.is_symlink():
                    try:
                        real = Path(os.path.realpath(file_path))
                        if not real.is_relative_to(base_root):
                            continue
                    except Exception:
                        continue

                # Skip protected or sensitive files
                rel_to_base = file_path.relative_to(base_root)
                if is_protected_file(rel_to_base):
                    continue

                # Skip binaries
                if file_path.suffix.lower() in BINARY_EXTENSIONS:
                    continue

                permitted_files.append(rel_to_base.as_posix())

        return permitted_files

    def read_bounded_file(
        self,
        repo_or_worktree_path: str | Path,
        file_path: str,
        start_line: int = 1,
        end_line: int | None = None,
        max_bytes: int = DEFAULT_MAX_FILE_READ_BYTES,
    ) -> dict[str, Any]:
        """Read file contents safely bounded by byte and line limits."""
        base_root = Path(repo_or_worktree_path).resolve()
        resolved_file = validate_safe_path(base_root, file_path, check_protected=True)

        if not resolved_file.is_file():
            raise FileNotFoundError(f"Target is not a regular file: {file_path}")

        file_size = resolved_file.stat().st_size
        truncated = False

        # Read content bounded by max_bytes
        with open(resolved_file, "rb") as f:
            raw_bytes = f.read(max_bytes + 1)

        if len(raw_bytes) > max_bytes:
            raw_bytes = raw_bytes[:max_bytes]
            truncated = True

        try:
            content_text = raw_bytes.decode("utf-8", errors="replace")
        except Exception as err:
            raise SecurityException(f"Unable to decode file content as text: {err}") from err

        all_lines = content_text.splitlines()
        total_lines = len(all_lines)

        s_line = max(1, start_line)
        e_line = total_lines if end_line is None else min(total_lines, end_line)

        selected_lines = all_lines[s_line - 1 : e_line]
        bounded_content = "\n".join(selected_lines)

        return {
            "content": bounded_content,
            "start_line": s_line,
            "end_line": e_line,
            "total_lines": total_lines,
            "truncated": truncated,
            "file_size_bytes": file_size,
        }

    def search_source_code(
        self,
        repo_or_worktree_path: str | Path,
        query: str,
        is_regex: bool = False,
        max_results: int = DEFAULT_MAX_SEARCH_RESULTS,
        file_pattern: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search code safely across permitted repository files."""
        if not query:
            return []

        base_root = Path(repo_or_worktree_path).resolve()
        permitted_files = self.list_permitted_files(base_root, max_files=1000)

        results: list[dict[str, Any]] = []

        if is_regex:
            try:
                pattern = re.compile(query, re.IGNORECASE)
            except re.error as err:
                raise SecurityException(f"Invalid search regex pattern: {err}") from err
        else:
            lower_query = query.lower()

        for rel_str in permitted_files:
            if file_pattern and not re.search(file_pattern, rel_str):
                continue

            full_path = base_root / rel_str
            try:
                with open(full_path, encoding="utf-8", errors="ignore") as f:
                    for line_no, line in enumerate(f, start=1):
                        matched = False
                        if is_regex:
                            if pattern.search(line):
                                matched = True
                        else:
                            if lower_query in line.lower():
                                matched = True

                        if matched:
                            results.append(
                                {
                                    "file": rel_str,
                                    "line_number": line_no,
                                    "line_content": line.rstrip()[:200],  # Bounded line width
                                }
                            )
                            if len(results) >= max_results:
                                return results
            except Exception:
                continue

        return results
