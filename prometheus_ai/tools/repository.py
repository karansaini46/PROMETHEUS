"""Repository and Git Inspection Tools for Agent Tool-Calling."""

from typing import Any

from prometheus_ai.execution.git_manager import GitManager
from prometheus_ai.tools.base import BaseTool, ToolDefinition


class RegisterRepositoryTool(BaseTool):
    """Register and validate a local repository."""

    def __init__(self, git_manager: GitManager | None = None) -> None:
        self.git_manager = git_manager or GitManager()

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="register_repository",
            description="Register a local Git repository, verifying worktree boundaries and disabling hooks.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Local path to Git repository."},
                    "name": {
                        "type": "string",
                        "description": "Optional human-readable repository name.",
                    },
                },
                "required": ["path"],
            },
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        path = str(kwargs.get("path", ""))
        name = kwargs.get("name")
        meta = self.git_manager.register_repository(path, name=name)
        return {
            "repo_id": meta.repo_id,
            "name": meta.name,
            "root_path": meta.root_path,
            "default_branch": meta.default_branch,
            "head_commit": meta.head_commit,
            "is_clean": meta.is_clean,
            "remotes": meta.remotes,
        }


class ListPermittedFilesTool(BaseTool):
    """List permitted source files in a repository or worktree."""

    def __init__(self, git_manager: GitManager | None = None) -> None:
        self.git_manager = git_manager or GitManager()

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="list_permitted_files",
            description="List permitted source files in repository or worktree, filtering out protected secrets and binaries.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Path to repository or worktree.",
                    },
                    "subpath": {
                        "type": "string",
                        "description": "Optional subdirectory to list within root.",
                        "default": "",
                    },
                    "max_files": {
                        "type": "integer",
                        "description": "Maximum number of files to return.",
                        "default": 500,
                    },
                },
                "required": ["repo_path"],
            },
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        repo_path = str(kwargs.get("repo_path", ""))
        subpath = str(kwargs.get("subpath", ""))
        max_files = int(kwargs.get("max_files", 500))
        files = self.git_manager.list_permitted_files(
            repo_path, subpath=subpath, max_files=max_files
        )
        return {
            "files": files,
            "count": len(files),
            "truncated": len(files) >= max_files,
        }


class ReadBoundedFileTool(BaseTool):
    """Read bounded file contents from repository or worktree."""

    def __init__(self, git_manager: GitManager | None = None) -> None:
        self.git_manager = git_manager or GitManager()

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="read_bounded_file",
            description="Read file contents bounded by line range and byte limits with strict traversal protection.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Path to repository or worktree root.",
                    },
                    "file_path": {"type": "string", "description": "Relative path to target file."},
                    "start_line": {
                        "type": "integer",
                        "description": "Starting line (1-indexed).",
                        "default": 1,
                    },
                    "end_line": {"type": "integer", "description": "Ending line (inclusive)."},
                    "max_bytes": {
                        "type": "integer",
                        "description": "Maximum bytes to read.",
                        "default": 100000,
                    },
                },
                "required": ["repo_path", "file_path"],
            },
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        repo_path = str(kwargs.get("repo_path", ""))
        file_path = str(kwargs.get("file_path", ""))
        start_line = int(kwargs.get("start_line", 1))
        end_line_val = kwargs.get("end_line")
        end_line = int(end_line_val) if end_line_val is not None else None
        max_bytes = int(kwargs.get("max_bytes", 100000))
        return self.git_manager.read_bounded_file(
            repo_or_worktree_path=repo_path,
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            max_bytes=max_bytes,
        )


class SearchSourceCodeTool(BaseTool):
    """Search source code across permitted files."""

    def __init__(self, git_manager: GitManager | None = None) -> None:
        self.git_manager = git_manager or GitManager()

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="search_source_code",
            description="Search source code content within permitted repository files using literal or regex matching.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Path to repository or worktree root.",
                    },
                    "query": {"type": "string", "description": "Search term or regex pattern."},
                    "is_regex": {
                        "type": "boolean",
                        "description": "Whether query is a regex pattern.",
                        "default": False,
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results to return.",
                        "default": 100,
                    },
                    "file_pattern": {
                        "type": "string",
                        "description": "Optional regex pattern to filter filenames.",
                    },
                },
                "required": ["repo_path", "query"],
            },
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        repo_path = str(kwargs.get("repo_path", ""))
        query = str(kwargs.get("query", ""))
        is_regex = bool(kwargs.get("is_regex", False))
        max_results = int(kwargs.get("max_results", 100))
        file_pattern = kwargs.get("file_pattern")
        matches = self.git_manager.search_source_code(
            repo_or_worktree_path=repo_path,
            query=query,
            is_regex=is_regex,
            max_results=max_results,
            file_pattern=file_pattern,
        )
        return {
            "query": query,
            "results": matches,
            "count": len(matches),
        }


class InspectGitStatusTool(BaseTool):
    """Inspect Git status of repository or worktree."""

    def __init__(self, git_manager: GitManager | None = None) -> None:
        self.git_manager = git_manager or GitManager()

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="inspect_git_status",
            description="Inspect git working tree status, listing modified, untracked, and staged files.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Path to repository or worktree.",
                    },
                },
                "required": ["repo_path"],
            },
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        repo_path = str(kwargs.get("repo_path", ""))
        status = self.git_manager.inspect_git_status(repo_path)
        return {
            "is_clean": status.is_clean,
            "modified": status.modified,
            "untracked": status.untracked,
            "staged": status.staged,
            "deleted": status.deleted,
            "raw_status": status.raw_status,
        }


class InspectGitDiffTool(BaseTool):
    """Inspect Git diff bounded by size limits."""

    def __init__(self, git_manager: GitManager | None = None) -> None:
        self.git_manager = git_manager or GitManager()

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="inspect_git_diff",
            description="Inspect unified diff of repository or worktree with byte bounding.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Path to repository or worktree.",
                    },
                    "base_ref": {
                        "type": "string",
                        "description": "Optional base reference commit or branch.",
                    },
                    "cached": {
                        "type": "boolean",
                        "description": "Whether to inspect staged/cached diff.",
                        "default": False,
                    },
                    "max_bytes": {
                        "type": "integer",
                        "description": "Maximum diff size in bytes.",
                        "default": 100000,
                    },
                },
                "required": ["repo_path"],
            },
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        repo_path = str(kwargs.get("repo_path", ""))
        base_ref = kwargs.get("base_ref")
        cached = bool(kwargs.get("cached", False))
        max_bytes = int(kwargs.get("max_bytes", 100000))
        diff_res = self.git_manager.inspect_git_diff(
            repo_or_worktree_path=repo_path,
            base_ref=base_ref,
            cached=cached,
            max_bytes=max_bytes,
        )
        return {
            "diff": diff_res.diff,
            "truncated": diff_res.truncated,
            "files_changed": diff_res.files_changed,
        }


class CreateWorktreeTool(BaseTool):
    """Create an isolated Git worktree."""

    def __init__(self, git_manager: GitManager | None = None) -> None:
        self.git_manager = git_manager or GitManager()

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="create_isolated_worktree",
            description="Create an isolated Git worktree for agent code modification and verification.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Path to source Git repository.",
                    },
                    "base_commit": {
                        "type": "string",
                        "description": "Base commit or branch to branch from.",
                        "default": "HEAD",
                    },
                    "branch_name": {
                        "type": "string",
                        "description": "Optional target branch name.",
                    },
                },
                "required": ["repo_path"],
            },
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        repo_path = str(kwargs.get("repo_path", ""))
        base_commit = str(kwargs.get("base_commit", "HEAD"))
        branch_name = kwargs.get("branch_name")
        meta = self.git_manager.create_worktree(
            repo_path=repo_path,
            base_commit=base_commit,
            branch_name=branch_name,
        )
        return {
            "worktree_id": meta.worktree_id,
            "repo_path": meta.repo_path,
            "worktree_path": meta.worktree_path,
            "branch_name": meta.branch_name,
            "base_commit": meta.base_commit,
        }


class ApplyPatchTool(BaseTool):
    """Apply a proposed patch to an isolated worktree."""

    def __init__(self, git_manager: GitManager | None = None) -> None:
        self.git_manager = git_manager or GitManager()

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="apply_patch",
            description="Validate and apply a unified diff patch to a worktree with path traversal verification.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "worktree_path": {
                        "type": "string",
                        "description": "Path to the isolated Git worktree.",
                    },
                    "patch_content": {
                        "type": "string",
                        "description": "Unified diff patch content.",
                    },
                    "check_only": {
                        "type": "boolean",
                        "description": "If true, tests patch without applying.",
                        "default": False,
                    },
                },
                "required": ["worktree_path", "patch_content"],
            },
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        worktree_path = str(kwargs.get("worktree_path", ""))
        patch_content = str(kwargs.get("patch_content", ""))
        check_only = bool(kwargs.get("check_only", False))
        res = self.git_manager.apply_patch(
            worktree_path=worktree_path,
            patch_content=patch_content,
            check_only=check_only,
        )
        return {
            "success": res.success,
            "applied_files": res.applied_files,
            "error_message": res.error_message,
        }
