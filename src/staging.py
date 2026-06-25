from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .chemistry import canonicalize_smiles
from .ingestion import candidate_id_for


def sha256_json(payload: object) -> str:
    data = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def load_staging_candidates(paths: list[str | Path]) -> list[dict]:
    candidates: list[dict] = []
    for path in paths:
        path = Path(path)
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        if isinstance(data, dict):
            source_name = data.get("source_name") or path.stem
            source_version = data.get("version")
            raw_candidates = data.get("candidates") or []
        else:
            source_name = path.stem
            source_version = None
            raw_candidates = data
        for raw in raw_candidates:
            candidate = dict(raw)
            if not candidate.get("candidate_id") and candidate.get("smiles"):
                candidate["candidate_id"] = candidate_id_for(
                    canonicalize_smiles(candidate["smiles"]),
                    str(candidate.get("source_type") or source_name),
                )
            candidate.setdefault("source_name", source_name)
            candidate.setdefault("source_version", source_version)
            candidate.setdefault("source_record_id", candidate.get("pubchem_query") or candidate.get("name"))
            if candidate.get("smiles") and not candidate.get("canonical_smiles"):
                candidate["canonical_smiles"] = canonicalize_smiles(candidate["smiles"])
            candidate.setdefault("candidate_status", "staged")
            candidate.setdefault("review_tier", "needs_medchem_review")
            candidates.append(candidate)
    return candidates


def raw_records_from_payloads(
    source_name: str,
    payloads: list[dict],
    source_url: str | None = None,
    status_code: int | None = None,
    ingest_batch: str | None = None,
) -> list[dict]:
    fetched_at = datetime.now(timezone.utc).isoformat()
    batch = ingest_batch or f"{source_name}-{fetched_at}"
    records = []
    for idx, payload in enumerate(payloads, start=1):
        source_record_id = str(payload.get("molecule_chembl_id") or payload.get("schembl_id") or payload.get("id") or idx)
        records.append(
            {
                "source_name": source_name,
                "source_record_id": source_record_id,
                "source_url": source_url,
                "fetched_at": fetched_at,
                "status_code": status_code,
                "payload_sha256": sha256_json(payload),
                "payload": payload,
                "ingest_batch": batch,
            }
        )
    return records

