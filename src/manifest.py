from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def file_sha256(path: str | Path) -> str | None:
    path = Path(path)
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_entry(path: str | Path) -> dict:
    path = Path(path)
    return {
        "path": str(path.resolve()),
        "exists": path.exists(),
        "size_bytes": path.stat().st_size if path.exists() and path.is_file() else None,
        "sha256": file_sha256(path),
    }


def build_manifest(
    seed_paths: list[str | Path],
    rule_paths: list[str | Path],
    raw_paths: list[str | Path],
    output_paths: list[str | Path],
    extra: dict | None = None,
) -> dict:
    created_at = datetime.now(timezone.utc).isoformat()
    manifest = {
        "manifest_id": f"BUILD-{created_at}",
        "created_at": created_at,
        "seeds": [file_entry(path) for path in seed_paths],
        "rules": [file_entry(path) for path in rule_paths],
        "raw_inputs": [file_entry(path) for path in raw_paths],
        "outputs": [file_entry(path) for path in output_paths],
        "extra": extra or {},
    }
    payload = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    manifest["payload_sha256"] = hashlib.sha256(payload).hexdigest()
    return manifest


def save_manifest(manifest: dict, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

