"""Integration tests for model configurations API endpoints."""

from uuid import uuid4

import pytest
from httpx import AsyncClient


@pytest.mark.integration
async def test_create_and_list_model_configurations(async_client: AsyncClient) -> None:
    """Test model configuration registration, retrieval, and conflict checking."""
    unique_name = f"deepseek-coder-{uuid4().hex[:8]}"
    model_payload = {
        "name": unique_name,
        "provider": "deepseek",
        "model_name": "deepseek-coder:33b",
        "api_base_url": "https://api.deepseek.com/v1",
        "temperature": 0.1,
        "max_tokens": 8192,
        "context_window": 64000,
        "cost_per_million_input_tokens": 1.0,
        "cost_per_million_output_tokens": 2.0,
        "is_active": True,
        "settings": {"top_p": 0.95},
    }

    create_res = await async_client.post("/api/v1/models", json=model_payload)
    assert create_res.status_code == 201
    created_model = create_res.json()
    assert created_model["name"] == unique_name
    assert created_model["provider"] == "deepseek"
    assert created_model["context_window"] == 64000

    model_id = created_model["id"]

    # Fetch by ID or name
    get_res = await async_client.get(f"/api/v1/models/{model_id}")
    assert get_res.status_code == 200
    assert get_res.json()["name"] == unique_name

    # List models includes the new model
    list_res = await async_client.get("/api/v1/models")
    assert list_res.status_code == 200
    models = list_res.json()
    assert any(m["id"] == model_id for m in models)

    # Creating duplicate model name must return 409 Conflict
    dup_res = await async_client.post("/api/v1/models", json=model_payload)
    assert dup_res.status_code == 409
