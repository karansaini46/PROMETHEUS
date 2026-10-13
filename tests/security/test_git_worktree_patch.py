"""Security tests for Git worktree management and patch validation."""

import os
import subprocess
import tempfile
from pathlib import Path

import pytest

from prometheus_ai.execution.git_manager import GitManager
from prometheus_ai.execution.guards import (
    PatchValidationError,
    ProtectedPathError,
)


def _init_test_git_repo(path: Path) -> None:
    """Helper to initialize a real git repository with an initial commit."""
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "GIT_AUTHOR_NAME": "Test Author",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "Test Committer",
        "GIT_COMMITTER_EMAIL": "test@example.com",
    }
    subprocess.run(
        ["git", "init", "-b", "main"], cwd=path, check=True, capture_output=True, env=env
    )
    (path / "README.md").write_text("# Test Repo\nHello world")
    (path / "src").mkdir()
    (path / "src" / "app.py").write_text("def add(a, b):\n    return a + b\n")
    subprocess.run(["git", "add", "."], cwd=path, check=True, capture_output=True, env=env)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=path,
        check=True,
        capture_output=True,
        env=env,
    )


@pytest.mark.security
def test_register_repository_disables_hooks() -> None:
    """Ensure repository registration configures hooksPath to /dev/null."""
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_dir = Path(temp_dir) / "test_repo"
        repo_dir.mkdir()
        _init_test_git_repo(repo_dir)

        mgr = GitManager()
        meta = mgr.register_repository(repo_dir, name="my-repo")

        assert meta.name == "my-repo"
        assert meta.default_branch == "main"
        assert meta.is_clean is True
        assert len(meta.head_commit) == 40

        # Check git config for core.hooksPath
        res = subprocess.run(
            ["git", "config", "core.hooksPath"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            check=True,
        )
        assert res.stdout.strip() == "/dev/null"


@pytest.mark.security
def test_create_worktree_isolation() -> None:
    """Ensure worktrees are created in isolated directories with detached branches."""
    with tempfile.TemporaryDirectory() as temp_dir:
        base_dir = Path(temp_dir)
        repo_dir = base_dir / "test_repo"
        repo_dir.mkdir()
        _init_test_git_repo(repo_dir)

        worktree_base = base_dir / "worktrees"
        mgr = GitManager(worktree_base_dir=worktree_base)

        wt = mgr.create_worktree(repo_dir)
        wt_path = Path(wt.worktree_path)

        assert wt_path.exists()
        assert wt_path.is_relative_to(worktree_base)
        assert (wt_path / "src" / "app.py").exists()

        # Verify hook is disabled inside worktree
        res = subprocess.run(
            ["git", "config", "core.hooksPath"],
            cwd=wt_path,
            capture_output=True,
            text=True,
            check=True,
        )
        assert res.stdout.strip() == "/dev/null"

        # Verify modifications inside worktree do not affect main repo working directory
        (wt_path / "src" / "app.py").write_text("def add(a, b):\n    return a * b\n")
        assert (repo_dir / "src" / "app.py").read_text() == "def add(a, b):\n    return a + b\n"

        # Cleanup worktree
        cleaned = mgr.cleanup_worktree(wt_path)
        assert cleaned is True
        assert not wt_path.exists()


@pytest.mark.security
def test_patch_application_and_dry_run() -> None:
    """Ensure valid patches can be dry-run tested and cleanly applied."""
    with tempfile.TemporaryDirectory() as temp_dir:
        base_dir = Path(temp_dir)
        repo_dir = base_dir / "test_repo"
        repo_dir.mkdir()
        _init_test_git_repo(repo_dir)

        mgr = GitManager()
        wt = mgr.create_worktree(repo_dir)
        wt_path = Path(wt.worktree_path)

        valid_patch = """diff --git a/src/app.py b/src/app.py
--- a/src/app.py
+++ b/src/app.py
@@ -1,2 +1,2 @@
 def add(a, b):
-    return a + b
+    return a + b + 1
"""
        # 1. Dry run check
        check_res = mgr.apply_patch(wt_path, valid_patch, check_only=True)
        assert check_res.success is True
        assert "src/app.py" in check_res.applied_files
        # File should not be modified yet
        assert "+ 1" not in (wt_path / "src" / "app.py").read_text()

        # 2. Apply patch
        apply_res = mgr.apply_patch(wt_path, valid_patch, check_only=False)
        assert apply_res.success is True
        assert "+ 1" in (wt_path / "src" / "app.py").read_text()

        mgr.cleanup_worktree(wt_path)


@pytest.mark.security
def test_patch_path_traversal_rejected() -> None:
    """Ensure patches attempting path traversal outside worktree are blocked."""
    with tempfile.TemporaryDirectory() as temp_dir:
        base_dir = Path(temp_dir)
        repo_dir = base_dir / "test_repo"
        repo_dir.mkdir()
        _init_test_git_repo(repo_dir)

        mgr = GitManager()
        wt = mgr.create_worktree(repo_dir)
        wt_path = Path(wt.worktree_path)

        # Hostile patch attempting relative traversal outside worktree root
        traversal_patch = """diff --git a/src/app.py b/../../escaped.py
--- a/src/app.py
+++ b/../../escaped.py
@@ -0,0 +1 @@
+malicious_payload = True
"""
        with pytest.raises(PatchValidationError, match="traversal"):
            mgr.apply_patch(wt_path, traversal_patch)

        # Hostile patch attempting absolute path
        abs_patch = """diff --git a/src/app.py b//etc/evil.py
--- a/src/app.py
+++ b//etc/evil.py
@@ -0,0 +1 @@
+malicious_payload = True
"""
        with pytest.raises(PatchValidationError, match="absolute path"):
            mgr.apply_patch(wt_path, abs_patch)

        # Hostile patch attempting to overwrite protected files (.env)
        env_patch = """diff --git a/src/app.py b/.env
--- a/src/app.py
+++ b/.env
@@ -0,0 +1 @@
+SECRET=stolen
"""
        with pytest.raises(ProtectedPathError):
            mgr.apply_patch(wt_path, env_patch)

        mgr.cleanup_worktree(wt_path)


@pytest.mark.security
def test_list_permitted_files_and_search() -> None:
    """Ensure file listing filters out sensitive files and search bounds results."""
    with tempfile.TemporaryDirectory() as temp_dir:
        base_dir = Path(temp_dir)
        repo_dir = base_dir / "test_repo"
        repo_dir.mkdir()
        _init_test_git_repo(repo_dir)

        # Add forbidden and binary files
        (repo_dir / ".env").write_text("SECRET=xyz")
        (repo_dir / "id_rsa").write_text("PRIVATE KEY")
        (repo_dir / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        (repo_dir / "src" / "helper.py").write_text(
            "def helper():\n    return 'prometheus_magic'\n"
        )

        mgr = GitManager()
        files = mgr.list_permitted_files(repo_dir)

        # Permitted files must include regular code
        assert "src/app.py" in files
        assert "src/helper.py" in files
        assert "README.md" in files

        # Must NOT include .env, id_rsa, or binary .png
        assert ".env" not in files
        assert "id_rsa" not in files
        assert "logo.png" not in files

        # Test search
        results = mgr.search_source_code(repo_dir, query="prometheus_magic")
        assert len(results) == 1
        assert results[0]["file"] == "src/helper.py"
        assert "prometheus_magic" in results[0]["line_content"]


@pytest.mark.security
def test_cleanup_all_worktrees() -> None:
    """Ensure cleanup_all_worktrees removes multiple active/abandoned worktrees."""
    with tempfile.TemporaryDirectory() as temp_dir:
        base_dir = Path(temp_dir)
        repo_dir = base_dir / "test_repo"
        repo_dir.mkdir()
        _init_test_git_repo(repo_dir)

        mgr = GitManager(worktree_base_dir=base_dir / "wts")
        wt1 = mgr.create_worktree(repo_dir)
        wt2 = mgr.create_worktree(repo_dir)

        assert Path(wt1.worktree_path).exists()
        assert Path(wt2.worktree_path).exists()

        cleaned = mgr.cleanup_all_worktrees()
        assert len(cleaned) == 2
        assert not Path(wt1.worktree_path).exists()
        assert not Path(wt2.worktree_path).exists()
