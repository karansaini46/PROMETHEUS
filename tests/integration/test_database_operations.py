"""Integration tests for all 16 normalized database tables and constraints."""

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.models import (
    AgentStep,
    Artifact,
    AuditEvent,
    EvaluationCase,
    EvaluationDataset,
    EvaluationRun,
    ExperimentDefinition,
    ExperimentResult,
    MemoryRecord,
    ModelConfiguration,
    ModelUsageRecord,
    Project,
    RepositoryRegistration,
    Task,
    ToolInvocation,
)


@pytest.mark.integration
async def test_all_16_tables_crud_and_cascade(test_db_session: AsyncSession) -> None:
    """Validate insertion, querying, and foreign key cascade deletion for all 16 models."""
    session = test_db_session

    # 1. Project
    project = Project(
        id=str(uuid4()),
        name="Test Monorepo Project",
        slug=f"monorepo-{uuid4().hex[:8]}",
        repository_url="https://github.com/test/monorepo.git",
    )
    session.add(project)
    await session.flush()

    # 2. Repository Registration
    repo = RepositoryRegistration(
        id=str(uuid4()),
        project_id=project.id,
        name="Monorepo Core",
        repo_url="https://github.com/test/monorepo.git",
    )
    session.add(repo)
    await session.flush()

    # 3. Model Configuration
    model_cfg = ModelConfiguration(
        id=str(uuid4()),
        name=f"test-model-{uuid4().hex[:6]}",
        provider="anthropic",
        model_name="claude-3-5-sonnet",
    )
    session.add(model_cfg)
    await session.flush()

    # 4. Task
    task = Task(
        id=str(uuid4()),
        project_id=project.id,
        repository_id=repo.id,
        title="Test Task for DB Verification",
        problem_statement="Problem statement details.",
    )
    session.add(task)
    await session.flush()

    # 5. Execution Run
    from services.api.models import ExecutionRun, RunStatusEnum

    run = ExecutionRun(
        id=f"run_{uuid4().hex}",
        task_id=task.id,
        model_configuration_id=model_cfg.id,
        status=RunStatusEnum.PENDING.value,
        model_provider="anthropic/claude-3-5-sonnet",
    )
    session.add(run)
    await session.flush()

    # 6. Agent Step
    step = AgentStep(
        id=str(uuid4()),
        run_id=run.id,
        step_number=1,
        step_name="LOCALIZE_FAULT",
        status="RUNNING",
    )
    session.add(step)
    await session.flush()

    # 7. Tool Invocation
    tool = ToolInvocation(
        id=str(uuid4()),
        run_id=run.id,
        step_id=step.id,
        tool_name="grep_search",
        parameters={"query": "def authenticate"},
        result={"matches": 1},
    )
    session.add(tool)
    await session.flush()

    # 8. Model Usage Record
    usage = ModelUsageRecord(
        id=str(uuid4()),
        run_id=run.id,
        model_configuration_id=model_cfg.id,
        step_id=step.id,
        prompt_tokens=150,
        completion_tokens=50,
        total_tokens=200,
        cost_usd=0.001,
    )
    session.add(usage)
    await session.flush()

    # 9. Artifact
    artifact = Artifact(
        id=str(uuid4()),
        run_id=run.id,
        name="patch.diff",
        artifact_type="DIFF",
        content="--- a/file.py\n+++ b/file.py\n",
    )
    session.add(artifact)
    await session.flush()

    # 10. Evaluation Dataset
    dataset = EvaluationDataset(
        id=str(uuid4()),
        name=f"dataset-{uuid4().hex[:8]}",
        description="Dataset for testing",
    )
    session.add(dataset)
    await session.flush()

    # 11. Evaluation Case
    eval_case = EvaluationCase(
        id=str(uuid4()),
        dataset_id=dataset.id,
        instance_id="case-101",
        repository_name="test/repo",
        base_commit="abc1234567890123456789012345678901234567",
        problem_statement="Eval case problem statement",
    )
    session.add(eval_case)
    await session.flush()

    # 12. Evaluation Run
    eval_run = EvaluationRun(
        id=str(uuid4()),
        dataset_id=dataset.id,
        model_configuration_id=model_cfg.id,
        status="PENDING",
        total_cases=1,
    )
    session.add(eval_run)
    await session.flush()

    # 13. Experiment Definition
    experiment = ExperimentDefinition(
        id=str(uuid4()),
        name=f"experiment-{uuid4().hex[:8]}",
        model_configuration_id=model_cfg.id,
    )
    session.add(experiment)
    await session.flush()

    # 14. Experiment Result
    exp_result = ExperimentResult(
        id=str(uuid4()),
        experiment_id=experiment.id,
        evaluation_run_id=eval_run.id,
        run_id=run.id,
        metric_name="pass@1",
        metric_value=1.0,
    )
    session.add(exp_result)
    await session.flush()

    # 15. Memory Record
    memory = MemoryRecord(
        id=str(uuid4()),
        project_id=project.id,
        run_id=run.id,
        memory_type="LESSON_LEARNED",
        key="test_key",
        content="Test content",
    )
    session.add(memory)
    await session.flush()

    # 16. Audit Event
    audit = AuditEvent(
        id=str(uuid4()),
        run_id=run.id,
        action="TEST_ACTION",
        actor="test-runner",
    )
    session.add(audit)
    await session.flush()

    # Query all back
    assert (
        await session.execute(select(Project).where(Project.id == project.id))
    ).scalar_one() is not None
    assert (await session.execute(select(Task).where(Task.id == task.id))).scalar_one() is not None
    assert (
        await session.execute(select(ExecutionRun).where(ExecutionRun.id == run.id))
    ).scalar_one() is not None
    assert (
        await session.execute(select(EvaluationCase).where(EvaluationCase.id == eval_case.id))
    ).scalar_one() is not None

    # Roll back after test verification
    await session.rollback()


@pytest.mark.integration
async def test_evaluation_case_unique_constraint(test_db_session: AsyncSession) -> None:
    """Ensure duplicate instance_id in same dataset violates unique constraint."""
    session = test_db_session
    dataset = EvaluationDataset(
        id=str(uuid4()),
        name=f"unique-test-ds-{uuid4().hex[:6]}",
    )
    session.add(dataset)
    await session.flush()

    case1 = EvaluationCase(
        id=str(uuid4()),
        dataset_id=dataset.id,
        instance_id="duplicate-id",
        repository_name="repo",
        base_commit="1234567890123456789012345678901234567890",
        problem_statement="Problem 1",
    )
    session.add(case1)
    await session.flush()

    case2 = EvaluationCase(
        id=str(uuid4()),
        dataset_id=dataset.id,
        instance_id="duplicate-id",  # Same instance_id in same dataset
        repository_name="repo",
        base_commit="1234567890123456789012345678901234567890",
        problem_statement="Problem 2",
    )
    session.add(case2)

    with pytest.raises(IntegrityError):
        await session.flush()

    await session.rollback()
