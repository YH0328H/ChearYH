"""Reproducible local hot-path baseline for the role-scoped L0 retrieval service.

Run: .venv\\Scripts\\python.exe benchmarks\\retrieval_baseline.py --records 2000 --queries 100
This synthetic baseline isolates CPU/local-archive costs; it does not represent an
external embedding endpoint or the project acceptance corpus.
"""

from __future__ import annotations

import argparse
import json
import statistics
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


def run(records_count: int, query_count: int) -> dict[str, object]:
    """Create a temporary role archive and measure synchronous warm queries."""
    with tempfile.TemporaryDirectory(prefix="cether-retrieval-bench-") as directory:
        root = Path(directory)
        registry = RoleRegistry(root / "registry.json")
        config_role = registry.create_role("benchmark", root / "role")
        registry.switch(config_role.role_id)
        role = registry.active
        archive = L0Archive(role.workspace / "memory" / "l0.jsonl")
        for index in range(records_count):
            archive.append(
                f"benchmark record {index} user preference topic{index % 97} detail{index % 19}",
                "benchmark",
            )
        config_path = root / "retrieval.toml"
        config_path.write_text(
            "[retrieval]\ntop_k=8\nlatency_budget_ms=300.0\njitter_range=0.0\n",
            encoding="utf-8",
        )
        service = L0RetrievalService(role, registry, archive, RetrievalConfigWatcher(config_path))
        service.search("warmup topic1")
        timings: list[float] = []
        budget_exceeded = 0
        for index in range(query_count):
            started = time.perf_counter()
            service.search(f"topic{index % 97} detail{index % 19}")
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
            "corpus": "synthetic local L0; not acceptance corpus",
            "semantic_provider": "disabled",
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--records", type=int, default=2000)
    parser.add_argument("--queries", type=int, default=100)
    args = parser.parse_args()
    if not 1000 <= args.records <= 3000 or args.queries < 1:
        parser.error("--records must be 1000..3000 and --queries must be positive")
    print(json.dumps(run(args.records, args.queries), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
