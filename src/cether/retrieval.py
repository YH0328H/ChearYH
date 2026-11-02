"""Three-way retrieval fusion: lexical (BM25), semantic (vector), and graph diffusion.

After fusion, results are multiplied by lifecycle, rumination suppression, drive bias,
valence bias, region bonus, jitter, and six-feature encoding penalty (7.2).

This module implements the core retrieval paths. Weight adjustment will be wired when
state modules are complete.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass


@dataclass(frozen=True)
class Document:
    """One document in the retrieval index."""
    id: str
    text: str
    tokens: list[str]


@dataclass(frozen=True)
class RetrievalResult:
    """One retrieval result with score."""
    doc_id: str
    score: float


class BM25:
    """BM25 lexical retrieval with configurable k1 and b parameters."""
    def __init__(self, documents: list[Document], k1: float = 1.5, b: float = 0.75) -> None:
        self._docs = {doc.id: doc for doc in documents}
        self._k1 = k1
        self._b = b
        self._avg_len = sum(len(doc.tokens) for doc in documents) / max(len(documents), 1)
        self._idf = self._compute_idf(documents)

    def _compute_idf(self, documents: list[Document]) -> dict[str, float]:
        """Compute IDF for each term."""
        df = Counter()
        for doc in documents:
            unique_tokens = set(doc.tokens)
            for token in unique_tokens:
                df[token] += 1
        n = len(documents)
        return {
            term: math.log((n - count + 0.5) / (count + 0.5) + 1.0)
            for term, count in df.items()
        }

    def search(self, query_tokens: list[str], top_k: int = 10) -> list[RetrievalResult]:
        """Return top-k documents by BM25 score."""
        scores = {}
        for doc_id, doc in self._docs.items():
            tf = Counter(doc.tokens)
            score = 0.0
            for token in query_tokens:
                if token not in self._idf:
                    continue
                idf = self._idf[token]
                freq = tf[token]
                norm = 1.0 - self._b + self._b * (len(doc.tokens) / self._avg_len)
                score += idf * (freq * (self._k1 + 1.0)) / (freq + self._k1 * norm)
            scores[doc_id] = score
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [RetrievalResult(doc_id, score) for doc_id, score in ranked[:top_k]]


def rrf_fusion(results_list: list[list[RetrievalResult]], k: int = 60) -> list[RetrievalResult]:
    """Reciprocal Rank Fusion: combine multiple ranked lists into one.

    RRF score = sum(1 / (k + rank)) for each list where the doc appears.
    Default k=60 is from the original RRF paper.
    """
    scores = {}
    for results in results_list:
        for rank, result in enumerate(results, start=1):
            if result.doc_id not in scores:
                scores[result.doc_id] = 0.0
            scores[result.doc_id] += 1.0 / (k + rank)
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [RetrievalResult(doc_id, score) for doc_id, score in ranked]
