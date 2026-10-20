"""Comprehensive unit tests for the PROMETHEUS Code Intelligence subsystem."""

import os
import subprocess
import tempfile
from pathlib import Path

import pytest

from prometheus_ai.code_intel.analysis import CodeAnalyzer
from prometheus_ai.code_intel.benchmark import (
    BenchmarkTestCase,
    run_retrieval_benchmark,
)
from prometheus_ai.code_intel.indexer import CodeIntelligenceIndex
from prometheus_ai.code_intel.models import IndexState, SymbolKind
from prometheus_ai.code_intel.parser import (
    PythonAstAdapter,
)
from prometheus_ai.code_intel.search import CodeSearchEngine


def _init_sample_repository(path: Path) -> None:
    """Helper to initialize a multi-module repository with functions, classes, and tests."""
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "GIT_AUTHOR_NAME": "Intel Tester",
        "GIT_AUTHOR_EMAIL": "inteltester@example.com",
        "GIT_COMMITTER_NAME": "Intel Tester",
        "GIT_COMMITTER_EMAIL": "inteltester@example.com",
    }
    subprocess.run(
        ["git", "init", "-b", "main"], cwd=path, check=True, capture_output=True, env=env
    )

    # 1. Math module
    math_code = (
        '"""Mathematical utilities module."""\n\n'
        "class Calculator:\n"
        '    """High-precision arithmetic engine."""\n\n'
        "    def add(self, a: int, b: int) -> int:\n"
        '        """Add two integers."""\n'
        "        return a + b\n\n"
        "    def multiply(self, a: int, b: int) -> int:\n"
        '        """Multiply two integers."""\n'
        "        return a * b\n\n"
        "def compute_average(values: list[float]) -> float:\n"
        '    """Compute arithmetic mean of a list."""\n'
        "    return sum(values) / len(values)\n"
    )
    (path / "calculator.py").write_text(math_code)

    # 2. Stats module importing calculator
    stats_code = (
        "import math\n"
        "from calculator import Calculator, compute_average\n\n"
        "def compute_variance(values: list[float]) -> float:\n"
        '    """Compute sample variance using compute_average."""\n'
        "    avg = compute_average(values)\n"
        "    calc = Calculator()\n"
        "    return sum(calc.multiply(int(x - avg), int(x - avg)) for x in values)\n"
    )
    (path / "stats.py").write_text(stats_code)

    # 3. Test module
    test_code = (
        "import pytest\n"
        "from calculator import Calculator\n"
        "from stats import compute_variance\n\n"
        "def test_calculator_add():\n"
        "    calc = Calculator()\n"
        "    assert calc.add(2, 3) == 5\n"
    )
    (path / "test_calculator.py").write_text(test_code)

    # 4. Text documentation
    (path / "README.md").write_text("# Math and Stats Engine\nDocumentation for data engine.\n")

    subprocess.run(["git", "add", "."], cwd=path, check=True, capture_output=True, env=env)
    subprocess.run(
        ["git", "commit", "-m", "Initial code commit"],
        cwd=path,
        check=True,
        capture_output=True,
        env=env,
    )


@pytest.mark.unit
def test_ast_symbol_extraction() -> None:
    """Ensure Python AST adapter correctly extracts classes, methods, docstrings, and imports."""
    adapter = PythonAstAdapter()
    sample_code = (
        "import sys\n"
        "from os import path\n\n"
        "class Engine:\n"
        '    """Engine docstring."""\n'
        "    def start(self, mode: str):\n"
        '        """Start the engine."""\n'
        "        return True\n\n"
        "async def run_pipeline():\n"
        "    eng = Engine()\n"
        "    eng.start('turbo')\n"
    )

    symbols, imports, refs, _chunks, parse_err = adapter.parse_source("engine.py", sample_code)
    assert parse_err is None

    # Verify Symbols
    sym_names = {s.name: s for s in symbols}
    assert "Engine" in sym_names
    assert sym_names["Engine"].kind == SymbolKind.CLASS
    assert sym_names["Engine"].docstring == "Engine docstring."

    assert "start" in sym_names
    assert sym_names["start"].kind == SymbolKind.METHOD
    assert sym_names["start"].parent_name == "Engine"
    assert sym_names["start"].signature is not None
    assert "(self, mode)" in sym_names["start"].signature

    assert "run_pipeline" in sym_names
    assert sym_names["run_pipeline"].kind == SymbolKind.FUNCTION

    # Verify Imports
    imp_mods = {i.source_module for i in imports}
    assert "sys" in imp_mods
    assert "os" in imp_mods

    # Verify Call References
    assert "start" in refs or "Engine" in refs


@pytest.mark.unit
def test_repository_indexing_and_incremental_updates() -> None:
    """Ensure repository indexing tracks content hashes, deleted files, and incremental skips."""
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_dir = Path(temp_dir) / "repo"
        repo_dir.mkdir()
        _init_sample_repository(repo_dir)

        index = CodeIntelligenceIndex(repo_dir)
        status = index.build_index(incremental=True)

        assert status.state == IndexState.COMPLETED
        assert status.files_indexed == 4
        assert len(index.file_indices) == 4
        assert "calculator.py" in index.file_indices
        assert index.is_stale() is False

        # Incremental reindex without changes
        status2 = index.build_index(incremental=True)
        assert status2.files_indexed == 4

        # Add a new file and delete an existing file
        (repo_dir / "new_module.py").write_text("def new_func(): pass\n")
        (repo_dir / "README.md").unlink()
        subprocess.run(["git", "add", "."], cwd=repo_dir, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Add new and remove readme"], cwd=repo_dir, check=True
        )

        index.build_index(incremental=True)
        assert "new_module.py" in index.file_indices
        assert "README.md" not in index.file_indices  # Deleted file purged


@pytest.mark.unit
def test_fault_isolation_with_malformed_files() -> None:
    """Ensure syntax errors in malformed files do not abort or corrupt indexing for valid files."""
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_dir = Path(temp_dir) / "repo"
        repo_dir.mkdir()
        _init_sample_repository(repo_dir)

        # Plant a deliberately malformed file
        (repo_dir / "broken.py").write_text("def broken_syntax(::: invalid python {{{\n")
        subprocess.run(["git", "add", "."], cwd=repo_dir, check=True)
        subprocess.run(["git", "commit", "-m", "Add broken file"], cwd=repo_dir, check=True)

        index = CodeIntelligenceIndex(repo_dir)
        status = index.build_index()

        assert status.state == IndexState.COMPLETED
        assert len(status.errors) >= 1
        assert any("broken.py" in err.get("file", "") for err in status.errors)

        # Valid files must remain cleanly indexed and uncorrupted
        assert "calculator.py" in index.file_indices
        assert len(index.file_indices["calculator.py"].symbols) >= 3


@pytest.mark.unit
def test_dependency_and_impact_analysis() -> None:
    """Ensure dependency graph, test discovery, and impact analysis function accurately."""
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_dir = Path(temp_dir) / "repo"
        repo_dir.mkdir()
        _init_sample_repository(repo_dir)

        index = CodeIntelligenceIndex(repo_dir)
        index.build_index()
        analyzer = CodeAnalyzer(index)

        # 1. Dependency Analysis: stats.py imports calculator.py
        stats_deps = analyzer.get_dependencies("stats.py")
        assert "calculator.py" in stats_deps

        # Dependents: calculator.py is imported by stats.py and test_calculator.py
        calc_dependents = analyzer.get_dependents("calculator.py")
        assert "stats.py" in calc_dependents
        assert "test_calculator.py" in calc_dependents

        # 2. Test Discovery
        tests_for_calc = analyzer.discover_tests_for_file("calculator.py")
        assert "test_calculator.py" in tests_for_calc

        # 3. Change Impact Analysis
        impact = analyzer.analyze_change_impact(["calculator.py"])
        assert "Calculator" in impact.directly_affected_symbols
        assert "stats.py" in impact.dependent_files
        assert "test_calculator.py" in impact.suggested_test_files
        assert impact.risk_level in ("medium", "high")


@pytest.mark.unit
def test_code_search_lexical_semantic_hybrid() -> None:
    """Ensure lexical, semantic, and hybrid search return ranked results with snippets."""
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_dir = Path(temp_dir) / "repo"
        repo_dir.mkdir()
        _init_sample_repository(repo_dir)

        index = CodeIntelligenceIndex(repo_dir)
        index.build_index()
        search_engine = CodeSearchEngine(index)

        # 1. Lexical search for exact symbol
        lex_results = search_engine.search_lexical("compute_average", limit=5)
        assert len(lex_results) >= 1
        assert any(r.file_path == "calculator.py" for r in lex_results)
        assert "compute_average" in lex_results[0].snippet

        # 2. Semantic search for conceptual query
        sem_results = search_engine.search_semantic("arithmetic mean calculator", limit=5)
        assert len(sem_results) >= 1

        # 3. Hybrid search
        hybrid_results = search_engine.search_hybrid("Calculator multiply", limit=5)
        assert len(hybrid_results) >= 1
        assert hybrid_results[0].match_type == "hybrid"
        assert hybrid_results[0].file_path in ("calculator.py", "stats.py")


@pytest.mark.unit
def test_retrieval_benchmark_and_empirical_comparison() -> None:
    """Ensure retrieval benchmark measures precision, recall, and provides empirical comparison."""
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_dir = Path(temp_dir) / "repo"
        repo_dir.mkdir()
        _init_sample_repository(repo_dir)

        index = CodeIntelligenceIndex(repo_dir)
        index.build_index()

        test_suite = [
            BenchmarkTestCase(
                query="compute_average",
                expected_files=["calculator.py"],
                expected_symbols=["compute_average"],
            ),
            BenchmarkTestCase(
                query="compute_variance",
                expected_files=["stats.py"],
                expected_symbols=["compute_variance"],
            ),
        ]

        report = run_retrieval_benchmark(index, test_cases=test_suite, k=3)
        assert report.total_test_cases == 2
        assert report.avg_lexical_recall > 0.0
        assert report.avg_hybrid_recall > 0.0
        assert report.avg_lexical_latency_ms >= 0.0
        assert len(report.empirical_comparison_summary) > 0
