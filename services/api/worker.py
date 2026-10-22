"""PROMETHEUS Worker Management, Health Checks, Crash Recovery & Cleanup.

Provides:
- Worker lifecycle monitoring and heartbeat tracking.
- Startup crash recovery: identifies and recovers runs interrupted by server restarts.
- Abandoned resource cleanup: prunes orphaned git worktrees and dangling sandbox containers.
- Graceful shutdown: drains and cleanly terminates in-flight operations.
"""

import asyncio
import logging
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import docker
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from prometheus_ai.tools.execution import ExecutionRegistry
from services.api.config import get_settings
from services.api.models import (
    AuditEvent,
    ExecutionRun,
    RunStatusEnum,
    Task,
    TaskStatusEnum,
)

logger = logging.getLogger("prometheus.worker")
settings = get_settings()


class WorkerStatus:
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    DRAINING = "DRAINING"
    STOPPED = "STOPPED"


class WorkerManager:
    """Singleton worker supervisor for health monitoring and task recovery."""

    _instance: "WorkerManager | None" = None

    def __init__(self) -> None:
        self.status = WorkerStatus.STARTING
        self.started_at = datetime.now(UTC)
        self.last_heartbeat = datetime.now(UTC)
        self.active_tasks_count = 0
        self.recovered_tasks_count = 0
        self.tasks_completed_count = 0
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._is_running = False

    @classmethod
    def get_instance(cls) -> "WorkerManager":
        if cls._instance is None:
            cls._instance = WorkerManager()
        return cls._instance

    async def start(self) -> None:
        """Initialize worker monitoring and start background heartbeat."""
        self.status = WorkerStatus.RUNNING
        self._is_running = True
        self.last_heartbeat = datetime.now(UTC)
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        logger.info("PROMETHEUS WorkerManager started in state: %s", self.status)

    async def _heartbeat_loop(self) -> None:
        """Periodically update worker heartbeat timestamp."""
        while self._is_running:
            self.last_heartbeat = datetime.now(UTC)
            await asyncio.sleep(5.0)

    async def stop(self, timeout_seconds: float = 5.0) -> None:
        """Gracefully drain and shut down worker."""
        self.status = WorkerStatus.DRAINING
        self._is_running = False
        logger.info("Worker entering DRAINING state (timeout=%.1fs)...", timeout_seconds)

        # 1. Cancel in-flight executions via registry
        registry = ExecutionRegistry.get_instance()
        with registry._mu:
            active_ids = list(registry._tokens.keys())

        for exec_id in active_ids:
            logger.info("Cancelling in-flight execution on shutdown: %s", exec_id)
            registry.cancel(exec_id)

        # 2. Cancel heartbeat loop
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        # 3. Clean abandoned resources
        cleanup_abandoned_resources()

        self.status = WorkerStatus.STOPPED
        logger.info("PROMETHEUS WorkerManager stopped cleanly.")

    def get_health_metrics(self) -> dict[str, Any]:
        """Return worker health status and telemetry metrics."""
        now = datetime.now(UTC)
        heartbeat_age_sec = (now - self.last_heartbeat).total_seconds()
        is_healthy = self.status == WorkerStatus.RUNNING and heartbeat_age_sec < 15.0

        return {
            "status": self.status,
            "healthy": is_healthy,
            "uptime_seconds": round((now - self.started_at).total_seconds(), 1),
            "heartbeat_age_seconds": round(heartbeat_age_sec, 2),
            "last_heartbeat": self.last_heartbeat.isoformat(),
            "active_tasks": self.active_tasks_count,
            "recovered_tasks": self.recovered_tasks_count,
            "completed_tasks": self.tasks_completed_count,
        }

    async def recover_interrupted_tasks(self, db: AsyncSession) -> int:
        """Instance method to recover interrupted tasks."""
        return await recover_interrupted_tasks(db)

    async def cleanup_abandoned_resources(
        self, worktree_dir: str | Path | None = None
    ) -> dict[str, int]:
        """Instance method to prune orphaned worktrees and dangling containers."""
        return cleanup_abandoned_resources(worktree_dir)


async def recover_interrupted_tasks(db: AsyncSession) -> int:
    """Detect and recover runs left in RUNNING/PENDING status after server crash or restart."""
    now = datetime.now(UTC)
    stmt = select(ExecutionRun).where(
        ExecutionRun.status.in_([RunStatusEnum.RUNNING.value, RunStatusEnum.PENDING.value])
    )
    res = await db.execute(stmt)
    interrupted_runs = res.scalars().all()

    recovered_count = 0
    for run in interrupted_runs:
        logger.warning(
            "Recovering interrupted run %s (prior status: %s)...",
            run.id,
            run.status,
        )
        run.status = RunStatusEnum.FAILED.value
        run.error_message = (
            "Process terminated abruptly: host restarted or worker crashed during execution."
        )
        run.completed_at = now
        run.updated_at = now

        if run.task_id:
            task = await db.get(Task, run.task_id)
            if task and task.status == TaskStatusEnum.IN_PROGRESS.value:
                task.status = TaskStatusEnum.OPEN.value

        audit = AuditEvent(
            id=str(uuid4()),
            run_id=run.id,
            action="RUN_RECOVERED_AFTER_INTERRUPTION",
            actor="worker-recovery-system",
            resource_type="ExecutionRun",
            resource_id=run.id,
            details={
                "prior_status": run.status,
                "reason": "Host restarted or worker process crashed during execution; run safely marked as failed.",
            },
            created_at=now,
        )
        db.add(audit)
        recovered_count += 1

    if recovered_count > 0:
        await db.commit()
        logger.info("Successfully recovered %d interrupted runs.", recovered_count)
        WorkerManager.get_instance().recovered_tasks_count += recovered_count

    return recovered_count


def cleanup_abandoned_resources(worktree_dir: str | Path | None = None) -> dict[str, int]:
    """Prune orphaned git worktrees and dangling sandbox docker containers."""
    cleaned_worktrees = 0
    cleaned_containers = 0

    # 1. Clean worktrees directory
    base_dir = Path(worktree_dir or settings.WORKTREE_BASE_DIR).resolve()
    if base_dir.exists() and base_dir.is_dir():
        for item in base_dir.iterdir():
            if item.is_dir() and item.name.startswith("wt-"):
                try:
                    # Check age of worktree directory (> 1 hour considered abandoned)
                    mtime = item.stat().st_mtime
                    if time.time() - mtime > 3600:
                        shutil.rmtree(item, ignore_errors=True)
                        cleaned_worktrees += 1
                        logger.info("Pruned abandoned worktree: %s", item.name)
                except Exception as err:
                    logger.warning("Failed to clean worktree %s: %s", item, err)

    # 2. Clean docker containers with label prometheus.sandbox=true
    try:
        client = docker.from_env(timeout=2)
        containers = client.containers.list(all=True, filters={"label": "prometheus.sandbox=true"})
        for c in containers:
            try:
                # Remove stopped containers or containers running longer than 1 hour
                if c.status in ("exited", "dead"):
                    c.remove(force=True)
                    cleaned_containers += 1
                    logger.info("Pruned exited sandbox container: %s", c.id[:12])
            except Exception as c_err:
                logger.warning("Error pruning container %s: %s", c.id[:12], c_err)
    except Exception:
        # Docker not running or unavailable, skip
        pass

    return {
        "cleaned_worktrees": cleaned_worktrees,
        "cleaned_containers": cleaned_containers,
    }


async def run_standalone_worker() -> None:
    """Run worker supervisor in standalone daemon mode."""
    import signal

    from services.api.db import AsyncSessionLocal
    from services.api.logging_config import setup_logging

    setup_logging(level=settings.LOG_LEVEL)
    logger.info("Starting standalone PROMETHEUS background worker supervisor...")

    worker = WorkerManager.get_instance()
    await worker.start()

    # Perform initial crash recovery
    try:
        async with AsyncSessionLocal() as session:
            recovered = await recover_interrupted_tasks(session)
            if recovered > 0:
                logger.info("Standalone worker recovered %d interrupted tasks", recovered)
    except Exception as exc:
        logger.warning("Worker initial task recovery check failed: %s", exc)

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass

    try:
        # Periodic maintenance loop (prune abandoned worktrees/containers)
        while not stop_event.is_set():
            try:
                cleanup_abandoned_resources()
            except Exception as e:
                logger.warning("Worker periodic cleanup encountered error: %s", e)
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=60.0)
            except TimeoutError:
                pass
    finally:
        logger.info("Shutting down standalone worker...")
        await worker.stop(timeout_seconds=5.0)
        logger.info("Standalone worker shutdown complete.")


if __name__ == "__main__":
    asyncio.run(run_standalone_worker())
