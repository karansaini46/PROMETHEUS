"""Integration tests for experiments and evaluations endpoints."""

from uuid import uuid4

import pytest
from httpx import AsyncClient


@pytest.mark.integration
async def test_experiments_and_evaluations_endpoints(async_client: AsyncClient) -> None:
    """Test experiment creation, result listing, and evaluation run inspection."""
    unique_exp_name = f"eval-study-{uuid4().hex[:8]}"
    exp_payload = {
        "name": unique_exp_name,
        "description": "Comparative study between AST parser and ripgrep search",
        "hypothesis": "AST parsing provides higher precision in identifying target functions",
        "parameters": {"depth": 3, "timeout": 60},
        "is_active": True,
    }

    create_res = await async_client.post("/api/v1/experiments", json=exp_payload)
    assert create_res.status_code == 201
    exp_data = create_res.json()
    assert exp_data["name"] == unique_exp_name
    exp_id = exp_data["id"]

    # List experiments
    list_res = await async_client.get("/api/v1/experiments")
    assert list_res.status_code == 200
    exps = list_res.json()
    assert any(e["id"] == exp_id for e in exps)

    # List results for this experiment (currently empty list, but 200 OK)
    results_res = await async_client.get(f"/api/v1/experiments/{exp_id}/results")
    assert results_res.status_code == 200
    assert isinstance(results_res.json(), list)

    # List all evaluation results
    eval_results_res = await async_client.get("/api/v1/evaluations/results")
    assert eval_results_res.status_code == 200
    assert isinstance(eval_results_res.json(), list)

    # List evaluation runs
    eval_runs_res = await async_client.get("/api/v1/evaluations/runs")
    assert eval_runs_res.status_code == 200
    assert isinstance(eval_runs_res.json(), list)
