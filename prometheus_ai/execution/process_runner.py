"""Hardened local process sandbox runner for development and fallback execution."""

import logging
import os
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

from prometheus_ai.execution.guards import (
    SecurityException,
    sanitize_untrusted_output,
    validate_safe_command_args,
)
from prometheus_ai.execution.sandbox import (
    BaseSandboxRunner,
    CancellationToken,
    SandboxLimits,
    SandboxResult,
)

logger = logging.getLogger(__name__)

# Sterile environment whitelist
STERILE_LOCAL_ENV: dict[str, str] = {
    "PATH": "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
    "PYTHONDONTWRITEBYTECODE": "1",
}


class ProcessSandboxRunner(BaseSandboxRunner):
    """Fallback local process runner enforcing resource limits and sterile environment.

    Used when Docker daemon is unavailable or for lightweight security testing.
    """

    def __init__(self) -> None:
        self._active_processes: dict[str, subprocess.Popen[bytes]] = {}

    @property
    def backend_name(self) -> str:
        return "process"

    @property
    def isolation_level(self) -> str:
        return "process"

    def execute_command(
        self,
        cmd: list[str],
        cwd: Path | str | None = None,
        env: dict[str, str] | None = None,
        limits: SandboxLimits | None = None,
        cancel_token: CancellationToken | None = None,
        network_enabled: bool = False,
    ) -> SandboxResult:
        """Execute command in a constrained local subprocess."""
        validate_safe_command_args(cmd)
        active_limits = limits or SandboxLimits()
        execution_id = f"prometheus-proc-{uuid.uuid4().hex[:12]}"

        # Resolve and validate working directory
        work_dir = None
        if cwd:
            work_dir = str(Path(cwd).resolve())

        # Construct sterile environment
        sterile_env = dict(STERILE_LOCAL_ENV)
        venv_bin = Path(sys.prefix) / "bin"
        if venv_bin.exists():
            sterile_env["PATH"] = f"{venv_bin}:{sterile_env['PATH']}"

        if cwd:
            sterile_env["HOME"] = str(work_dir)
            sterile_env["PYTHONPATH"] = str(work_dir)

        if env:
            for key, val in env.items():
                if any(sec in key.upper() for sec in ("KEY", "SECRET", "TOKEN", "AUTH", "PASS")):
                    raise SecurityException(
                        f"Attempted to pass sensitive environment variable '{key}' to sandbox runner"
                    )
                sterile_env[key] = val

        start_time = time.monotonic()
        timed_out = False
        was_cancelled = False
        oom_killed = False

        # Set up POSIX resource limits hook if supported
        def preexec() -> None:
            # Create a new process group so we can terminate all children cleanly
            os.setsid()
            try:
                import resource

                # Set maximum process count limit
                if hasattr(resource, "RLIMIT_NPROC"):
                    resource.setrlimit(
                        resource.RLIMIT_NPROC,
                        (active_limits.pids_limit, active_limits.pids_limit),
                    )
            except Exception:
                pass

        try:
            try:
                proc = subprocess.Popen(
                    cmd,
                    cwd=work_dir,
                    env=sterile_env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    shell=False,  # Strictly disallow shell interpolation
                    preexec_fn=preexec,
                )
            except FileNotFoundError as err:
                return SandboxResult(
                    exit_code=127,
                    stdout="",
                    stderr=f"[PROMETHEUS: Command not found]: {err}",
                    duration_seconds=time.monotonic() - start_time,
                    execution_id=execution_id,
                    metadata={"backend": self.backend_name},
                )
            self._active_processes[execution_id] = proc

            if cancel_token:

                def _on_cancel() -> None:
                    self.cancel(execution_id)

                cancel_token.add_callback(_on_cancel)
                if cancel_token.is_cancelled:
                    was_cancelled = True
                    self.cancel(execution_id)
                    return SandboxResult(
                        exit_code=-1,
                        stdout="",
                        stderr="Execution cancelled before start",
                        duration_seconds=0.0,
                        cancelled=True,
                        execution_id=execution_id,
                    )

            try:
                raw_stdout, raw_stderr = proc.communicate(timeout=active_limits.timeout_seconds)
                exit_code = proc.returncode
            except subprocess.TimeoutExpired:
                timed_out = True
                self._terminate_proc_group(proc)
                raw_stdout, raw_stderr = proc.communicate()
                exit_code = -1
            except Exception:
                self._terminate_proc_group(proc)
                raw_stdout, raw_stderr = b"", b""
                exit_code = -1

            duration_seconds = time.monotonic() - start_time

            if cancel_token and cancel_token.is_cancelled:
                was_cancelled = True

            # If terminated by SIGKILL (-9) or SIGTERM (-15)
            if (
                exit_code in (-signal.SIGKILL, -signal.SIGTERM)
                and not timed_out
                and not was_cancelled
            ):
                oom_killed = True

            stdout_str = (raw_stdout or b"").decode("utf-8", errors="replace")
            stderr_str = (raw_stderr or b"").decode("utf-8", errors="replace")

            clean_stdout, stdout_trunc = sanitize_untrusted_output(
                stdout_str, max_bytes=active_limits.max_output_bytes
            )
            clean_stderr, stderr_trunc = sanitize_untrusted_output(
                stderr_str, max_bytes=active_limits.max_output_bytes
            )

            if timed_out:
                clean_stderr += f"\n[PROMETHEUS: Execution exceeded hard timeout of {active_limits.timeout_seconds}s]"
            if was_cancelled:
                clean_stderr += "\n[PROMETHEUS: Execution was explicitly cancelled]"

            return SandboxResult(
                exit_code=exit_code,
                stdout=clean_stdout,
                stderr=clean_stderr,
                duration_seconds=duration_seconds,
                timed_out=timed_out,
                oom_killed=oom_killed,
                cancelled=was_cancelled,
                truncated=stdout_trunc or stderr_trunc,
                execution_id=execution_id,
                metadata={"backend": self.backend_name},
            )

        finally:
            self._active_processes.pop(execution_id, None)

    def _terminate_proc_group(self, proc: subprocess.Popen[bytes]) -> None:
        """Terminate process group cleanly with SIGTERM then SIGKILL."""
        try:
            pgid = os.getpgid(proc.pid)
            os.killpg(pgid, signal.SIGTERM)
            time.sleep(0.1)
            os.killpg(pgid, signal.SIGKILL)
        except (ProcessLookupError, OSError):
            pass

    def cancel(self, execution_id: str) -> bool:
        """Cancel execution by process group termination."""
        proc = self._active_processes.get(execution_id)
        if proc:
            self._terminate_proc_group(proc)
            return True
        return False

    def cleanup(self) -> None:
        """Kill all active processes tracked by this runner."""
        for _execution_id, proc in list(self._active_processes.items()):
            self._terminate_proc_group(proc)
        self._active_processes.clear()
