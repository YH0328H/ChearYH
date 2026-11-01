"""Six-drive inertia filter and four-willingness projection.

Drives move toward a target by first-order inertia. Each willingness is a
linear projection of the drives, clamped to [0, 1]. Coefficients and band
thresholds come from config/state_mapping.toml.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Mapping:
    drives: tuple[str, ...]
    alpha: float
    willingness: dict[str, tuple[float, tuple[float, ...]]]
    high: float
    low: float


def load_mapping(path: Path) -> Mapping:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    drives = tuple(raw["drives"]["order"])
    willingness: dict[str, tuple[float, tuple[float, ...]]] = {}
    for name, spec in raw["willingness"].items():
        weights = tuple(float(w) for w in spec["weights"])
        if len(weights) != len(drives):
            raise ValueError(f"{name}: {len(weights)} weights for {len(drives)} drives")
        willingness[name] = (float(spec["bias"]), weights)
    alpha = float(raw["filter"]["alpha"])
    if not 0 < alpha <= 1:
        raise ValueError("filter.alpha must be in (0, 1]")
    return Mapping(
        drives=drives,
        alpha=alpha,
        willingness=willingness,
        high=float(raw["bands"]["high"]),
        low=float(raw["bands"]["low"]),
    )


def clamp(x: float) -> float:
    return min(1.0, max(0.0, x))


def step_drives(current: tuple[float, ...], target: tuple[float, ...], alpha: float) -> tuple[float, ...]:
    return tuple(clamp(c + alpha * (t - c)) for c, t in zip(current, target))


def run_drives(mapping: Mapping, initial: tuple[float, ...], target: tuple[float, ...], steps: int) -> list[tuple[float, ...]]:
    trace = [tuple(initial)]
    for _ in range(steps):
        trace.append(step_drives(trace[-1], target, mapping.alpha))
    return trace


def project(mapping: Mapping, drives: tuple[float, ...]) -> dict[str, float]:
    return {
        name: clamp(bias + sum(w * d for w, d in zip(weights, drives)))
        for name, (bias, weights) in mapping.willingness.items()
    }


def band(value: float, mapping: Mapping) -> str:
    if value >= mapping.high:
        return "high"
    if value <= mapping.low:
        return "low"
    return "mid"
