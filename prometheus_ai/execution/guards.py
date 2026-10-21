"""Execution guards and sandbox isolation security policies."""

import os
import re
from pathlib import Path
from typing import Any

from prometheus_ai.models.sanitizer import sanitize_secrets

# --- Exception Hierarchy ---


class SecurityException(Exception):
    """Base exception for all security boundary violations."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class PathTraversalError(SecurityException):
    """Raised when a path attempts directory traversal outside allowed roots."""

    pass


class SymlinkEscapeError(SecurityException):
    """Raised when a symlink targets a path outside allowed roots or loops."""

    pass


class ProtectedPathError(SecurityException):
    """Raised when attempting to access sensitive/protected files."""

    pass


class ResourceLimitExceededError(SecurityException):
    """Raised when an operation exceeds bounded size, depth, or time limits."""

    pass


class CommandPolicyViolationError(SecurityException):
    """Raised when a command violates isolation or execution allowlists."""

    pass


class PatchValidationError(SecurityException):
    """Raised when a proposed patch contains dangerous paths or structures."""

    pass


# --- Security Constants and Limits ---

DEFAULT_MAX_FILE_READ_BYTES: int = 2 * 1024 * 1024  # 2 MB
DEFAULT_MAX_OUTPUT_BYTES: int = 500 * 1024  # 500 KB
DEFAULT_MAX_SEARCH_RESULTS: int = 200
DEFAULT_MAX_RECURSION_DEPTH: int = 20
DEFAULT_MAX_EXECUTION_TIMEOUT: int = 300  # 5 minutes

PROTECTED_EXACT_NAMES: frozenset[str] = frozenset(
    {
        ".env",
        ".env.local",
        ".env.production",
        ".env.development",
        ".env.test",
        ".git/config",
        ".git/hooks",
        "id_rsa",
        "id_ed25519",
        "id_dsa",
        "id_ecdsa",
        ".netrc",
        ".bash_history",
        ".zsh_history",
        ".docker/config.json",
    }
)

PROTECTED_NAME_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^\.env(\..+)?$", re.IGNORECASE),
    re.compile(r"^.*id_(rsa|ed25519|dsa|ecdsa)(\.pub)?$", re.IGNORECASE),
    re.compile(r"^.*\.pem$", re.IGNORECASE),
    re.compile(r"^.*\.key$", re.IGNORECASE),
    re.compile(r"^.*\.pfx$", re.IGNORECASE),
    re.compile(r"^.*credentials(\.json|\.ini|\.xml)?$", re.IGNORECASE),
    re.compile(r"^.*secrets?(\.json|\.yml|\.yaml)?$", re.IGNORECASE),
)

PROTECTED_DIR_PARTS: frozenset[str] = frozenset(
    {
        ".ssh",
        ".aws",
        ".gnupg",
        ".docker",
    }
)


# --- Validation Functions ---


def validate_safe_filename(filename: str) -> str:
    """Validate that a filename is free of null bytes and illegal control characters."""
    if not filename:
        raise SecurityException("Filename cannot be empty")

    if "\0" in filename:
        raise PathTraversalError("Filename contains forbidden null byte")

    # Reject ASCII control characters (0-31 and 127)
    for ch in filename:
        if ord(ch) < 32 or ord(ch) == 127:
            raise SecurityException(
                f"Filename contains forbidden control character (ASCII {ord(ch)})"
            )

    return filename


def is_protected_file(relative_path: Path | str) -> bool:
    """Check if a relative path matches any protected/sensitive file criteria."""
    rel = Path(relative_path)
    posix_path = rel.as_posix().lower()

    # Exact name check
    for protected in PROTECTED_EXACT_NAMES:
        if posix_path == protected.lower() or posix_path.endswith(f"/{protected.lower()}"):
            return True

    # Protected directory parts
    for part in rel.parts:
        if part.lower() in PROTECTED_DIR_PARTS:
            return True

    # Regex patterns on filename
    file_name = rel.name
    for pattern in PROTECTED_NAME_PATTERNS:
        if pattern.match(file_name):
            return True

    return False


def validate_safe_path(
    base_dir: str | Path,
    target_path: str | Path,
    allow_nonexistent: bool = False,
    check_protected: bool = True,
) -> Path:
    """Validate that target_path resolves strictly within base_dir.

    Prevents directory traversal (e.g. `../../etc/passwd`), null-byte poisoning,
    and symlink escapes outside the designated base directory.
    """
    raw_str = str(target_path)
    if "\0" in raw_str:
        raise PathTraversalError("Path traversal detected: path contains null byte")

    resolved_base = Path(base_dir).resolve()
    target = Path(target_path)

    # If target is absolute, check containment or join
    if target.is_absolute():
        resolved_target = target.resolve()
    else:
        resolved_target = (resolved_base / target).resolve()

    # Check if target or any parent component along the unresolved path is a symlink
    unresolved_target = target if target.is_absolute() else (resolved_base / target)
    curr = unresolved_target
    while curr != resolved_base and curr != curr.parent:
        if curr.is_symlink():
            try:
                real = Path(os.path.realpath(curr))
            except (OSError, RuntimeError) as err:
                raise SymlinkEscapeError(f"Symlink resolution failed for '{curr}': {err}") from err
            if not real.is_relative_to(resolved_base):
                raise SymlinkEscapeError(
                    f"Symlink traversal detected: '{target_path}' targets external file '{real}'"
                )
        curr = curr.parent

    # Boundary check
    if not resolved_target.is_relative_to(resolved_base):
        raise PathTraversalError(
            f"Path traversal detected: '{target_path}' escapes root '{base_dir}'"
        )

    # Existence check
    if not allow_nonexistent and not resolved_target.exists():
        raise FileNotFoundError(f"Path does not exist within boundary: '{target_path}'")

    # Protected file check
    if check_protected:
        rel_to_base = resolved_target.relative_to(resolved_base)
        if is_protected_file(rel_to_base):
            raise ProtectedPathError(
                f"Access denied: '{target_path}' is a protected file or contains sensitive credentials"
            )

    return resolved_target


def sanitize_untrusted_output(
    text: str,
    max_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
) -> tuple[str, bool]:
    """Sanitize and bound untrusted command output or file content.

    Redacts known secrets and enforces a strict byte cap with truncation notice.
    Returns (sanitized_text, was_truncated).
    """
    # First redact application secrets
    scrubbed = sanitize_secrets(text)
    encoded = scrubbed.encode("utf-8", errors="replace")

    if len(encoded) <= max_bytes:
        return scrubbed, False

    # Truncate at safe byte boundary
    truncated_bytes = encoded[:max_bytes]
    truncated_text = truncated_bytes.decode("utf-8", errors="ignore")
    notice = f"\n\n[PROMETHEUS: Output truncated at {max_bytes} bytes limit]"
    return truncated_text + notice, True


def validate_safe_command_args(args: list[str]) -> list[str]:
    """Validate that command arguments do not contain forbidden control sequences."""
    if not args:
        raise CommandPolicyViolationError("Command argument list cannot be empty")

    for arg in args:
        if not isinstance(arg, str):
            raise CommandPolicyViolationError(f"Command argument must be a string: {arg!r}")
        if "\0" in arg:
            raise CommandPolicyViolationError(
                f"Command argument contains forbidden null byte: {arg!r}"
            )

    return args


FORBIDDEN_SYSTEM_ROOTS: frozenset[str] = frozenset(
    {"/", "/etc", "/proc", "/sys", "/dev", "/boot", "/root", "/bin", "/sbin", "/usr"}
)


def validate_safe_repo_dir(repo_path: str | Path) -> Path:
    """Validate that a repository directory path is canonical and not an OS system root."""
    raw = str(repo_path)
    if "\0" in raw:
        raise PathTraversalError("Repository path contains forbidden null byte")

    resolved = Path(repo_path).resolve()
    resolved_str = str(resolved).rstrip("/")

    if resolved_str in FORBIDDEN_SYSTEM_ROOTS or resolved_str == "":
        raise SecurityException(
            f"Access denied: Path '{repo_path}' targets a forbidden system root directory"
        )

    for forbidden in FORBIDDEN_SYSTEM_ROOTS:
        if forbidden != "/" and resolved_str.startswith(f"{forbidden}/"):
            raise SecurityException(
                f"Access denied: Path '{repo_path}' is inside protected system directory '{forbidden}'"
            )

    return resolved


def validate_safe_git_ref(ref: str) -> str:
    """Validate that a git branch name or commit ref is free of command injection flags and illegal characters."""
    if not ref or not isinstance(ref, str):
        raise SecurityException("Git ref cannot be empty")

    clean_ref = ref.strip()
    if clean_ref.startswith("-"):
        raise SecurityException(
            f"Git ref cannot start with a dash to prevent option injection: '{ref}'"
        )

    if "\0" in clean_ref:
        raise PathTraversalError("Git ref contains forbidden null byte")

    # Reject whitespace and control characters
    for ch in clean_ref:
        if ord(ch) <= 32 or ord(ch) == 127:
            raise SecurityException(
                f"Git ref contains forbidden whitespace or control character: '{ref}'"
            )

    # Reject shell injection metacharacters
    forbidden_chars = set(";$\"`'|&><!\\()")
    for ch in clean_ref:
        if ch in forbidden_chars:
            raise SecurityException(
                f"Git ref contains forbidden shell metacharacter '{ch}': '{ref}'"
            )

    # Check for git illegal ref sequences
    forbidden_sequences = ["..", "@{", "//"]
    for seq in forbidden_sequences:
        if seq in clean_ref:
            raise SecurityException(
                f"Git ref contains illegal git character sequence '{seq}': '{ref}'"
            )

    if len(clean_ref) > 255:
        raise ResourceLimitExceededError(
            f"Git ref exceeds maximum length of 255 characters: '{ref}'"
        )

    return clean_ref
