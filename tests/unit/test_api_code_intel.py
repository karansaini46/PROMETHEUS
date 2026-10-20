"""Unit tests for Code Intelligence API routes."""

import subprocess
import tempfile
from pathlib import Path

import pytest
from httpx import AsyncClient


def _init_api_test_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-b", "main"], cwd=path, check=True, capture_output=True)
    (path / "app.py").write_text("def run_app():\n    return 'running'\n")
    subprocess.run(["git", "add", "."], cwd=path, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.name=T", "-c", "user.email=t@e.com", "commit", "-m", "init"],
        cwd=path,
        check=True,
        capture_output=True,
    )


@pytest.mark.unit
async def test_code_intel_api_lifecycle(async_client: AsyncClient) -> None:
    """Test indexing, search, symbol lookup, and impact endpoints."""
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_dir = Path(temp_dir)
        _init_api_test_repo(repo_dir)

        # 1. Trigger indexing
        index_res = await async_client.post(
            "/api/v1/code-intel/index",
            json={"repo_path": str(repo_dir), "incremental": True},
        )
        assert index_res.status_code == 200
        idx_data = index_res.json()
        assert idx_data["status"]["state"] == "completed"
        assert idx_data["status"]["files_indexed"] >= 1

        # 2. Get status
        status_res = await async_client.get(
            "/api/v1/code-intel/status",
            params={"repo_path": str(repo_dir)},
        )
        assert status_res.status_code == 200
        st_data = status_res.json()
        assert st_data["status"]["state"] == "completed"
        assert st_data["total_symbols_indexed"] >= 1

        # 3. Search code
        search_res = await async_client.get(
            "/api/v1/code-intel/search",
            params={"repo_path": str(repo_dir), "query": "run_app", "mode": "hybrid"},
        )
        assert search_res.status_code == 200
        s_data = search_res.json()
        assert s_data["count"] >= 1
        assert s_data["results"][0]["file_path"] == "app.py"

        # 4. Lookup symbols
        sym_res = await async_client.get(
            "/api/v1/code-intel/symbols",
            params={"repo_path": str(repo_dir), "name": "run_app"},
        )
        assert sym_res.status_code == 200
        sym_data = sym_res.json()
        assert len(sym_data["definitions"]) >= 1
        assert sym_data["definitions"][0]["symbol_name"] == "run_app"

        # 5. Analyze impact
        impact_res = await async_client.get(
            "/api/v1/code-intel/impact",
            params={"repo_path": str(repo_dir), "files": ["app.py"]},
        )
        assert impact_res.status_code == 200
        imp_data = impact_res.json()
        assert "run_app" in imp_data["directly_affected_symbols"]
        assert imp_data["risk_level"] in ["low", "medium", "high"]
