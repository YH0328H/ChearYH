"""Keyword retrieval over L0 records. Degraded path used when embedding is unavailable.

Chinese text has no spaces, so tokens are character bigrams plus ASCII words.
A query with no matching record returns an empty list. Nothing is filled in
to look like a hit.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

_ASCII_WORD = re.compile(r"[A-Za-z0-9]+")
_CJK = re.compile(r"[一-鿿]")


def tokenize(text: str) -> set[str]:
    tokens = {w.lower() for w in _ASCII_WORD.findall(text)}
    chars = [c for c in text if _CJK.match(c)]
    tokens.update(a + b for a, b in zip(chars, chars[1:]))
    return tokens


@dataclass(frozen=True)
class Hit:
    record_id: str
    score: float
    text: str


def search(query: str, records: Iterable[dict], limit: int = 5) -> list[Hit]:
    query_tokens = tokenize(query)
    if not query_tokens:
        return []
    hits: list[Hit] = []
    for rec in records:
        overlap = query_tokens & tokenize(rec["text"])
        if overlap:
            hits.append(Hit(rec["id"], len(overlap) / len(query_tokens), rec["text"]))
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:limit]
