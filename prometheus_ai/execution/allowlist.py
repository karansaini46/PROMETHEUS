"""Test command allowlisting and injection defense policies."""

import re
import shutil
from pathlib import Path
from typing import Final

from prometheus_ai.execution.guards import (
    CommandPolicyViolationError,
    validate_safe_command_args,
    validate_safe_path,
)

# Supported test runner bases
ALLOWED_TEST_RUNNERS: Final[frozenset[str]] = frozenset(
    {
        "pytest",
        "python",
        "python3",
        "npm",
        "yarn",
        "pnpm",
        "cargo",
        "go",
    }
)

# Shell metacharacters that must never appear in command tokens
DANGEROUS_SHELL_PATTERN: Final[re.Pattern[str]] = re.compile(r"[;&|`$<>\n\r\t]")

# Dangerous flags that could lead to host breakout or arbitrary script loading
DISALLOWED_RUNNER_FLAGS: Final[frozenset[str]] = frozenset(
    {
        "--override-ini",
        "-c",
        "--import-mode",
        "--exec",
        "-e",
    }
)


def validate_test_command(
    runner: str,
    target: str | None = None,
    extra_args: list[str] | None = None,
    workspace_dir: str | Path | None = None,
) -> list[str]:
    """Validate and build an allowlisted test execution command.

    Ensures that only permitted test runners and arguments can execute,
    preventing arbitrary shell injection or external script loading.
    """
    clean_runner = runner.strip()
    if not clean_runner:
        raise CommandPolicyViolationError("Test runner cannot be empty")

    # Check for shell metacharacters in runner name
    if DANGEROUS_SHELL_PATTERN.search(clean_runner):
        raise CommandPolicyViolationError(
            f"Forbidden shell metacharacters in runner: {clean_runner!r}"
        )

    # Split runner if given as e.g. "python -m unittest" or "npm test"
    runner_tokens = clean_runner.split()
    base_runner = runner_tokens[0]

    if base_runner not in ALLOWED_TEST_RUNNERS:
        raise CommandPolicyViolationError(
            f"Test runner '{base_runner}' is not in the permitted allowlist: "
            f"{sorted(ALLOWED_TEST_RUNNERS)}"
        )

    cmd_tokens: list[str] = list(runner_tokens)

    # Special validation for python
    if base_runner in ("python", "python3"):
        if len(runner_tokens) < 2 or runner_tokens[1] != "-m":
            raise CommandPolicyViolationError(
                "Python runner is only permitted as a module runner (e.g. 'python -m unittest')"
            )
        module_name = runner_tokens[2] if len(runner_tokens) > 2 else ""
        if module_name not in ("unittest", "pytest"):
            raise CommandPolicyViolationError(
                f"Unauthorized python module for test execution: {module_name!r}"
            )
        if base_runner == "python" and not shutil.which("python") and shutil.which("python3"):
            cmd_tokens[0] = "python3"

    # Validate target path if specified
    if target:
        clean_target = target.strip()
        if DANGEROUS_SHELL_PATTERN.search(clean_target):
            raise CommandPolicyViolationError(
                f"Forbidden shell metacharacters in test target: {clean_target!r}"
            )
        if workspace_dir:
            # Must be within workspace directory
            validate_safe_path(
                workspace_dir, clean_target, allow_nonexistent=False, check_protected=True
            )
        cmd_tokens.append(clean_target)

    # Validate extra arguments
    if extra_args:
        validate_safe_command_args(extra_args)
        for arg in extra_args:
            clean_arg = arg.strip()
            if DANGEROUS_SHELL_PATTERN.search(clean_arg):
                raise CommandPolicyViolationError(
                    f"Forbidden shell metacharacters in argument: {clean_arg!r}"
                )
            for disallowed in DISALLOWED_RUNNER_FLAGS:
                if clean_arg == disallowed or clean_arg.startswith(f"{disallowed}="):
                    raise CommandPolicyViolationError(
                        f"Forbidden option flag for test runner: {clean_arg!r}"
                    )
            cmd_tokens.append(clean_arg)

    return cmd_tokens
