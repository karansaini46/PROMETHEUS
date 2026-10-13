"""Unit tests for the Learning Experiment evaluating agent with vs without memory."""

from collections.abc import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from prometheus_ai.learning.memory_experiment import (
    ExperimentTask,
    MemoryExperimentRunner,
)
from prometheus_ai.memory.manager import MemoryManager


@pytest.fixture
def memory_manager(test_db_session: AsyncSession) -> MemoryManager:
    """Fixture providing a MemoryManager wired to the isolated test database session."""

    async def _session_factory() -> AsyncGenerator[AsyncSession, None]:
        yield test_db_session

    return MemoryManager(session_factory=_session_factory, enable_vector_search=True)


@pytest.mark.unit
async def test_memory_experiment_comparison(memory_manager: MemoryManager) -> None:
    """Verify comparative evaluation comparing Agent without memory vs Agent with retrieved memory."""
    runner = MemoryExperimentRunner(
        memory_manager=memory_manager,
        agent_core_instructions="Standard instructions: Never hallucinate, use allowlisted tools.",
    )

    # 1. Tuning tasks (used exclusively to build experience)
    tuning_tasks = [
        ExperimentTask(
            task_id="tune-01",
            issue_description="FastAPI lifespan startup failing due to telemetry misconfiguration",
            expected_patch="diff --git a/main.py...",
            repo_path="/repos/sample",
            project_id="proj-bench",
            difficulty="medium",
        ),
        ExperimentTask(
            task_id="tune-02",
            issue_description="AsyncPG connection pool exhausted under high concurrent request volume",
            expected_patch="diff --git a/db.py...",
            repo_path="/repos/sample",
            project_id="proj-bench",
            difficulty="hard",
        ),
    ]

    # 2. Held-out evaluation tasks (kept strictly separate from tuning data)
    held_out_tasks = [
        ExperimentTask(
            task_id="eval-01",
            issue_description="FastAPI lifespan startup shutdown exception in test mode",
            expected_patch="diff --git a/main.py...",
            repo_path="/repos/sample",
            project_id="proj-bench",
            difficulty="medium",
        ),
        ExperimentTask(
            task_id="eval-02",
            issue_description="AsyncPG connection timeout when running alembic migrations",
            expected_patch="diff --git a/db.py...",
            repo_path="/repos/sample",
            project_id="proj-bench",
            difficulty="hard",
        ),
    ]

    # Run the comparative experiment
    report = await runner.run_experiment(
        tuning_tasks=tuning_tasks,
        held_out_tasks=held_out_tasks,
    )

    # Validate report structure and tracking
    assert report.tuning_task_count == 2
    assert report.held_out_task_count == 2
    assert report.condition_a_baseline.total_tasks == 2
    assert report.condition_b_memory.total_tasks == 2

    # Check metrics tracked
    assert report.condition_a_baseline.total_cost_usd > 0
    assert report.condition_b_memory.total_cost_usd > 0
    assert report.condition_a_baseline.avg_latency_seconds > 0
    assert report.condition_b_memory.avg_latency_seconds > 0
    assert report.retrieval_error_count == 0

    # Invariant: Core instructions must remain intact without modification
    assert report.instructions_unmodified_verified is True

    # Validate conclusion format: demonstrates whether memory improves benchmark or is inconclusive
    assert "Memory" in report.conclusion or "INCONCLUSIVE" in report.conclusion
    assert len(report.summary_text) > 50

    # Under this task distribution, memory should improve the resolution on the hard task
    assert report.condition_b_memory.success_rate >= report.condition_a_baseline.success_rate


@pytest.mark.unit
async def test_memory_experiment_inconclusive_scenario(memory_manager: MemoryManager) -> None:
    """Verify that when tasks yield identical success across conditions, it documents INCONCLUSIVE."""
    runner = MemoryExperimentRunner(
        memory_manager=memory_manager,
    )

    # Easy tasks where both conditions resolve 100% of tasks
    tuning_tasks = [
        ExperimentTask(
            task_id="tune-easy-1",
            issue_description="Fix typo in README header",
            expected_patch="diff...",
            repo_path="/repos/sample",
            project_id="proj-inconclusive",
            difficulty="easy",
        )
    ]
    held_out_tasks = [
        ExperimentTask(
            task_id="eval-easy-1",
            issue_description="Fix typo in CONTRIBUTING header",
            expected_patch="diff...",
            repo_path="/repos/sample",
            project_id="proj-inconclusive",
            difficulty="easy",
        )
    ]

    report = await runner.run_experiment(
        tuning_tasks=tuning_tasks,
        held_out_tasks=held_out_tasks,
    )

    # Both conditions resolve the easy task (delta == 0)
    assert report.delta_success_rate == 0.0
    assert "INCONCLUSIVE" in report.conclusion
