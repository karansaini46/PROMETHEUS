"""Lexical, Semantic, and Hybrid Code Search Engine."""

import math
from collections import Counter

from prometheus_ai.code_intel.indexer import CodeIntelligenceIndex
from prometheus_ai.code_intel.models import CodeChunk, SearchResult
from prometheus_ai.code_intel.parser import tokenize_code


class CodeSearchEngine:
    """Multi-modal code retrieval combining lexical and semantic rankings."""

    def __init__(self, index: CodeIntelligenceIndex) -> None:
        self.index = index

    def _generate_snippet(
        self,
        content: str,
        match_line: int,
        start_line: int,
        context_radius: int = 2,
    ) -> str:
        """Extract a small, bounded evidence snippet around the match line."""
        lines = content.splitlines()
        offset = max(0, match_line - start_line)
        low = max(0, offset - context_radius)
        high = min(len(lines), offset + context_radius + 1)

        snippet_lines = []
        for idx in range(low, high):
            line_no = start_line + idx
            line_text = lines[idx]
            prefix = ">" if idx == offset else " "
            snippet_lines.append(f"{prefix} {line_no:4d} | {line_text}")

        return "\n".join(snippet_lines)

    def search_lexical(
        self,
        query: str,
        limit: int = 10,
    ) -> list[SearchResult]:
        """Perform exact keyword and substring matching across indexed code chunks."""
        if not query.strip():
            return []

        lower_query = query.lower()
        results: list[SearchResult] = []

        for rel_path, file_idx in self.index.file_indices.items():
            for chunk in file_idx.chunks:
                lower_content = chunk.content.lower()
                if lower_query in lower_content:
                    # Count exact occurrences
                    count = lower_content.count(lower_query)
                    score = min(1.0, 0.4 + (count * 0.05))
                    if chunk.symbol_name:
                        if chunk.symbol_name.lower() == lower_query:
                            score = min(1.0, score + 0.5)
                        elif lower_query in chunk.symbol_name.lower():
                            score = min(1.0, score + 0.2)
                    if lower_query in rel_path.lower():
                        score = min(1.0, score + 0.1)

                    # Identify match line
                    match_line = chunk.start_line
                    for idx, line in enumerate(chunk.content.splitlines()):
                        if lower_query in line.lower():
                            match_line = chunk.start_line + idx
                            break

                    snippet = self._generate_snippet(
                        content=chunk.content,
                        match_line=match_line,
                        start_line=chunk.start_line,
                    )

                    results.append(
                        SearchResult(
                            file_path=rel_path,
                            start_line=chunk.start_line,
                            end_line=chunk.end_line,
                            snippet=snippet,
                            score=score,
                            match_type="lexical",
                            symbol_name=chunk.symbol_name,
                        )
                    )

        # Sort descending by score
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:limit]

    def search_semantic(
        self,
        query: str,
        limit: int = 10,
    ) -> list[SearchResult]:
        """Perform tokenized frequency and BM25-style semantic retrieval.

        # ponytail: BM25 term-frequency scoring over normalized AST symbol tokens provides
        # robust semantic relevance without external neural network downloads or GPU overhead.
        # Upgrade path: Dense vector embeddings with pgvector / text-embedding-3-small.
        """
        query_tokens = tokenize_code(query)
        if not query_tokens:
            return []

        all_chunks: list[tuple[str, CodeChunk]] = []
        doc_frequencies: Counter[str] = Counter()

        for rel_path, file_idx in self.index.file_indices.items():
            for chunk in file_idx.chunks:
                all_chunks.append((rel_path, chunk))
                unique_tokens = set(chunk.tokens)
                for tok in unique_tokens:
                    doc_frequencies[tok] += 1

        total_docs = max(1, len(all_chunks))
        results: list[SearchResult] = []

        for rel_path, chunk in all_chunks:
            if not chunk.tokens:
                continue

            chunk_counter = Counter(chunk.tokens)
            chunk_len = len(chunk.tokens)
            score = 0.0

            for q_tok in query_tokens:
                tf = chunk_counter.get(q_tok, 0)
                if tf > 0:
                    df = doc_frequencies.get(q_tok, 1)
                    idf = math.log((total_docs - df + 0.5) / (df + 0.5) + 1.0)
                    # BM25 term weight
                    k1 = 1.5
                    b = 0.75
                    norm_tf = (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * (chunk_len / 40.0)))
                    score += idf * norm_tf

            if score > 0.05:
                snippet = self._generate_snippet(
                    content=chunk.content,
                    match_line=chunk.start_line,
                    start_line=chunk.start_line,
                )
                results.append(
                    SearchResult(
                        file_path=rel_path,
                        start_line=chunk.start_line,
                        end_line=chunk.end_line,
                        snippet=snippet,
                        score=score,
                        match_type="semantic",
                        symbol_name=chunk.symbol_name,
                    )
                )

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:limit]

    def search_hybrid(
        self,
        query: str,
        limit: int = 10,
    ) -> list[SearchResult]:
        """Combine lexical and semantic retrieval using Reciprocal Rank Fusion (RRF)."""
        lexical_hits = self.search_lexical(query, limit=limit * 2)
        semantic_hits = self.search_semantic(query, limit=limit * 2)

        # RRF formula: RRF_score(d) = sum(1.0 / (60 + rank_i))
        k_rrf = 60.0
        rrf_scores: dict[str, float] = {}
        chunk_map: dict[str, SearchResult] = {}

        for rank, hit in enumerate(lexical_hits, start=1):
            key = f"{hit.file_path}:{hit.start_line}:{hit.end_line}"
            rrf_scores[key] = rrf_scores.get(key, 0.0) + (1.0 / (k_rrf + rank))
            chunk_map[key] = hit

        for rank, hit in enumerate(semantic_hits, start=1):
            key = f"{hit.file_path}:{hit.start_line}:{hit.end_line}"
            rrf_scores[key] = rrf_scores.get(key, 0.0) + (1.0 / (k_rrf + rank))
            if key not in chunk_map:
                chunk_map[key] = hit

        fused_results: list[SearchResult] = []
        for key, rrf_score in sorted(rrf_scores.items(), key=lambda item: item[1], reverse=True):
            base_hit = chunk_map[key]
            fused_results.append(
                SearchResult(
                    file_path=base_hit.file_path,
                    start_line=base_hit.start_line,
                    end_line=base_hit.end_line,
                    snippet=base_hit.snippet,
                    score=round(rrf_score, 4),
                    match_type="hybrid",
                    symbol_name=base_hit.symbol_name,
                )
            )

        return fused_results[:limit]
