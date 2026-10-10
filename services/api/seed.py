"""Safe Development Seed Script for PROMETHEUS.

Populates initial projects, model configurations, tasks, and benchmark
definitions for local development. Does not insert fake production metrics.
Idempotent and safe to run multiple times.
"""

import asyncio
import logging
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.db import AsyncSessionLocal
from services.api.models import (
    AuditEvent,
    EvaluationCase,
    EvaluationDataset,
    ExperimentDefinition,
    MemoryRecord,
    ModelConfiguration,
    Project,
    RepositoryRegistration,
    Task,
    TaskPriorityEnum,
    TaskStatusEnum,
    TaskTypeEnum,
)

logger = logging.getLogger("prometheus.seed")


async def seed_database(db: AsyncSession) -> None:
    """Seed base development entities without fabricating fake metrics."""
    # 1. Default Project
    proj_slug = "prometheus-core"
    existing_proj = await db.execute(select(Project).where(Project.slug == proj_slug))
    project = existing_proj.scalar_one_or_none()

    if not project:
        project = Project(
            id=str(uuid4()),
            name="Prometheus Core Engineering Workspace",
            slug=proj_slug,
            description="Default workspace for autonomous debugging and benchmark verification.",
            repository_url="https://github.com/prometheus/sample-workspace.git",
            default_branch="main",
        )
        db.add(project)
        await db.flush()
        logger.info("Created development project: %s", project.name)

    # 2. Repository Registration
    repo_url = "https://github.com/prometheus/sample-workspace.git"
    existing_repo = await db.execute(
        select(RepositoryRegistration).where(
            RepositoryRegistration.project_id == project.id,
            RepositoryRegistration.repo_url == repo_url,
        )
    )
    repo = existing_repo.scalar_one_or_none()
    if not repo:
        repo = RepositoryRegistration(
            id=str(uuid4()),
            project_id=project.id,
            name="Sample Target Repository",
            repo_url=repo_url,
            default_branch="main",
            auth_type="NONE",
            is_active=True,
            settings={"language": "python", "test_runner": "pytest"},
        )
        db.add(repo)
        await db.flush()
        logger.info("Created repository registration: %s", repo.name)

    # 3. Model Configurations
    seed_models: list[dict[str, Any]] = [
        {
            "name": "claude-3-5-sonnet",
            "provider": "anthropic",
            "model_name": "claude-3-5-sonnet-20241022",
            "api_base_url": None,
            "temperature": 0.0,
            "max_tokens": 8192,
            "context_window": 200000,
            "cost_per_million_input_tokens": 3.0,
            "cost_per_million_output_tokens": 15.0,
        },
        {
            "name": "gpt-4o",
            "provider": "openai",
            "model_name": "gpt-4o-2024-08-06",
            "api_base_url": None,
            "temperature": 0.0,
            "max_tokens": 4096,
            "context_window": 128000,
            "cost_per_million_input_tokens": 2.5,
            "cost_per_million_output_tokens": 10.0,
        },
        {
            "name": "qwen2.5-coder-local",
            "provider": "local",
            "model_name": "qwen2.5-coder:7b",
            "api_base_url": "http://localhost:11434/v1",
            "temperature": 0.0,
            "max_tokens": 4096,
            "context_window": 32768,
            "cost_per_million_input_tokens": 0.0,
            "cost_per_million_output_tokens": 0.0,
        },
    ]

    for m in seed_models:
        existing_m = await db.execute(
            select(ModelConfiguration).where(ModelConfiguration.name == m["name"])
        )
        if not existing_m.scalar_one_or_none():
            config = ModelConfiguration(id=str(uuid4()), **m)
            db.add(config)
            logger.info("Registered model configuration: %s", m["name"])

    # 4. Baseline Software Engineering Tasks
    seed_tasks = [
        {
            "title": "Fix token expiration off-by-one verification boundary",
            "problem_statement": (
                "Tokens expiring exactly on the boundary second are rejected prematurely. "
                "The comparison in auth/tokens.py line 45 should use <= instead of <."
            ),
            "task_type": TaskTypeEnum.BUG_FIX.value,
            "priority": TaskPriorityEnum.HIGH.value,
            "base_commit": "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678",
            "reproduce_command": "pytest tests/test_tokens.py -k test_boundary_expiry",
        },
        {
            "title": "Implement exponential backoff retry for network timeouts",
            "problem_statement": (
                "Network calls to external model endpoints fail abruptly on transient HTTP 429 "
                "or socket timeouts. Add jittered exponential backoff with max 3 attempts."
            ),
            "task_type": TaskTypeEnum.FEATURE.value,
            "priority": TaskPriorityEnum.MEDIUM.value,
            "base_commit": "b2c3d4e5f60718293a4b5c6d7e8f9012345678a1",
            "reproduce_command": "pytest tests/test_retries.py",
        },
    ]

    for t_data in seed_tasks:
        existing_t = await db.execute(
            select(Task).where(Task.project_id == project.id, Task.title == t_data["title"])
        )
        if not existing_t.scalar_one_or_none():
            task = Task(
                id=str(uuid4()),
                project_id=project.id,
                repository_id=repo.id if repo else None,
                status=TaskStatusEnum.OPEN.value,
                **t_data,
            )
            db.add(task)
            logger.info("Registered task: %s", t_data["title"])

    # 5. Evaluation Dataset & Sample Case
    dataset_name = "swe-bench-lite-sample"
    existing_ds = await db.execute(
        select(EvaluationDataset).where(EvaluationDataset.name == dataset_name)
    )
    dataset = existing_ds.scalar_one_or_none()
    if not dataset:
        dataset = EvaluationDataset(
            id=str(uuid4()),
            name=dataset_name,
            description="Sample instances from SWE-bench Lite evaluation benchmark.",
            version="1.0.0",
            source_url="https://github.com/princeton-nlp/SWE-bench",
        )
        db.add(dataset)
        await db.flush()
        logger.info("Created evaluation dataset: %s", dataset_name)

        # Sample case
        sample_case = EvaluationCase(
            id=str(uuid4()),
            dataset_id=dataset.id,
            instance_id="sympy__sympy-18057",
            repository_name="sympy/sympy",
            base_commit="7e909062eb182e0df40a6b7d19c3b885ff71bb9b",
            problem_statement="Equality comparison with Symbol and un-evaluable expressions raises unexpected exception.",
        )
        db.add(sample_case)
        logger.info("Added evaluation case: sympy__sympy-18057")

    # 6. Baseline Experiment Definition
    exp_name = "baseline-fault-localization-study"
    existing_exp = await db.execute(
        select(ExperimentDefinition).where(ExperimentDefinition.name == exp_name)
    )
    if not existing_exp.scalar_one_or_none():
        experiment = ExperimentDefinition(
            id=str(uuid4()),
            name=exp_name,
            description="Investigate accuracy of Tree-sitter symbol graph versus lexical ripgrep.",
            hypothesis="Syntactic symbol linking reduces localized file candidates by 50%.",
            parameters={"max_iterations": 5, "enable_ast": True},
            is_active=True,
        )
        db.add(experiment)
        logger.info("Created experiment definition: %s", exp_name)

    # 7. Knowledge / Memory Record
    mem_key = "ast_traversal_best_practice"
    existing_mem = await db.execute(select(MemoryRecord).where(MemoryRecord.key == mem_key))
    if not existing_mem.scalar_one_or_none():
        mem = MemoryRecord(
            id=str(uuid4()),
            project_id=project.id,
            memory_type="CODE_PATTERN",
            key=mem_key,
            content="When analyzing Python syntax trees, inspect FunctionDef and ClassDef nodes before checking global variables.",
        )
        db.add(mem)
        logger.info("Added seed memory record: %s", mem_key)

    # 8. Audit Event
    audit = AuditEvent(
        id=str(uuid4()),
        action="DEVELOPMENT_DATABASE_SEEDED",
        actor="system",
        resource_type="Database",
        details={"environment": "development"},
    )
    db.add(audit)

    await db.commit()
    logger.info("Database seeding completed successfully.")


async def main() -> None:
    """CLI entrypoint for database seeding."""
    logging.basicConfig(level=logging.INFO)
    async with AsyncSessionLocal() as session:
        await seed_database(session)


if __name__ == "__main__":
    asyncio.run(main())
