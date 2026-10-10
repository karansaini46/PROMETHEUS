"""Security tests for path traversal guards and worktree boundaries."""

import tempfile
from pathlib import Path

import pytest

from prometheus_ai.execution.guards import SecurityException, validate_safe_path


@pytest.mark.security
def test_valid_path_within_root() -> None:
    """Ensure safe paths inside base directory are accepted."""
    with tempfile.TemporaryDirectory() as temp_dir:
        base = Path(temp_dir)
        subfile = base / "src" / "main.py"
        subfile.parent.mkdir(parents=True)
        subfile.write_text("print('hello')")

        safe = validate_safe_path(base, "src/main.py")
        assert safe.exists()
        assert safe == subfile.resolve()


@pytest.mark.security
def test_traversal_relative_escape_rejected() -> None:
    """Ensure paths attempting relative directory traversal are rejected."""
    with tempfile.TemporaryDirectory() as temp_dir:
        base = Path(temp_dir)
        with pytest.raises(SecurityException, match="Path traversal detected"):
            validate_safe_path(base, "../../../etc/passwd")


@pytest.mark.security
def test_symlink_escape_rejected() -> None:
    """Ensure symlinks pointing outside the base directory are rejected."""
    with tempfile.TemporaryDirectory() as temp_dir:
        base = Path(temp_dir)
        external_file = base.parent / "secret_file.txt"
        external_file.write_text("sensitive")

        try:
            symlink_path = base / "evil_link"
            symlink_path.symlink_to(external_file)

            with pytest.raises(SecurityException, match="traversal detected"):
                validate_safe_path(base, "evil_link")
        finally:
            if external_file.exists():
                external_file.unlink()
