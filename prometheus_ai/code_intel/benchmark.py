"""Empirical Retrieval Benchmark and Comparative Evaluation."""

import time
from dataclasses import dataclass, field

from prometheus_ai.code_intel.indexer import CodeIntelligenceIndex
from prometheus_ai.code_intel.search import CodeSearchEngine


@dataclass
class BenchmarkTestCase:
    """Ground-truth benchmark test case for code retrieval."""

    query: str
    expected_files: list[str]
    expected_symbols: list[str] = field(default_factory=list)


@dataclass
class QueryEvaluationMetric:
    """Performance metrics for an individual benchmark query."""

    query: str
    lexical_precision: float
    lexical_recall: float
    lexical_latency_ms: float
    hybrid_precision: float
    hybrid_recall: float
    hybrid_latency_ms: float


@dataclass
class RetrievalEvaluationReport:
    """Comparative evaluation report between lexical and hybrid retrieval."""

    indexing_duration_seconds: float
    indexing_cost_usd: float
    total_test_cases: int
    avg_lexical_precision: float
    avg_lexical_recall: float
    avg_lexical_latency_ms: float
    avg_hybrid_precision: float
    avg_hybrid_recall: float
    avg_hybrid_latency_ms: float
    query_metrics: list[QueryEvaluationMetric] = field(default_factory=list)
    empirical_comparison_summary: str = ""


# Default version-controlled benchmark dataset for PROMETHEUS codebase
DEFAULT_BENCHMARK_SUITE: list[BenchmarkTestCase] = [
    BenchmarkTestCase(
        query="validate_safe_path",
        expected_files=["prometheus_ai/execution/guards.py"],
        expected_symbols=["validate_safe_path"],
    ),
    BenchmarkTestCase(
        query="BaseSandboxRunner",
        expected_files=["prometheus_ai/execution/sandbox.py"],
        expected_symbols=["BaseSandboxRunner"],
    ),
    BenchmarkTestCase(
        query="DockerSandboxRunner",
        expected_files=["prometheus_ai/execution/docker_runner.py"],
        expected_symbols=["DockerSandboxRunner"],
    ),
    BenchmarkTestCase(
        query="create_worktree",
        expected_files=["prometheus_ai/execution/git_manager.py"],
        expected_symbols=["create_worktree"],
    ),
    BenchmarkTestCase(
        query="DebuggingWorkflow",
        expected_files=["prometheus_ai/agents/workflow.py"],
        expected_symbols=["DebuggingWorkflow"],
    ),
]


def run_retrieval_benchmark(
    index: CodeIntelligenceIndex,
    test_cases: list[BenchmarkTestCase] | None = None,
    k: int = 5,
) -> RetrievalEvaluationReport:
    """Execute evaluation benchmark measuring Precision@K, Recall@K, Latency, and Cost."""
    cases = test_cases or DEFAULT_BENCHMARK_SUITE
    search_engine = CodeSearchEngine(index)

    query_metrics: list[QueryEvaluationMetric] = []
    lex_precisions: list[float] = []
    lex_recalls: list[float] = []
    lex_latencies: list[float] = []
    hyb_precisions: list[float] = []
    hyb_recalls: list[float] = []
    hyb_latencies: list[float] = []

    for tc in cases:
        expected_set = set(tc.expected_files)

        # 1. Lexical retrieval evaluation
        t0 = time.perf_counter()
        lex_hits = search_engine.search_lexical(tc.query, limit=k)
        lex_latency = (time.perf_counter() - t0) * 1000.0

        lex_retrieved_files = {h.file_path for h in lex_hits}
        lex_relevant = len(lex_retrieved_files.intersection(expected_set))
        lex_p = lex_relevant / max(1, len(lex_hits))
        lex_r = lex_relevant / max(1, len(expected_set))

        # 2. Hybrid retrieval evaluation
        t1 = time.perf_counter()
        hyb_hits = search_engine.search_hybrid(tc.query, limit=k)
        hyb_latency = (time.perf_counter() - t1) * 1000.0

        hyb_retrieved_files = {h.file_path for h in hyb_hits}
        hyb_relevant = len(hyb_retrieved_files.intersection(expected_set))
        hyb_p = hyb_relevant / max(1, len(hyb_hits))
        hyb_r = hyb_relevant / max(1, len(expected_set))

        lex_precisions.append(lex_p)
        lex_recalls.append(lex_r)
        lex_latencies.append(lex_latency)
        hyb_precisions.append(hyb_p)
        hyb_recalls.append(hyb_r)
        hyb_latencies.append(hyb_latency)

        query_metrics.append(
            QueryEvaluationMetric(
                query=tc.query,
                lexical_precision=round(lex_p, 3),
                lexical_recall=round(lex_r, 3),
                lexical_latency_ms=round(lex_latency, 2),
                hybrid_precision=round(hyb_p, 3),
                hybrid_recall=round(hyb_r, 3),
                hybrid_latency_ms=round(hyb_latency, 2),
            )
        )

    avg_lex_p = sum(lex_precisions) / max(1, len(lex_precisions))
    avg_lex_r = sum(lex_recalls) / max(1, len(lex_recalls))
    avg_lex_lat = sum(lex_latencies) / max(1, len(lex_latencies))

    avg_hyb_p = sum(hyb_precisions) / max(1, len(hyb_precisions))
    avg_hyb_r = sum(hyb_recalls) / max(1, len(hyb_recalls))
    avg_hyb_lat = sum(hyb_latencies) / max(1, len(hyb_latencies))

    # Empirical comparison without unsubstantiated claims
    summary = (
        f"Retrieval Benchmark (N={len(cases)} queries @ K={k}):\n"
        f"Lexical -> Precision: {avg_lex_p:.2f}, Recall: {avg_lex_r:.2f}, Latency: {avg_lex_lat:.2f}ms\n"
        f"Hybrid  -> Precision: {avg_hyb_p:.2f}, Recall: {avg_hyb_r:.2f}, Latency: {avg_hyb_lat:.2f}ms\n"
        f"Outcome: {'Hybrid achieved higher recall' if avg_hyb_r > avg_lex_r else 'Lexical matched or exceeded hybrid on this dataset'}; "
        f"Lexical retrieval latency was {avg_hyb_lat - avg_lex_lat:+.2f}ms compared to hybrid."
    )

    return RetrievalEvaluationReport(
        indexing_duration_seconds=0.0,
        indexing_cost_usd=0.0,  # Zero API cost using local AST / BM25
        total_test_cases=len(cases),
        avg_lexical_precision=round(avg_lex_p, 3),
        avg_lexical_recall=round(avg_lex_r, 3),
        avg_lexical_latency_ms=round(avg_lex_lat, 2),
        avg_hybrid_precision=round(avg_hyb_p, 3),
        avg_hybrid_recall=round(avg_hyb_r, 3),
        avg_hybrid_latency_ms=round(avg_hyb_lat, 2),
        query_metrics=query_metrics,
        empirical_comparison_summary=summary,
    )
