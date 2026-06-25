from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.database import initialize_database, insert_candidate_substituents, insert_raw_source_records  # noqa: E402
from localmedchem.patent_parser import extract_surechembl_candidates  # noqa: E402
from localmedchem.staging import load_staging_candidates, raw_records_from_payloads  # noqa: E402


SURECHEMBL_BASE_URL = "https://www.api.surechembl.org/"


def try_fetch_root(timeout: float = 20.0, verify_tls: bool = True) -> dict:
    fetched_at = datetime.now(timezone.utc).isoformat()
    try:
        response = requests.get(SURECHEMBL_BASE_URL, timeout=timeout, verify=verify_tls, headers={"User-Agent": "AutoMedChemist/0.1"})
        return {
            "source_name": "SureChEMBL",
            "source_url": SURECHEMBL_BASE_URL,
            "status_code": response.status_code,
            "fetched_at": fetched_at,
            "text_preview": response.text[:1000],
        }
    except Exception as exc:
        return {
            "source_name": "SureChEMBL",
            "source_url": SURECHEMBL_BASE_URL,
            "status_code": None,
            "fetched_at": fetched_at,
            "error": str(exc),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage SureChEMBL/patent-mined candidates with explicit advanced-review gating.")
    parser.add_argument("--seed", default=str(ROOT / "data" / "sources" / "patent_mined_candidates.yaml"))
    parser.add_argument("--raw-out", default=str(ROOT / "data" / "raw" / "surechembl_api_probe.json"))
    parser.add_argument("--candidates-out", default=str(ROOT / "data" / "sources" / "surechembl_patent_candidates.yaml"))
    parser.add_argument("--db-out", default=str(ROOT / "data" / "localmedchem.sqlite"))
    parser.add_argument("--write-db", action="store_true")
    parser.add_argument("--insecure", action="store_true", help="Disable TLS verification for the API probe only.")
    args = parser.parse_args()

    probe = try_fetch_root(verify_tls=not args.insecure)
    raw_path = Path(args.raw_out)
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(json.dumps(probe, indent=2, sort_keys=True), encoding="utf-8")

    seed_path = Path(args.seed)
    candidates_path = Path(args.candidates_out)
    candidates_path.parent.mkdir(parents=True, exist_ok=True)
    data = yaml.safe_load(seed_path.read_text(encoding="utf-8")) or {}
    parsed_candidates = extract_surechembl_candidates([probe])
    if parsed_candidates:
        existing_ids = {candidate.get("candidate_id") for candidate in data.get("candidates") or []}
        data.setdefault("candidates", [])
        data["candidates"].extend(candidate for candidate in parsed_candidates if candidate.get("candidate_id") not in existing_ids)
    data["parser_report"] = {
        "parsed_candidate_count": len(parsed_candidates),
        "source_payload_count": 1,
        "note": "Generic parser extracts explicit candidates/compounds or one-attachment SMILES from SureChEMBL-like payloads.",
    }
    data["api_probe"] = {
        "status_code": probe.get("status_code"),
        "fetched_at": probe.get("fetched_at"),
        "note": "Candidates are curated patent/SureChEMBL-inspired staging rows until API records are available.",
    }
    candidates_path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=False), encoding="utf-8")

    candidates = load_staging_candidates([candidates_path])
    if args.write_db:
        conn = initialize_database(args.db_out)
        try:
            insert_raw_source_records(conn, raw_records_from_payloads("SureChEMBL", [probe], SURECHEMBL_BASE_URL, probe.get("status_code")))
            insert_candidate_substituents(conn, candidates)
        finally:
            conn.close()

    print(
        json.dumps(
            {
                "api_status_code": probe.get("status_code"),
                "parsed_candidate_count": len(parsed_candidates),
                "candidate_count": len(candidates),
                "raw_out": str(raw_path.resolve()),
                "candidates_out": str(candidates_path.resolve()),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
