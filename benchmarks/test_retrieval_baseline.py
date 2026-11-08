from __future__ import annotations

import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("retrieval_baseline.py")
SPEC = importlib.util.spec_from_file_location("retrieval_baseline", MODULE_PATH)
assert SPEC and SPEC.loader
BASELINE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BASELINE)


def test_percentile_interpolation() -> None:
    assert BASELINE.percentile([1.0, 2.0, 3.0, 4.0], 50) == 2.5


def test_baseline_reports_acceptance_corpus_hot_path_metrics() -> None:
    result = BASELINE.run(records_count=1000, query_count=5)
    assert result["records"] == 1000
    assert result["queries"] == 5
    assert 0 <= result["p50_ms"] <= result["p99_ms"]
    assert result["corpus"] == "acceptance/corpus.json"
    assert result["record_source"].startswith("acceptance corpus fixtures")
    assert result["semantic_provider"] == "disabled; local lexical path only"
    assert result["vector_store"] == "not connected; lexical-only result"
    assert result["corpus_fixtures"]["query_count"] > 0
    assert result["corpus_fixtures"]["memory_count"] > 0
