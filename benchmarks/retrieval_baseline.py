"""Reproducible corpus-derived hot-path baseline for role-scoped L0 retrieval.

Run: .venv\\Scripts\\python.exe benchmarks\\retrieval_baseline.py --records 2000 --queries 100
Records and queries derive from acceptance/corpus.json. The measured path remains
local lexical retrieval: no external embedding provider or persistent vector store.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cether.l0 import L0Archive
from cether.memory_retrieval import L0RetrievalService, RetrievalConfig, RetrievalConfigWatcher
from cether.roles import RoleRegistry


def percentile(values: list[float], percent: float) -> float:
    """Return a linearly interpolated percentile for a non-empty sample."""
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percent / 100.0
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def load_corpus_fixtures(corpus_path: Path) -> tuple[list[str], list[str]]:
    """Return query and memory text fixtures declared by the project corpus."""
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    queries: list[str] = []
    memories: list[str] = []
    for case in corpus.get("cases", []):
        values = case.get("input", {})
        if isinstance(values.get("query"), str) and values["query"].strip():
            queries.append(values["query"].strip())
        if isinstance(values.get("memory"), str) and values["memory"].strip():
            memories.append(values["memory"].strip())
        elif isinstance(values.get("text"), str) and values["text"].strip():
            memories.append(values["text"].strip())
    queries = list(dict.fromkeys(queries))
    memories = list(dict.fromkeys(memories))
    if not queries or not memories:
        raise ValueError(f"acceptance corpus has no query/memory fixtures: {corpus_path}")
    return queries, memories


def run(records_count: int, query_count: int, corpus_path: Path | None = None) -> dict[str, object]:
    """Measure synchronous warm local retrieval over corpus-derived archive records."""
    source_path = corpus_path or ROOT / "acceptance" / "corpus.json"
    queries, memories = load_corpus_fixtures(source_path)
    with tempfile.TemporaryDirectory(prefix="cether-retrieval-bench-") as directory:
        root = Path(directory)
        registry = RoleRegistry(root / "registry.json")
        config_role = registry.create_role("benchmark", root / "role")
        registry.switch(config_role.role_id)
        role = registry.active
        archive = L0Archive(role.workspace / "memory" / "l0.jsonl")
        for index in range(records_count):
            memory = memories[index % len(memories)]
            archive.append(f"{memory} [bench-record:{index}]", "acceptance-corpus")
        config_path = root / "retrieval.toml"
        config_path.write_text(
            "[retrieval]\ntop_k=8\nlatency_budget_ms=300.0\njitter_range=0.0\n",
            encoding="utf-8",
        )
        service = L0RetrievalService(role, registry, archive, RetrievalConfigWatcher(config_path))
        service.search(queries[0])
        timings: list[float] = []
        budget_exceeded = 0
        for index in range(query_count):
            started = time.perf_counter()
            service.search(queries[index % len(queries)])
            elapsed = (time.perf_counter() - started) * 1000.0
            timings.append(elapsed)
            budget_exceeded += int(service.last_observation.budget_exceeded)
        return {
            "records": records_count,
            "queries": query_count,
            "p50_ms": round(percentile(timings, 50), 3),
            "p95_ms": round(percentile(timings, 95), 3),
            "p99_ms": round(percentile(timings, 99), 3),
            "max_ms": round(max(timings), 3),
            "budget_ms": service.last_observation.budget_ms,
            "budget_exceeded_queries": budget_exceeded,
            "corpus": source_path.relative_to(ROOT).as_posix() if source_path.is_relative_to(ROOT) else str(source_path),
            "corpus_fixtures": {"query_count": len(queries), "memory_count": len(memories)},
            "record_source": "acceptance corpus fixtures, deterministically repeated to requested archive size",
            "semantic_provider": "disabled; local lexical path only",
            "cold_start_excluded": True,
            "graph_hops": 0,
            "vector_store": "not connected; lexical-only result",
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--records", type=int, default=2000)
    parser.add_argument("--queries", type=int, default=100)
    parser.add_argument("--corpus", type=Path, default=ROOT / "acceptance" / "corpus.json")
    args = parser.parse_args()
    if not 1000 <= args.records <= 3000 or args.queries < 1:
        parser.error("--records must be 1000..3000 and --queries must be positive")
    print(json.dumps(run(args.records, args.queries, args.corpus), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
