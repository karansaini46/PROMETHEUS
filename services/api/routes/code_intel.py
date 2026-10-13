"""Code Intelligence API Routes for repository indexing, search, and impact analysis."""

from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from prometheus_ai.code_intel.analysis import CodeAnalyzer
from prometheus_ai.code_intel.indexer import CodeIntelligenceIndex
from prometheus_ai.code_intel.search import CodeSearchEngine
from services.api.security import AuthenticatedClient, verify_api_key

router = APIRouter(prefix="/code-intel", tags=["Code Intelligence"])

# In-memory registry of active repository indexes
_active_indices: dict[str, CodeIntelligenceIndex] = {}


def get_or_create_index(repo_path: str) -> CodeIntelligenceIndex:
    """Retrieve or instantiate an index for a canonical repository path."""
    resolved = str(Path(repo_path).resolve())
    if resolved not in _active_indices:
        _active_indices[resolved] = CodeIntelligenceIndex(resolved)
    return _active_indices[resolved]


class IndexRequest(BaseModel):
    """Trigger indexing request payload."""

    repo_path: str = Field(description="Local repository path to index")
    incremental: bool = Field(default=True, description="Enable incremental hash-based indexing")


@router.post("/index")
async def trigger_indexing(
    payload: IndexRequest,
    client: Annotated[AuthenticatedClient, Depends(verify_api_key)],
) -> dict[str, Any]:
    """Trigger repository indexing and return progress status."""
    index = get_or_create_index(payload.repo_path)
    status = index.build_index(incremental=payload.incremental)
    return {
        "status": status.to_dict(),
        "is_stale": index.is_stale(),
    }


@router.get("/status")
async def get_index_status(
    repo_path: Annotated[str, Query(description="Repository path to check")],
    client: Annotated[AuthenticatedClient | None, Depends(verify_api_key)] = None,
) -> dict[str, Any]:
    """Inspect current indexing progress, file counts, and failure errors."""
    index = get_or_create_index(repo_path)
    return {
        "status": index.status.to_dict(),
        "is_stale": index.is_stale(),
        "total_symbols_indexed": sum(len(f.symbols) for f in index.file_indices.values()),
    }


@router.get("/search")
async def search_code(
    repo_path: Annotated[str, Query(description="Repository path")],
    query: Annotated[str, Query(description="Search query string")],
    mode: Annotated[str, Query(description="Search mode: lexical, semantic, hybrid")] = "hybrid",
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
    client: Annotated[AuthenticatedClient | None, Depends(verify_api_key)] = None,
) -> dict[str, Any]:
    """Perform lexical, semantic, or hybrid code search across the index."""
    index = get_or_create_index(repo_path)
    search_engine = CodeSearchEngine(index)

    if mode == "lexical":
        results = search_engine.search_lexical(query, limit=limit)
    elif mode == "semantic":
        results = search_engine.search_semantic(query, limit=limit)
    else:
        results = search_engine.search_hybrid(query, limit=limit)

    return {
        "query": query,
        "mode": mode,
        "is_stale": index.is_stale(),
        "count": len(results),
        "results": [
            {
                "file_path": r.file_path,
                "start_line": r.start_line,
                "end_line": r.end_line,
                "snippet": r.snippet,
                "score": r.score,
                "match_type": r.match_type,
                "symbol_name": r.symbol_name,
            }
            for r in results
        ],
    }


@router.get("/symbols")
async def lookup_symbols(
    repo_path: Annotated[str, Query(description="Repository path")],
    name: Annotated[str, Query(description="Symbol name to look up")],
    client: Annotated[AuthenticatedClient | None, Depends(verify_api_key)] = None,
) -> dict[str, Any]:
    """Look up definitions and references for a symbol."""
    index = get_or_create_index(repo_path)
    analyzer = CodeAnalyzer(index)

    definitions = analyzer.find_definition(name)
    references = analyzer.find_references(name)

    return {
        "symbol_name": name,
        "definitions": definitions,
        "references": references,
    }


@router.get("/impact")
async def analyze_impact(
    repo_path: Annotated[str, Query(description="Repository path")],
    files: Annotated[list[str], Query(description="List of modified files")],
    client: Annotated[AuthenticatedClient | None, Depends(verify_api_key)] = None,
) -> dict[str, Any]:
    """Analyze cascading impact of modified files on dependent modules and tests."""
    index = get_or_create_index(repo_path)
    analyzer = CodeAnalyzer(index)

    impact = analyzer.analyze_change_impact(files)
    return {
        "modified_files": impact.modified_files,
        "directly_affected_symbols": impact.directly_affected_symbols,
        "dependent_files": impact.dependent_files,
        "suggested_test_files": impact.suggested_test_files,
        "risk_level": impact.risk_level,
    }
