"""Hardened Docker Sandbox Runner implementation."""

import logging
import time
import uuid
from pathlib import Path
from typing import Any

import docker
from docker.errors import DockerException

from prometheus_ai.execution.guards import (
    PathTraversalError,
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
from services.api.telemetry import traced

logger = logging.getLogger(__name__)

# Sterile environment whitelist - Host env vars and API keys are strictly excluded
STERILE_ENV_WHITELIST: dict[str, str] = {
    "PATH": "/usr/local/bin:/usr/local/sbin:/usr/bin:/usr/sbin:/bin:/sbin",
    "PYTHONPATH": "/workspace",
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
    "HOME": "/workspace",
    "PYTHONDONTWRITEBYTECODE": "1",
}

FORBIDDEN_MOUNTS: frozenset[str] = frozenset(
    {
        "/var/run/docker.sock",
        "docker.sock",
        "/etc/shadow",
        "/etc/passwd",
        "/proc",
        "/sys",
    }
)


class DockerSandboxRunner(BaseSandboxRunner):
    """Containerized sandbox executing untrusted code with defense-in-depth isolation."""

    def __init__(
        self,
        image_name: str = "python:3.12-slim",
        client: docker.DockerClient | None = None,
    ) -> None:
        self.image_name = image_name
        self._client = client
        self._active_containers: dict[str, Any] = {}

    @property
    def backend_name(self) -> str:
        return "docker"

    @property
    def isolation_level(self) -> str:
        return "container"

    def _get_client(self) -> docker.DockerClient:
        if self._client is None:
            try:
                self._client = docker.from_env()
            except DockerException as err:
                raise SecurityException(
                    f"Docker daemon is not accessible: {err}. Ensure Docker is running."
                ) from err
        return self._client

    @traced(span_name="sandbox.execution")
    def execute_command(
        self,
        cmd: list[str],
        cwd: Path | str | None = None,
        env: dict[str, str] | None = None,
        limits: SandboxLimits | None = None,
        cancel_token: CancellationToken | None = None,
        network_enabled: bool = False,
    ) -> SandboxResult:
        """Run an untrusted command inside an ephemeral hardened Docker container."""
        validate_safe_command_args(cmd)
        active_limits = limits or SandboxLimits()
        execution_id = f"prometheus-box-{uuid.uuid4().hex[:12]}"

        # 1. Path & Mount Validation
        volumes: dict[str, dict[str, str]] = {}
        if cwd:
            resolved_cwd = Path(cwd).resolve()
            # Prevent mounting forbidden host files
            for forbidden in FORBIDDEN_MOUNTS:
                if forbidden in str(resolved_cwd):
                    raise PathTraversalError(
                        f"Mounting sensitive host path into sandbox is forbidden: {forbidden}"
                    )
            volumes[str(resolved_cwd)] = {"bind": "/workspace", "mode": "rw"}

        # 2. Sterile Environment Formulation
        sterile_env = dict(STERILE_ENV_WHITELIST)
        if env:
            # Only permit non-secret additional environment variables
            for key, val in env.items():
                if any(sec in key.upper() for sec in ("KEY", "SECRET", "TOKEN", "AUTH", "PASS")):
                    raise SecurityException(
                        f"Attempted to pass sensitive environment variable '{key}' to untrusted sandbox"
                    )
                sterile_env[key] = val

        # 3. Network Policy
        # Network access is deny-by-default
        effective_network = (
            "bridge" if (network_enabled and active_limits.network_mode != "none") else "none"
        )

        # 4. Resource & Hardening Parameters
        tmpfs_config = {
            "/tmp": f"size={active_limits.disk_limit_mb}m,noexec,nosuid",
            "/run": "size=16m,noexec,nosuid",
        }

        client = self._get_client()
        start_time = time.monotonic()
        container = None
        timed_out = False
        oom_killed = False
        was_cancelled = False

        try:
            container = client.containers.create(
                image=self.image_name,
                command=cmd,
                working_dir="/workspace",
                volumes=volumes,
                environment=sterile_env,
                user=active_limits.user,
                network_mode=effective_network,
                cap_drop=list(active_limits.drop_capabilities),
                security_opt=["no-new-privileges:true"],
                pids_limit=active_limits.pids_limit,
                mem_limit=active_limits.memory_limit,
                memswap_limit=active_limits.memory_limit,
                nano_cpus=int(active_limits.cpu_limit * 1_000_000_000),
                read_only=active_limits.read_only_rootfs,
                tmpfs=tmpfs_config,
                name=execution_id,
                detach=True,
            )
            self._active_containers[execution_id] = container

            # Wire cancellation token
            if cancel_token:

                def _on_cancel() -> None:
                    self.cancel(execution_id)

                cancel_token.add_callback(_on_cancel)
                if cancel_token.is_cancelled:
                    was_cancelled = True
                    return SandboxResult(
                        exit_code=-1,
                        stdout="",
                        stderr="Execution cancelled before start",
                        duration_seconds=0.0,
                        cancelled=True,
                        execution_id=execution_id,
                    )

            container.start()

            # Wait with bounded timeout
            try:
                res = container.wait(timeout=active_limits.timeout_seconds)
                exit_code = res.get("StatusCode", -1)
            except Exception:
                duration = time.monotonic() - start_time
                if cancel_token and cancel_token.is_cancelled:
                    was_cancelled = True
                elif duration >= active_limits.timeout_seconds:
                    timed_out = True
                try:
                    container.kill()
                except Exception:
                    pass
                exit_code = -1

            duration_seconds = time.monotonic() - start_time

            # Inspect container state for OOM
            try:
                container.reload()
                state = container.attrs.get("State", {})
                oom_killed = bool(state.get("OOMKilled", False))
            except Exception:
                pass

            # Extract logs bounded by output size
            try:
                raw_stdout = container.logs(stdout=True, stderr=False) or b""
                raw_stderr = container.logs(stdout=False, stderr=True) or b""
            except Exception:
                raw_stdout = b""
                raw_stderr = b""

            stdout_str = raw_stdout.decode("utf-8", errors="replace")
            stderr_str = raw_stderr.decode("utf-8", errors="replace")

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
            if oom_killed:
                clean_stderr += "\n[PROMETHEUS: Process killed by OOM (Out Of Memory)]"

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
                metadata={"backend": self.backend_name, "network_mode": effective_network},
            )

        finally:
            self._active_containers.pop(execution_id, None)
            if container:
                try:
                    container.remove(force=True, v=True)
                except Exception:
                    pass

    def cancel(self, execution_id: str) -> bool:
        """Stop and force remove a container associated with the execution."""
        container = self._active_containers.get(execution_id)
        if container:
            try:
                container.kill()
                container.remove(force=True, v=True)
                return True
            except Exception as err:
                logger.warning("Error cancelling container %s: %s", execution_id, err)
                return False
        return False

    def cleanup(self) -> None:
        """Remove any remaining active containers tracked by this runner."""
        for _execution_id, container in list(self._active_containers.items()):
            try:
                container.remove(force=True, v=True)
            except Exception:
                pass
        self._active_containers.clear()
