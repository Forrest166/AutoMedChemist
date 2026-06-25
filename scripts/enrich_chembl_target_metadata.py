from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.activity import infer_target_family, load_activity_evidence, save_activity_evidence, save_activity_report  # noqa: E402
from localmedchem.database import initialize_database, insert_chembl_activity_evidence  # noqa: E402


CHEMBL_TARGET_URL = "https://www.ebi.ac.uk/chembl/api/data/target.json"


def fetch_target_batch(target_ids: list[str], timeout: float = 45.0) -> tuple[dict[str, dict], str]:
    params = {
        "target_chembl_id__in": ",".join(target_ids),
        "limit": len(target_ids),
        "only": "target_chembl_id,pref_name,target_type,organism",
    }
    response = requests.get(CHEMBL_TARGET_URL, params=params, timeout=timeout, headers={"User-Agent": "AutoMedChemist/0.3"})
    response.raise_for_status()
    payload = response.json()
    targets = {}
    for item in payload.get("targets") or []:
        target_id = item.get("target_chembl_id")
        if not target_id:
            continue
        metadata = {
            "target_chembl_id": target_id,
            "target_pref_name": item.get("pref_name"),
            "target_type": item.get("target_type"),
            "target_organism": item.get("organism"),
        }
        metadata["target_family"] = infer_target_family(metadata)
        targets[str(target_id)] = metadata
    return targets, response.url


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich stored ChEMBL activity rows with target metadata and target-family labels.")
    parser.add_argument("--activity", default=str(ROOT / "data" / "activity" / "chembl_activity_evidence.yaml"))
    parser.add_argument("--report-out", default=str(ROOT / "data" / "substituents" / "chembl_activity_quality_report.json"))
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--max-targets", type=int, default=0, help="Optional cap for incremental metadata refresh; 0 means all missing targets.")
    parser.add_argument("--db-out", default=str(ROOT / "data" / "localmedchem.sqlite"))
    parser.add_argument("--write-db", action="store_true")
    args = parser.parse_args()

    rows = load_activity_evidence(args.activity)
    target_ids = []
    seen = set()
    for row in rows:
        target_id = row.get("target_chembl_id")
        if not target_id or target_id in seen:
            continue
        if row.get("target_pref_name") and row.get("target_family"):
            continue
        seen.add(target_id)
        target_ids.append(str(target_id))
    if args.max_targets:
        target_ids = target_ids[: args.max_targets]

    metadata_by_target: dict[str, dict] = {}
    urls = []
    for start in range(0, len(target_ids), args.batch_size):
        batch = target_ids[start : start + args.batch_size]
        metadata, url = fetch_target_batch(batch)
        metadata_by_target.update(metadata)
        urls.append(url)

    enriched = []
    for row in rows:
        target_metadata = metadata_by_target.get(str(row.get("target_chembl_id")), {})
        updated = {**row, **{key: value for key, value in target_metadata.items() if value not in {None, ""}}}
        updated["target_family"] = infer_target_family(updated)
        enriched.append(updated)

    existing_metadata = {}
    metadata = {
        **existing_metadata,
        "target_metadata_enriched_count": len(metadata_by_target),
        "target_metadata_api_urls": urls[:10],
    }
    save_activity_evidence(enriched, args.activity, metadata=metadata)
    report = save_activity_report(enriched, args.report_out)
    report["metadata"] = metadata
    Path(args.report_out).write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    if args.write_db:
        conn = initialize_database(args.db_out)
        try:
            insert_chembl_activity_evidence(conn, enriched)
        finally:
            conn.close()

    print(json.dumps({key: value for key, value in report.items() if key != "issues"}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
