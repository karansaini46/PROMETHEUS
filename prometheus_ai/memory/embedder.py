"""Embedding generation for semantic memory retrieval."""

import hashlib
import math
import re
from typing import Protocol


class BaseEmbedder(Protocol):
    """Protocol for embedding generation."""

    def embed_text(self, text: str) -> list[float]:
        """Generate a fixed-dimension float embedding vector from text."""
        ...


class DeterministicHashEmbedder:
    """Zero-dependency 384-dimensional feature hashing embedder.

    Produces normalized vectors that support vector cosine distance operations
    in pgvector or local cosine similarity calculations.
    """

    def __init__(self, dimension: int = 384) -> None:
        self.dimension = dimension

    def embed_text(self, text: str) -> list[float]:
        """Convert input text into a deterministic, unit-normalized 384-dim vector.

        # ponytail: Feature-hashing 384-dim embedder operates completely offline with zero
        # external API calls or heavyweight model dependencies (ceiling: semantic nuance is
        # lexical-hash bounded; upgrade path: replace with sentence-transformers or text-embedding-3-small).
        """
        vec = [0.0] * self.dimension
        tokens = re.findall(r"\w+", text.lower())
        if not tokens:
            return vec

        for i, token in enumerate(tokens):
            # Uni-gram hash
            h = int(hashlib.sha256(token.encode("utf-8")).hexdigest(), 16)
            idx = h % self.dimension
            sign = 1.0 if ((h >> 8) & 1) == 0 else -1.0
            vec[idx] += sign

            # Bi-gram hash for contextual pairing
            if i > 0:
                bi = f"{tokens[i - 1]}_{token}"
                h_bi = int(hashlib.sha256(bi.encode("utf-8")).hexdigest(), 16)
                idx_bi = h_bi % self.dimension
                sign_bi = 1.0 if ((h_bi >> 8) & 1) == 0 else -1.0
                vec[idx_bi] += sign_bi * 1.5

        # L2 Normalization to unit length for accurate cosine distance
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 1e-9:
            vec = [x / norm for x in vec]

        return vec
