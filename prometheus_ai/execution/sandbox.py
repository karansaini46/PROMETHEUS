"""Sandbox executor interface, resource limits, and execution results."""

import asyncio
import threading
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal


@dataclass(frozen=True)
class SandboxLimits:
    """Resource constraints for untrusted execution."""

    timeout_seconds: int = 300
    memory_limit: str = "4g"
    cpu_limit: float = 2.0
    pids_limit: int = 256
    disk_limit_mb: int = 512
    network_mode: Literal["none", "bridge"] = "none"
    max_output_bytes: int = 500_000
    user: str = "1000:1000"
    read_only_rootfs: bool = True
    drop_capabilities: tuple[str, ...] = ("ALL",)


@dataclass
class SandboxResult:
    """Outcome of command executed in an isolated container or runner."""

    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool = False
    oom_killed: bool = False
    cancelled: bool = False
    truncated: bool = False
    execution_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class CancellationToken:
    """Thread-safe cancellation token for running executions."""

    def __init__(self) -> None:
        self._is_cancelled = False
        self._lock = threading.Lock()
        self._callbacks: list[Callable[[], None]] = []

    @property
    def is_cancelled(self) -> bool:
        with self._lock:
            return self._is_cancelled

    def cancel(self) -> None:
        """Trigger cancellation and invoke registered callbacks."""
        callbacks_to_call: list[Callable[[], None]] = []
        with self._lock:
            if not self._is_cancelled:
                self._is_cancelled = True
                callbacks_to_call = list(self._callbacks)
                self._callbacks.clear()

        for callback in callbacks_to_call:
            try:
                callback()
            except Exception:
                pass

    def add_callback(self, callback: Callable[[], None]) -> None:
        """Register a callback to run if or when cancelled."""
        with self._lock:
            if self._is_cancelled:
                callbacks_to_call = [callback]
            else:
                self._callbacks.append(callback)
                callbacks_to_call = []

        for cb in callbacks_to_call:
            try:
                cb()
            except Exception:
                pass


class BaseSandboxRunner(ABC):
    """Abstract interface for isolated execution backends.

    Allows swappable implementations (Docker, gVisor, Firecracker microVM,
    or hardened local process runner for development/testing).
    """

    @property
    @abstractmethod
    def backend_name(self) -> str:
        """Identifier for the execution backend."""
        raise NotImplementedError

    @property
    @abstractmethod
    def isolation_level(self) -> str:
        """Description of the isolation boundary (e.g. 'container', 'process', 'microvm')."""
        raise NotImplementedError

    @abstractmethod
    def execute_command(
        self,
        cmd: list[str],
        cwd: Path | str | None = None,
        env: dict[str, str] | None = None,
        limits: SandboxLimits | None = None,
        cancel_token: CancellationToken | None = None,
        network_enabled: bool = False,
    ) -> SandboxResult:
        """Execute a command within the sandboxed environment synchronously."""
        raise NotImplementedError

    async def execute_command_async(
        self,
        cmd: list[str],
        cwd: Path | str | None = None,
        env: dict[str, str] | None = None,
        limits: SandboxLimits | None = None,
        cancel_token: CancellationToken | None = None,
        network_enabled: bool = False,
    ) -> SandboxResult:
        """Execute a command within the sandboxed environment asynchronously."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            self.execute_command,
            cmd,
            cwd,
            env,
            limits,
            cancel_token,
            network_enabled,
        )

    @abstractmethod
    def cancel(self, execution_id: str) -> bool:
        """Cancel an ongoing execution by identifier."""
        raise NotImplementedError

    @abstractmethod
    def cleanup(self) -> None:
        """Clean up all abandoned or persistent execution artifacts/containers."""
        raise NotImplementedError
