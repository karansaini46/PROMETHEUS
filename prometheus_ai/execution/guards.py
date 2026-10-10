"""Execution guards and sandbox isolation security policies."""

import os
from pathlib import Path


class SecurityException(Exception):
    """Raised when an operation violates security boundaries."""

    pass


def validate_safe_path(base_dir: str | Path, target_path: str | Path) -> Path:
    """Validate that target_path resolves strictly within base_dir.

    Prevents directory traversal (e.g. `../../etc/passwd` or symlink escapes).
    """
    resolved_base = Path(base_dir).resolve()
    resolved_target = (resolved_base / target_path).resolve()

    if not resolved_target.is_relative_to(resolved_base):
        raise SecurityException(
            f"Path traversal detected: '{target_path}' escapes root '{base_dir}'"
        )

    # Detect symlinks pointing outside the base directory
    if resolved_target.is_symlink():
        real_path = Path(os.path.realpath(resolved_target))
        if not real_path.is_relative_to(resolved_base):
            raise SecurityException(
                f"Symlink traversal detected: '{target_path}' targets external file '{real_path}'"
            )

    return resolved_target
