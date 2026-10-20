"""Execution and Testing Tools for Agent Tool-Calling."""

import threading
import uuid
from typing import Any

from prometheus_ai.execution.allowlist import validate_test_command
from prometheus_ai.execution.sandbox import (
    BaseSandboxRunner,
    CancellationToken,
    SandboxLimits,
    SandboxResult,
)
from prometheus_ai.tools.base import BaseTool, ToolDefinition


class ExecutionRegistry:
    """Thread-safe registry of active executions and cancellation tokens."""

    _instance: "ExecutionRegistry | None" = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._tokens: dict[str, CancellationToken] = {}
        self._runners: dict[str, BaseSandboxRunner] = {}
        self._mu = threading.Lock()

    @classmethod
    def get_instance(cls) -> "ExecutionRegistry":
        with cls._lock:
            if cls._instance is None:
                cls._instance = ExecutionRegistry()
            return cls._instance

    def register(
        self,
        execution_id: str,
        token: CancellationToken,
        runner: BaseSandboxRunner,
    ) -> None:
        with self._mu:
            self._tokens[execution_id] = token
            self._runners[execution_id] = runner

    def unregister(self, execution_id: str) -> None:
        with self._mu:
            self._tokens.pop(execution_id, None)
            self._runners.pop(execution_id, None)

    def cancel(self, execution_id: str) -> bool:
        with self._mu:
            token = self._tokens.get(execution_id)
            runner = self._runners.get(execution_id)

        cancelled = False
        if token:
            token.cancel()
            cancelled = True
        if runner:
            runner_cancelled = runner.cancel(execution_id)
            cancelled = cancelled or runner_cancelled
        return cancelled


class RunAllowlistedTestsTool(BaseTool):
    """Execute allowlisted tests inside the sandbox environment."""

    def __init__(
        self,
        runner: BaseSandboxRunner,
        registry: ExecutionRegistry | None = None,
    ) -> None:
        self.runner = runner
        self.registry = registry or ExecutionRegistry.get_instance()

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="run_allowlisted_tests",
            description="Run allowlisted tests (e.g. pytest, npm test) in an isolated sandbox with resource constraints.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "worktree_path": {
                        "type": "string",
                        "description": "Absolute path to worktree.",
                    },
                    "test_runner": {
                        "type": "string",
                        "description": "Allowlisted runner (e.g. 'pytest', 'python -m unittest').",
                        "default": "pytest",
                    },
                    "test_target": {
                        "type": "string",
                        "description": "Optional specific test file or directory path relative to worktree.",
                    },
                    "extra_args": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional safe command line flags (e.g. ['-k', 'test_login']).",
                    },
                    "timeout_seconds": {
                        "type": "integer",
                        "description": "Maximum execution time in seconds.",
                        "default": 300,
                    },
                    "network_enabled": {
                        "type": "boolean",
                        "description": "Explicit permission to enable network access.",
                        "default": False,
                    },
                },
                "required": ["worktree_path"],
            },
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        worktree_path = str(kwargs.get("worktree_path", ""))
        test_runner = str(kwargs.get("test_runner", "pytest"))
        test_target = kwargs.get("test_target")
        extra_args = kwargs.get("extra_args")
        timeout_seconds = int(kwargs.get("timeout_seconds", 300))
        network_enabled = bool(kwargs.get("network_enabled", False))

        # 1. Validate test command against allowlist and injection rules
        cmd = validate_test_command(
            runner=test_runner,
            target=test_target,
            extra_args=extra_args,
            workspace_dir=worktree_path,
        )

        limits = SandboxLimits(
            timeout_seconds=timeout_seconds,
            network_mode="bridge" if network_enabled else "none",
        )

        # 2. Setup cancellation token and register execution
        cancel_token = CancellationToken()
        execution_id = (
            f"exec-{uuid.uuid4().hex[:12]}" if "uuid" in globals() else f"exec-{id(cancel_token)}"
        )
        self.registry.register(execution_id, cancel_token, self.runner)

        try:
            # Run async in executor
            result: SandboxResult = await self.runner.execute_command_async(
                cmd=cmd,
                cwd=worktree_path,
                limits=limits,
                cancel_token=cancel_token,
                network_enabled=network_enabled,
            )
        finally:
            self.registry.unregister(execution_id)

        return {
            "exit_code": result.exit_code,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "duration_seconds": result.duration_seconds,
            "timed_out": result.timed_out,
            "oom_killed": result.oom_killed,
            "cancelled": result.cancelled,
            "truncated": result.truncated,
            "execution_id": result.execution_id,
            "backend": self.runner.backend_name,
            "isolation_level": self.runner.isolation_level,
        }


class CancelExecutionTool(BaseTool):
    """Explicitly cancel a running sandbox execution."""

    def __init__(self, registry: ExecutionRegistry | None = None) -> None:
        self.registry = registry or ExecutionRegistry.get_instance()

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="cancel_execution",
            description="Cancel an active running sandbox execution and terminate its resources.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "execution_id": {
                        "type": "string",
                        "description": "The execution identifier to cancel.",
                    },
                },
                "required": ["execution_id"],
            },
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        execution_id = str(kwargs.get("execution_id", ""))
        cancelled = self.registry.cancel(execution_id)
        return {
            "execution_id": execution_id,
            "cancelled": cancelled,
        }
