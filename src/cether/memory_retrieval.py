"""Role-scoped, observable hybrid retrieval over the active L0 archive."""

from __future__ import annotations

import re
import tomllib
import time
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Callable, Protocol

from .hexbit import EncodedResult, HexbitConfig, apply_hexbit_penalty, encode_six_bits
from .l0 import L0Archive
from .multipliers import MultiplierConfig, apply_multipliers
from .retrieval import (
    BM25, Document, GraphRetrieval, KnowledgeGraph, RetrievalResult,
    VectorDocument, VectorRetrieval,
)
from .roles import RoleContext, ScopeMismatchError

_WORD = re.compile(r"[a-zA-Z0-9_]+|[\u3400-\u9fff]+")


def tokenize(text: str) -> list[str]:
    """Tokenize Latin words and Chinese runs into characters plus adjacent bigrams."""
    tokens: list[str] = []
    for match in _WORD.finditer(text.casefold()):
        token = match.group()
        if "\u3400" <= token[0] <= "\u9fff":
            tokens.extend(token)
            tokens.extend(token[index:index + 2] for index in range(len(token) - 1))
        else:
            tokens.append(token)
    return tokens


def weighted_rrf_fusion(
    results_list: list[list[RetrievalResult]], weights: list[float], k: int = 60
) -> list[RetrievalResult]:
    """Fuse ranked channels with per-channel reliability weights using weighted RRF."""
    if len(results_list) != len(weights) or k < 1 or any(weight < 0 for weight in weights):
        raise ValueError("weighted RRF requires aligned channels, positive k and non-negative weights")
    scores: dict[str, float] = {}
    for results, weight in zip(results_list, weights):
        for rank, result in enumerate(results, start=1):
            scores[result.doc_id] = scores.get(result.doc_id, 0.0) + weight / (k + rank)
    return [RetrievalResult(doc_id, score) for doc_id, score in sorted(scores.items(), key=lambda item: item[1], reverse=True)]


@dataclass(frozen=True)
class RetrievalConfig:
    """Hot retrieval and fusion parameters; latency limits are observational."""

    top_k: int = 8
    min_score: float = 0.0
    bm25_k1: float = 1.5
    bm25_b: float = 0.75
    rrf_k: int = 60
    vector_top_k: int = 10
    graph_top_k: int = 10
    graph_max_hops: int = 1
    graph_edge_min_weight: float = 0.0
    vector_weight: float = 1.0
    graph_weight: float = 1.0
    high_weight_cutoff: float = 0.8
    medium_weight_cutoff: float = 0.3
    lifecycle_tau_seconds: float = 604800.0
    lifecycle_min: float = 0.5
    rumination_threshold: int = 5
    rumination_penalty: float = 0.6
    drive_weights: tuple[tuple[str, float], ...] = ()
    region_bonus: float = 1.2
    jitter_range: float = 0.0
    hexbit_decay_factor: float = 0.85
    hexbit_min_repeat: int = 1
    latency_budget_ms: float = 300.0

    def __post_init__(self) -> None:
        if self.top_k < 1:
            raise ValueError("top_k must be positive")
        if self.min_score < 0 or self.bm25_k1 <= 0 or not 0 <= self.bm25_b <= 1:
            raise ValueError("invalid retrieval scoring configuration")
        if self.rrf_k < 1 or min(self.vector_top_k, self.graph_top_k) < 1 or self.graph_max_hops < 0:
            raise ValueError("invalid retrieval channel limits")
        if min(self.graph_edge_min_weight, self.vector_weight, self.graph_weight) < 0:
            raise ValueError("retrieval channel weights must be non-negative")
        if not 0 <= self.medium_weight_cutoff <= self.high_weight_cutoff <= 1:
            raise ValueError("memory weight cutoffs must satisfy 0 <= medium <= high <= 1")
        if self.lifecycle_tau_seconds <= 0 or not 0 <= self.lifecycle_min <= 1 or self.rumination_threshold < 1:
            raise ValueError("invalid lifecycle or rumination configuration")
        if not 0 <= self.rumination_penalty <= 1 or self.region_bonus < 0 or not 0 <= self.jitter_range < 1:
            raise ValueError("invalid retrieval multiplier configuration")
        if not 0 < self.hexbit_decay_factor <= 1 or self.hexbit_min_repeat < 0:
            raise ValueError("invalid hexbit configuration")
        if any(not name or value < 0 for name, value in self.drive_weights):
            raise ValueError("drive_weights must contain named non-negative values")
        if self.latency_budget_ms <= 0:
            raise ValueError("latency_budget_ms must be positive")


class ScopeGuard(Protocol):
    def ensure_role_scope(self, scope_id: str) -> RoleContext: ...


class RetrievalConfigWatcher:
    """Reload TOML on mtime change; retain last valid config after malformed edits."""

    def __init__(self, path: Path, default: RetrievalConfig | None = None) -> None:
        self.path = path
        self._config = default or RetrievalConfig()
        self._mtime_ns = -1
        self._lock = RLock()
        self.get()

    def get(self) -> RetrievalConfig:
        with self._lock:
            try:
                stat = self.path.stat()
            except OSError:
                return self._config
            if stat.st_mtime_ns == self._mtime_ns:
                return self._config
            try:
                raw = tomllib.loads(self.path.read_text(encoding="utf-8")).get("retrieval", {})
                candidate = RetrievalConfig(
                    top_k=int(raw.get("top_k", self._config.top_k)),
                    min_score=float(raw.get("min_score", self._config.min_score)),
                    bm25_k1=float(raw.get("bm25_k1", self._config.bm25_k1)),
                    bm25_b=float(raw.get("bm25_b", self._config.bm25_b)),
                    rrf_k=int(raw.get("rrf_k", self._config.rrf_k)),
                    vector_top_k=int(raw.get("vector_top_k", self._config.vector_top_k)),
                    graph_top_k=int(raw.get("graph_top_k", self._config.graph_top_k)),
                    graph_max_hops=int(raw.get("graph_max_hops", self._config.graph_max_hops)),
                    graph_edge_min_weight=float(raw.get("graph_edge_min_weight", self._config.graph_edge_min_weight)),
                    vector_weight=float(raw.get("vector_weight", self._config.vector_weight)),
                    graph_weight=float(raw.get("graph_weight", self._config.graph_weight)),
                    high_weight_cutoff=float(raw.get("high_weight_cutoff", self._config.high_weight_cutoff)),
                    medium_weight_cutoff=float(raw.get("medium_weight_cutoff", self._config.medium_weight_cutoff)),
                    lifecycle_tau_seconds=float(raw.get("lifecycle_tau_seconds", self._config.lifecycle_tau_seconds)),
                    lifecycle_min=float(raw.get("lifecycle_min", self._config.lifecycle_min)),
                    rumination_threshold=int(raw.get("rumination_threshold", self._config.rumination_threshold)),
                    rumination_penalty=float(raw.get("rumination_penalty", self._config.rumination_penalty)),
                    drive_weights=tuple((str(k), float(v)) for k, v in raw.get("drive_weights", self._config.drive_weights).items()) if isinstance(raw.get("drive_weights", self._config.drive_weights), dict) else self._config.drive_weights,
                    region_bonus=float(raw.get("region_bonus", self._config.region_bonus)),
                    jitter_range=float(raw.get("jitter_range", self._config.jitter_range)),
                    hexbit_decay_factor=float(raw.get("hexbit_decay_factor", self._config.hexbit_decay_factor)),
                    hexbit_min_repeat=int(raw.get("hexbit_min_repeat", self._config.hexbit_min_repeat)),
                    latency_budget_ms=float(raw.get("latency_budget_ms", self._config.latency_budget_ms)),
                )
            except (OSError, ValueError, TypeError, tomllib.TOMLDecodeError):
                return self._config
            self._config = candidate
            self._mtime_ns = stat.st_mtime_ns
            return self._config


@dataclass(frozen=True)
class RetrievalObservation:
    elapsed_ms: float
    budget_ms: float
    budget_exceeded: bool
    result_count: int
    channel: str
    error: str | None = None
    lexical_count: int = 0
    vector_count: int = 0
    graph_count: int = 0


class L0RetrievalService:
    """Retrieve only positive lexical matches from one role's append-only L0."""

    def __init__(
        self,
        role: RoleContext,
        scope_guard: ScopeGuard,
        archive: L0Archive,
        config: RetrievalConfigWatcher | None = None,
        *,
        embedding_provider: Callable[[list[str]], list[list[float]]] | None = None,
        graph_provider: Callable[[list[dict]], KnowledgeGraph] | None = None,
        spatial_provider: Callable[[str, list[dict]], list[RetrievalResult]] | None = None,
        current_state: Callable[[], dict[str, float]] | None = None,
        current_context: Callable[[], dict[str, str | None]] | None = None,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self.role = role
        self.scope_guard = scope_guard
        self.archive = archive
        self.embedding_provider = embedding_provider
        self.graph_provider = graph_provider
        self.spatial_provider = spatial_provider
        self.current_state = current_state or (lambda: {})
        self.current_context = current_context or (lambda: {})
        self._recall_counts: dict[str, int] = {}
        self._embedding_cache: dict[str, tuple[str, list[float]]] = {}
        self._embedding_archive_signature: tuple[int, int] | None = None
        self._archive_signature: tuple[int, int] | None = None
        self._cached_high_weight_cutoff: float | None = None
        self._records_cache: tuple[dict, ...] = ()
        self._normal_docs_cache: tuple[Document, ...] = ()
        self._bm25_cache: dict[tuple[float, float, int], BM25] = {}
        self._lock = RLock()
        default_config_path = Path(__file__).resolve().parents[2] / "config" / "retrieval.toml"
        self.config = config or RetrievalConfigWatcher(default_config_path)
        self.clock = clock
        self.last_observation = RetrievalObservation(0.0, self.config.get().latency_budget_ms, False, 0, "lexical")
        self.last_results: tuple[RetrievalResult, ...] = ()

    def search(self, query: str) -> tuple[str, ...]:
        """Return ranked role-local L0 matches, with hybrid channels injected explicitly.

        Normal-weight records use BM25, optionally fused with an embedding channel
        and a graph channel. High-weight records use only the provided spatial graph
        route; low-weight records are never proactively injected. Channel misses
        remain misses, and external provider errors make this turn return no hits.
        """
        with self._lock:
            return self._search(query)

    def _search(self, query: str) -> tuple[str, ...]:
        self.scope_guard.ensure_role_scope(self.role.scope_id)
        cfg = self.config.get()
        started = self.clock()
        lexical_count = vector_count = graph_count = 0
        try:
            signature = self._archive_file_signature()
            if (signature is None or signature != self._archive_signature
                    or self._cached_high_weight_cutoff != cfg.high_weight_cutoff):
                records = tuple(self.archive)
                normal_records = tuple(
                    record for record in records
                    if record.get("weight", "normal") != "low"
                    and not self._is_high_record(record, cfg)
                    and str(record.get("text", "")).strip()
                )
                self._records_cache = records
                self._normal_docs_cache = tuple(
                    Document(str(record["id"]), str(record["text"]), tokenize(str(record["text"])))
                    for record in normal_records
                )
                self._bm25_cache.clear()
                self._archive_signature = signature
                self._cached_high_weight_cutoff = cfg.high_weight_cutoff
                if signature != self._embedding_archive_signature:
                    valid_ids = {str(record["id"]) for record in records}
                    self._embedding_cache = {
                        doc_id: value for doc_id, value in self._embedding_cache.items()
                        if doc_id in valid_ids
                    }
                    self._embedding_archive_signature = signature
            records = self._records_cache
            by_id = {str(record["id"]): record for record in records}
            low = [record for record in records if record.get("weight", "normal") == "low"]
            normal = [record for record in records if record.get("weight", "normal") != "low" and not self._is_high_record(record, cfg)]
            high = [record for record in records if self._is_high_record(record, cfg)]
            query_tokens = tokenize(query)
            query_state = self.current_state()
            query_context = self.current_context()

            normal_docs = list(self._normal_docs_cache)
            channel_lists: list[list[RetrievalResult]] = []
            channel_weights: list[float] = []
            lexical = []
            if normal_docs and query_tokens:
                bm25_key = (cfg.bm25_k1, cfg.bm25_b, len(normal_docs))
                bm25 = self._bm25_cache.get(bm25_key)
                if bm25 is None:
                    bm25 = BM25(normal_docs, k1=cfg.bm25_k1, b=cfg.bm25_b)
                    self._bm25_cache[bm25_key] = bm25
                lexical = bm25.search(query_tokens, cfg.top_k)
            lexical = [result for result in lexical if result.score > 0.0]
            lexical_count = len(lexical)
            if lexical:
                channel_lists.append(lexical)
                channel_weights.append(1.0)

            if self.embedding_provider is not None and normal_docs and query.strip():
                missing_docs = [doc for doc in normal_docs
                                if doc.id not in self._embedding_cache
                                or self._embedding_cache[doc.id][0] != doc.text]
                inputs = [query] + [doc.text for doc in missing_docs]
                vectors = self.embedding_provider(inputs)
                if len(vectors) != len(inputs):
                    raise ValueError(f"embedding provider returned {len(vectors)} vectors for {len(inputs)} inputs")
                query_vector = vectors[0]
                for doc, vector_value in zip(missing_docs, vectors[1:]):
                    self._embedding_cache[doc.id] = (doc.text, vector_value)
                vector_docs = [
                    VectorDocument(doc.id, doc.text, self._embedding_cache[doc.id][1])
                    for doc in normal_docs
                ]
                vector = VectorRetrieval(vector_docs).search(query_vector, cfg.vector_top_k)
                vector = [result for result in vector if result.score > 0.0]
                vector_count = len(vector)
                if vector:
                    channel_lists.append(vector)
                    channel_weights.append(cfg.vector_weight)

            if self.graph_provider is not None and normal:
                graph = self.graph_provider(normal)
                seeds = [entity for entity in query_tokens if graph.get_node(entity) is not None]
                graph_results = GraphRetrieval(graph).search(seeds, cfg.graph_top_k, cfg.graph_max_hops)
                graph_results = [result for result in graph_results if result.score >= cfg.graph_edge_min_weight and result.doc_id in by_id and by_id[result.doc_id] in normal]
                graph_count = len(graph_results)
                if graph_results:
                    channel_lists.append(graph_results)
                    channel_weights.append(cfg.graph_weight)

            fused = weighted_rrf_fusion(channel_lists, channel_weights, cfg.rrf_k)
            graph_high: list[RetrievalResult] = []
            if high and self.spatial_provider is not None:
                graph_high = [r for r in self.spatial_provider(query, high) if r.doc_id in by_id and by_id[r.doc_id] in high and r.score > 0.0]
            # No spatial provider means no high-weight hits; never relabel lexical recall as spatial recall.
            high_ranked = graph_high
            for result in high_ranked:
                if result not in fused:
                    fused.append(result)

            # Keep high-weight spatial results separate from the medium-weight fusion ranking.
            spatial_scores: list[tuple[str, float]] = []
            context_region = query_context.get("region")
            encoded: list[EncodedResult] = []
            raw_scores: dict[str, float] = {}
            spatial_ids = {result.doc_id for result in high_ranked}
            for result in fused:
                record = by_id.get(result.doc_id)
                if record is None or record in low:
                    continue
                is_high = record in high
                if is_high and result.doc_id not in spatial_ids:
                    continue
                weight_value = self._weight_value(record.get("weight", "normal"))
                if not is_high and weight_value < cfg.medium_weight_cutoff:
                    continue
                created = self._timestamp(record.get("ts"))
                elapsed_seconds = max(0.0, self.clock() - created) if created is not None else 0.0
                drive_map = dict(cfg.drive_weights)
                tags = record.get("tags", []) if isinstance(record.get("tags", []), list) else []
                active_drives = {name: value for name, value in query_state.items() if name in set(drive_map.values())}
                score = result.score
                score = apply_multipliers(
                    score, elapsed_seconds, self._recall_counts.get(result.doc_id, 0), tags,
                    active_drives, drive_map, float(record.get("valence", 0.0)),
                    float(query_state.get("valence", 0.0)), record.get("region"), context_region,
                    MultiplierConfig(lifecycle_min=cfg.lifecycle_min,
                                     rumination_threshold=cfg.rumination_threshold,
                                     rumination_penalty=cfg.rumination_penalty,
                                     jitter_range=cfg.jitter_range, region_bonus=cfg.region_bonus),
                    lifecycle_tau=cfg.lifecycle_tau_seconds,
                )
                raw_scores[result.doc_id] = score
                if is_high:
                    spatial_scores.append((result.doc_id, score))
                else:
                    encoded.append(EncodedResult(result.doc_id, score, encode_six_bits(record)))
            adjusted = apply_hexbit_penalty(encoded, HexbitConfig(cfg.hexbit_decay_factor, cfg.hexbit_min_repeat))
            medium_ranked = sorted((RetrievalResult(item.doc_id, item.score) for item in adjusted if item.score > cfg.min_score), key=lambda r: r.score, reverse=True)[:cfg.top_k]
            high_ranked_scored = sorted(spatial_scores, key=lambda item: item[1], reverse=True)[:cfg.top_k]
            ranked = [RetrievalResult(doc_id, score) for doc_id, score in high_ranked_scored] + medium_ranked
            ranked = ranked[:cfg.top_k]
            self.last_results = tuple(ranked)
            self._recall_counts.update({result.doc_id: self._recall_counts.get(result.doc_id, 0) + 1 for result in ranked})
            hits = tuple(str(by_id[result.doc_id]["text"]) for result in ranked)
            channels = [name for name, count in (("lexical", lexical_count), ("vector", vector_count), ("graph", graph_count)) if count]
            channel = "+".join(channels) if channels else "none"
            if high_ranked_scored:
                channel = "+".join(filter(None, (channel, "spatial")))
            error = None
        except ScopeMismatchError:
            raise
        except Exception as exc:
            hits = ()
            self.last_results = ()
            channel = "none"
            error = f"{type(exc).__name__}: {exc}"
        elapsed = max(0.0, (self.clock() - started) * 1000.0)
        self.last_observation = RetrievalObservation(
            elapsed, cfg.latency_budget_ms, elapsed > cfg.latency_budget_ms, len(hits), channel, error,
            lexical_count, vector_count, graph_count,
        )
        return hits

    def _archive_file_signature(self) -> tuple[int, int] | None:
        """Return append-only archive identity and size/mtime for cache invalidation."""
        path = getattr(self.archive, "path", None)
        if path is None:
            return None
        try:
            stat = path.stat()
        except OSError:
            return None
        return stat.st_mtime_ns, stat.st_size

    @staticmethod
    def _is_high_record(record: dict, config: RetrievalConfig) -> bool:
        metadata = record.get("tier_metadata", {})
        if isinstance(metadata, dict) and metadata.get("memory_tier") == "high":
            return True
        return L0RetrievalService._weight_value(record.get("weight", "normal")) >= config.high_weight_cutoff

    @staticmethod
    def _weight_value(value: object) -> float:
        """Map the L0 coarse weight labels into configurable retrieval bands."""
        if isinstance(value, (int, float)):
            return max(0.0, min(1.0, float(value)))
        return {"low": 0.1, "normal": 0.6, "medium": 0.6, "high": 0.9, "flash": 1.0}.get(str(value).lower(), 0.6)

    @staticmethod
    def _timestamp(value: object) -> float | None:
        """Parse an ISO-8601 archive timestamp to Unix seconds, if present."""
        from datetime import datetime
        if not isinstance(value, str):
            return None
        try:
            return datetime.fromisoformat(value).timestamp()
        except ValueError:
            return None
