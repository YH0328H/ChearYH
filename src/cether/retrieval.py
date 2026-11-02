"""Three-way retrieval fusion: lexical (BM25), semantic (vector), and graph diffusion.

After fusion, results are multiplied by lifecycle, rumination suppression, drive bias,
valence bias, region bonus, jitter, and six-feature encoding penalty (7.2).

This module implements the core retrieval paths. Weight adjustment will be wired when
state modules are complete.
"""

from __future__ import annotations

import json
import math
import tomllib
import urllib.error
import urllib.request
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

Post = Callable[[str, dict, dict], dict]


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


@dataclass(frozen=True)
class EmbeddingConfig:
    base_url: str
    model_id: str
    api_key: str
    dimensions: int


class EmbeddingError(RuntimeError):
    pass


def load_embedding_config(path: Path, environ: Mapping[str, str]) -> EmbeddingConfig:
    """Read the [embedding] table. The key comes from the environment, never from the file."""
    raw = tomllib.loads(path.read_text(encoding="utf-8"))["embedding"]
    return EmbeddingConfig(
        base_url=str(raw["base_url"]),
        model_id=str(raw["model_id"]),
        api_key=environ.get(str(raw["key_env"]), ""),
        dimensions=int(raw["dimensions"]),
    )


def embed_text(cfg: EmbeddingConfig, text: str, post: Post) -> list[float]:
    """Return the embedding vector for one text."""
    if not cfg.api_key:
        raise EmbeddingError("API key is not set")
    body = {"model": cfg.model_id, "input": text}
    headers = {"Authorization": f"Bearer {cfg.api_key}", "Content-Type": "application/json"}
    url = cfg.base_url.rstrip("/") + "/embeddings"
    try:
        reply = post(url, body, headers)
    except Exception as exc:
        raise EmbeddingError(f"failed to call embedding slot: {exc}") from exc
    try:
        vector = reply["data"][0]["embedding"]
    except (KeyError, IndexError, TypeError) as exc:
        raise EmbeddingError(f"unexpected response shape: {json.dumps(reply, ensure_ascii=False)[:200]}") from exc
    if not isinstance(vector, list) or len(vector) != cfg.dimensions:
        raise EmbeddingError(f"expected {cfg.dimensions} dimensions, got {len(vector)}")
    return vector


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Return cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


@dataclass(frozen=True)
class VectorDocument:
    """One document with precomputed embedding."""
    id: str
    text: str
    vector: list[float]


class VectorRetrieval:
    """Semantic retrieval via cosine similarity of embeddings."""
    def __init__(self, documents: list[VectorDocument]) -> None:
        self._docs = {doc.id: doc for doc in documents}

    def search(self, query_vector: list[float], top_k: int = 10) -> list[RetrievalResult]:
        """Return top-k documents by cosine similarity to query vector."""
        scores = {
            doc_id: cosine_similarity(query_vector, doc.vector)
            for doc_id, doc in self._docs.items()
        }
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
