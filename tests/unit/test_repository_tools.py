"""Unit tests for agent repository and execution tools."""

import os
import subprocess
import tempfile
from pathlib import Path

import pytest

from prometheus_ai.execution.git_manager import GitManager
from prometheus_ai.execution.process_runner import ProcessSandboxRunner
from prometheus_ai.tools.execution import (
    CancelExecutionTool,
    ExecutionRegistry,
    RunAllowlistedTestsTool,
)
from prometheus_ai.tools.repository import (
    ApplyPatchTool,
    CreateWorktreeTool,
    InspectGitDiffTool,
    InspectGitStatusTool,
    ListPermittedFilesTool,
    ReadBoundedFileTool,
    RegisterRepositoryTool,
    SearchSourceCodeTool,
)


def _init_test_git_repo(path: Path) -> None:
    """Helper to initialize a real git repository."""
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "GIT_AUTHOR_NAME": "Tool Tester",
        "GIT_AUTHOR_EMAIL": "tooltester@example.com",
        "GIT_COMMITTER_NAME": "Tool Tester",
        "GIT_COMMITTER_EMAIL": "tooltester@example.com",
    }
    subprocess.run(
        ["git", "init", "-b", "main"], cwd=path, check=True, capture_output=True, env=env
    )
    (path / "README.md").write_text("# Test Repo\nDocumentation content")
    (path / "calculator.py").write_text("def multiply(x, y):\n    return x * y\n")
    (path / "test_calc.py").write_text("def test_multiply():\n    assert 2 * 3 == 6\n")
    subprocess.run(["git", "add", "."], cwd=path, check=True, capture_output=True, env=env)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=path,
        check=True,
        capture_output=True,
        env=env,
    )


@pytest.mark.unit
async def test_repository_tools_lifecycle() -> None:
    """Test full cycle of repository tools: register, list, read, search, status, diff, worktree, patch."""
    with tempfile.TemporaryDirectory() as temp_dir:
        base_dir = Path(temp_dir)
        repo_dir = base_dir / "my_project"
        repo_dir.mkdir()
        _init_test_git_repo(repo_dir)

        git_mgr = GitManager(worktree_base_dir=base_dir / "wts")

        # 1. RegisterRepositoryTool
        reg_tool = RegisterRepositoryTool(git_manager=git_mgr)
        assert reg_tool.definition.name == "register_repository"
        reg_res = await reg_tool.execute(path=str(repo_dir), name="my-project")
        assert reg_res["name"] == "my-project"
        assert reg_res["default_branch"] == "main"
        assert reg_res["is_clean"] is True

        # 2. ListPermittedFilesTool
        list_tool = ListPermittedFilesTool(git_manager=git_mgr)
        assert list_tool.definition.name == "list_permitted_files"
        list_res = await list_tool.execute(repo_path=str(repo_dir))
        assert "calculator.py" in list_res["files"]
        assert "README.md" in list_res["files"]

        # 3. ReadBoundedFileTool
        read_tool = ReadBoundedFileTool(git_manager=git_mgr)
        assert read_tool.definition.name == "read_bounded_file"
        read_res = await read_tool.execute(
            repo_path=str(repo_dir), file_path="calculator.py", start_line=1, end_line=2
        )
        assert "def multiply" in read_res["content"]
        assert read_res["start_line"] == 1
        assert read_res["end_line"] == 2

        # 4. SearchSourceCodeTool
        search_tool = SearchSourceCodeTool(git_manager=git_mgr)
        assert search_tool.definition.name == "search_source_code"
        search_res = await search_tool.execute(repo_path=str(repo_dir), query="multiply")
        assert search_res["count"] >= 1
        assert any(r["file"] == "calculator.py" for r in search_res["results"])

        # 5. CreateWorktreeTool
        wt_tool = CreateWorktreeTool(git_manager=git_mgr)
        assert wt_tool.definition.name == "create_isolated_worktree"
        wt_res = await wt_tool.execute(repo_path=str(repo_dir), branch_name="test-fix")
        wt_path = wt_res["worktree_path"]
        assert Path(wt_path).exists()

        # 6. ApplyPatchTool
        patch_tool = ApplyPatchTool(git_manager=git_mgr)
        assert patch_tool.definition.name == "apply_patch"
        patch = """diff --git a/calculator.py b/calculator.py
--- a/calculator.py
+++ b/calculator.py
@@ -1,2 +1,2 @@
 def multiply(x, y):
-    return x * y
+    return x * y + 0
"""
        patch_res = await patch_tool.execute(worktree_path=wt_path, patch_content=patch)
        assert patch_res["success"] is True
        assert "calculator.py" in patch_res["applied_files"]

        # 7. InspectGitStatusTool
        status_tool = InspectGitStatusTool(git_manager=git_mgr)
        assert status_tool.definition.name == "inspect_git_status"
        status_res = await status_tool.execute(repo_path=wt_path)
        assert status_res["is_clean"] is False
        assert "calculator.py" in status_res["modified"]

        # 8. InspectGitDiffTool
        diff_tool = InspectGitDiffTool(git_manager=git_mgr)
        assert diff_tool.definition.name == "inspect_git_diff"
        diff_res = await diff_tool.execute(repo_path=wt_path)
        assert "+    return x * y + 0" in diff_res["diff"]

        # Cleanup
        git_mgr.cleanup_worktree(wt_path)


@pytest.mark.unit
async def test_execution_tools() -> None:
    """Test RunAllowlistedTestsTool and CancelExecutionTool."""
    runner = ProcessSandboxRunner()
    registry = ExecutionRegistry()
    run_tool = RunAllowlistedTestsTool(runner=runner, registry=registry)
    cancel_tool = CancelExecutionTool(registry=registry)

    assert run_tool.definition.name == "run_allowlisted_tests"
    assert cancel_tool.definition.name == "cancel_execution"

    with tempfile.TemporaryDirectory() as temp_dir:
        # Run a test command using python module runner
        res = await run_tool.execute(
            worktree_path=temp_dir,
            test_runner="python -m unittest",
            extra_args=["--help"],
            timeout_seconds=10,
        )
        assert res["exit_code"] == 0
        assert "unittest" in res["stdout"].lower() or "usage" in res["stdout"].lower()
        assert res["backend"] == "process"

        # Test cancel execution tool
        cancel_res = await cancel_tool.execute(execution_id="non-existent-id")
        assert cancel_res["cancelled"] is False
