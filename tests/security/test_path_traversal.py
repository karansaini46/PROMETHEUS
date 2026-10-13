"""Security tests for path traversal guards and worktree boundaries."""

import tempfile
from pathlib import Path

import pytest

from prometheus_ai.execution.guards import (
    DEFAULT_MAX_OUTPUT_BYTES,
    PathTraversalError,
    ProtectedPathError,
    SecurityException,
    SymlinkEscapeError,
    is_protected_file,
    sanitize_untrusted_output,
    validate_safe_filename,
    validate_safe_path,
)


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

        nested = base / "sub"
        nested.mkdir()
        with pytest.raises(PathTraversalError):
            validate_safe_path(base, "sub/../../../../etc/shadow")


@pytest.mark.security
def test_traversal_absolute_escape_rejected() -> None:
    """Ensure absolute paths outside the base directory are rejected."""
    with tempfile.TemporaryDirectory() as temp_dir:
        base = Path(temp_dir)
        with pytest.raises(PathTraversalError):
            validate_safe_path(base, "/etc/passwd")


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


@pytest.mark.security
def test_symlink_chain_escape_rejected() -> None:
    """Ensure chained symlinks attempting to escape are caught."""
    with tempfile.TemporaryDirectory() as temp_dir:
        base = Path(temp_dir)
        external_file = base.parent / "ext_target.txt"
        external_file.write_text("external content")

        try:
            link1 = base / "link1"
            link1.symlink_to(external_file)

            link2 = base / "link2"
            link2.symlink_to(link1)

            with pytest.raises(SymlinkEscapeError):
                validate_safe_path(base, "link2")
        finally:
            if external_file.exists():
                external_file.unlink()


@pytest.mark.security
def test_malicious_filenames_rejected() -> None:
    """Ensure filenames containing null bytes or control characters are rejected."""
    with pytest.raises(PathTraversalError):
        validate_safe_filename("main.py\0.evil")

    with pytest.raises(SecurityException, match="control character"):
        validate_safe_filename("file\x01name.py")

    with pytest.raises(SecurityException, match="control character"):
        validate_safe_filename("test\x1fname.py")

    with pytest.raises(SecurityException, match="empty"):
        validate_safe_filename("")

    assert validate_safe_filename("valid_file-name.123.py") == "valid_file-name.123.py"


@pytest.mark.security
def test_null_byte_in_path_rejected() -> None:
    """Ensure null bytes in paths trigger immediate traversal errors."""
    with tempfile.TemporaryDirectory() as temp_dir:
        base = Path(temp_dir)
        with pytest.raises(PathTraversalError, match="null byte"):
            validate_safe_path(base, "safe_dir/test\0file.txt")


@pytest.mark.security
def test_protected_files_blocked() -> None:
    """Ensure sensitive credentials and configuration files are blocked."""
    with tempfile.TemporaryDirectory() as temp_dir:
        base = Path(temp_dir)

        # Create sensitive files inside the base dir
        env_file = base / ".env"
        env_file.write_text("SECRET=123")

        prod_env = base / ".env.production"
        prod_env.write_text("DB_PASS=xyz")

        ssh_key = base / "id_rsa"
        ssh_key.write_text("-----BEGIN RSA PRIVATE KEY-----")

        aws_cred = base / ".aws" / "credentials"
        aws_cred.parent.mkdir(parents=True)
        aws_cred.write_text("[default]\naws_access_key_id=test")

        git_cfg = base / ".git" / "config"
        git_cfg.parent.mkdir(parents=True)
        git_cfg.write_text("[core]\nrepositoryformatversion=0")

        # All must be rejected by is_protected_file
        assert is_protected_file(".env")
        assert is_protected_file(".env.production")
        assert is_protected_file("id_rsa")
        assert is_protected_file(".aws/credentials")
        assert is_protected_file(".git/config")
        assert is_protected_file("server.pem")
        assert is_protected_file("cert.key")

        # And rejected by validate_safe_path
        with pytest.raises(ProtectedPathError):
            validate_safe_path(base, ".env")

        with pytest.raises(ProtectedPathError):
            validate_safe_path(base, ".env.production")

        with pytest.raises(ProtectedPathError):
            validate_safe_path(base, "id_rsa")

        with pytest.raises(ProtectedPathError):
            validate_safe_path(base, ".aws/credentials")


@pytest.mark.security
def test_output_bounds_and_truncation() -> None:
    """Ensure output sanitization bounds size and truncates with warning."""
    huge_text = "A" * (DEFAULT_MAX_OUTPUT_BYTES + 5000)
    sanitized, truncated = sanitize_untrusted_output(huge_text)
    assert truncated is True
    assert len(sanitized.encode("utf-8")) <= DEFAULT_MAX_OUTPUT_BYTES + 200
    assert "Output truncated" in sanitized

    # Small text is not truncated
    small_text = "Standard test output line\n"
    sanitized_sm, truncated_sm = sanitize_untrusted_output(small_text)
    assert truncated_sm is False
    assert sanitized_sm == small_text
