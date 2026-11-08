"""Versioned, user-safe registration for bundled default files."""
from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PresetResult:
    name: str
    status: str
    path: str
    version: str


def register_presets(source: Path, destination: Path, manifest_path: Path) -> list[PresetResult]:
    """Register missing or pristine bundled files; retain modified user copies.

    A content hash distinguishes an untouched managed preset from a user-edited
    copy. Upgrades replace only files whose current bytes match the old manifest.
    """
    source, destination = Path(source), Path(destination)
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {"files": {}}
    old_files = manifest.get("files", {})
    results: list[PresetResult] = []
    next_files: dict[str, dict[str, str]] = {}
    destination.mkdir(parents=True, exist_ok=True)
    for bundled in sorted(p for p in source.rglob("*") if p.is_file()):
        name = bundled.relative_to(source).as_posix()
        target = destination / name
        version = _version(bundled)
        bundled_hash = _hash(bundled)
        previous = old_files.get(name, {})
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(bundled, target)
            status = "registered"
        elif _hash(target) == bundled_hash:
            status = "unchanged"
        elif previous and _hash(target) == previous.get("sha256"):
            shutil.copy2(bundled, target)
            status = "upgraded"
        else:
            status = "user_copy"
        next_files[name] = {"sha256": bundled_hash, "version": version}
        results.append(PresetResult(name, status, str(target), version))
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    temp = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
    temp.write_text(json.dumps({"files": next_files}, indent=2), encoding="utf-8")
    temp.replace(manifest_path)
    return results


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _version(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines()[:8]:
        if line.lower().startswith("version:"):
            return line.split(":", 1)[1].strip()
    return "1"
