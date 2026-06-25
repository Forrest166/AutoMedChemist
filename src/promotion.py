from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

import yaml

from .chemistry import canonicalize_smiles
from .ingestion import normalize_candidate
from .library import load_records, validate_library
from .staging import load_staging_candidates


SUB_ID_RE = re.compile(r"^SUB(\d{6})$")


def load_candidate_from_db(db_path: str | Path, candidate_id: str) -> dict | None:
    db_path = Path(db_path)
    if not db_path.exists():
        return None
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT payload_json FROM candidate_substituent WHERE candidate_id = ?",
            (candidate_id,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    return json.loads(row[0])


def load_candidate_from_sources(paths: list[str | Path], candidate_id: str) -> dict | None:
    for candidate in load_staging_candidates(paths):
        if candidate.get("candidate_id") == candidate_id:
            return candidate
    return None


def _next_substituent_id(records: list[dict]) -> str:
    max_number = 0
    for record in records:
        match = SUB_ID_RE.match(str(record.get("substituent_id", "")))
        if match:
            max_number = max(max_number, int(match.group(1)))
    return f"SUB{max_number + 1:06d}"


def _existing_by_canonical(records: list[dict]) -> dict[str, str]:
    existing = {}
    for record in records:
        try:
            existing[canonicalize_smiles(record["smiles"])] = record["substituent_id"]
        except Exception:
            continue
    return existing


def _load_seed_payload(path: Path) -> dict:
    if not path.exists():
        return {"substituents": []}
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if isinstance(data, list):
        return {"substituents": data}
    if isinstance(data, dict):
        data.setdefault("substituents", [])
        return data
    raise ValueError(f"Unsupported seed shape: {path}")


def promote_candidate_to_seed(
    candidate: dict,
    existing_seed_paths: list[str | Path],
    output_seed_path: str | Path,
    reviewed_by: str = "localmedchem",
    note: str | None = None,
    source_version: str = "promotion-0.1",
) -> dict:
    output_seed = Path(output_seed_path)
    seed_paths = [Path(path) for path in existing_seed_paths]
    if output_seed not in seed_paths and output_seed.exists():
        seed_paths.append(output_seed)

    existing_records = load_records(seed_paths) if seed_paths else []
    existing_by_canonical = _existing_by_canonical(existing_records)

    raw = dict(candidate)
    if raw.get("proposed_substituent_smiles"):
        raw["smiles"] = raw["proposed_substituent_smiles"]
    raw.setdefault("promotion_note", note or "Reviewed and promoted from staging candidate.")
    raw.setdefault("source_type", raw.get("source_type") or raw.get("source_name") or "staging_candidate")

    canonical = canonicalize_smiles(raw["smiles"])
    if canonical in existing_by_canonical:
        return {
            "candidate_id": raw.get("candidate_id"),
            "substituent_id": existing_by_canonical[canonical],
            "status": "duplicate_existing",
            "appended": False,
            "seed_path": str(output_seed.resolve()),
        }

    substituent_id = _next_substituent_id(existing_records)
    record = normalize_candidate(raw, substituent_id, source_version=source_version)
    record.setdefault("review", {})
    record["review"]["status"] = "approved"
    record["review"]["reviewed_by"] = reviewed_by
    if note:
        notes = record["review"].setdefault("review_notes", [])
        if isinstance(notes, str):
            notes = [notes]
        notes.append(note)
        record["review"]["review_notes"] = notes

    valid, errors = validate_library([record])
    if errors:
        return {
            "candidate_id": raw.get("candidate_id"),
            "status": "validation_failed",
            "appended": False,
            "validation_errors": errors,
            "seed_path": str(output_seed.resolve()),
        }

    payload = _load_seed_payload(output_seed)
    payload["substituents"].extend(valid)
    output_seed.parent.mkdir(parents=True, exist_ok=True)
    output_seed.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=False), encoding="utf-8")
    return {
        "candidate_id": raw.get("candidate_id"),
        "substituent_id": substituent_id,
        "status": "promoted",
        "appended": True,
        "seed_path": str(output_seed.resolve()),
    }

