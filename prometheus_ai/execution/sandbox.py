"""Docker sandbox executor interface and resource limits."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class SandboxLimits:
    """Resource constraints for untrusted execution."""

    timeout_seconds: int = 300
    memory_limit: str = "4g"
    cpu_limit: float = 2.0
    pids_limit: int = 256
    network_mode: Literal["none", "bridge"] = "none"


@dataclass
class SandboxResult:
    """Outcome of command executed in an isolated container."""

    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool = False
    oom_killed: bool = False


class BaseSandboxRunner:
    """Abstract interface for sandbox command runners."""

    def execute_command(self, cmd: list[str], timeout: int | None = None) -> SandboxResult:
        """Execute a command within the sandboxed environment."""
        raise NotImplementedError(
            "Milestone 1 Deliverable: Concrete Docker runner not yet initialized."
        )
