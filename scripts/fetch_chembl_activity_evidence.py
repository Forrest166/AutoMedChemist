from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.activity import load_activity_evidence, normalize_activity_row, save_activity_evidence, save_activity_report  # noqa: E402
from localmedchem.database import initialize_database, insert_chembl_activity_evidence  # noqa: E402
from localmedchem.mmp import load_mmp_evidence  # noqa: E402
from localmedchem.transform_mmp_mapping import load_transform_mmp_mappings, map_mmp_to_transform_rules  # noqa: E402


CHEMBL_ACTIVITY_URL = "https://www.ebi.ac.uk/chembl/api/data/activity.json"
DEFAULT_TYPES = {"IC50", "EC50", "Ki", "Kd", "Potency"}


def fetch_batch(molecule_ids: list[str], limit: int, timeout: float = 45.0) -> tuple[list[dict], str]:
    params = {
        "molecule_chembl_id__in": ",".join(molecule_ids),
        "limit": limit,
        "only": (
            "activity_id,molecule_chembl_id,target_chembl_id,target_pref_name,target_type,target_organism,"
            "assay_chembl_id,document_chembl_id,standard_type,standard_value,standard_units,"
            "standard_relation,pchembl_value"
        ),
    }
    response = requests.get(CHEMBL_ACTIVITY_URL, params=params, timeout=timeout, headers={"User-Agent": "AutoMedChemist/0.3"})
    response.raise_for_status()
    payload = response.json()
    return list(payload.get("activities") or []), response.url


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch ChEMBL activity evidence for harvested ChEMBL molecules.")
    parser.add_argument("--raw", default=str(ROOT / "data" / "raw" / "chembl_molecule_records.json"))
    parser.add_argument("--out", default=str(ROOT / "data" / "activity" / "chembl_activity_evidence.yaml"))
    parser.add_argument("--report-out", default=str(ROOT / "data" / "substituents" / "chembl_activity_quality_report.json"))
    parser.add_argument("--max-molecules", type=int, default=120)
    parser.add_argument("--molecule-ids", default=None, help="Optional comma/semicolon-separated ChEMBL molecule IDs to query instead of the first raw molecules.")
    parser.add_argument("--molecule-id-file", default=None, help="Optional text file with one ChEMBL molecule ID per line.")
    parser.add_argument("--mapped-mmp-examples", action="store_true", help="Fetch example molecule IDs from all currently mapped MMP transforms.")
    parser.add_argument("--mmp-evidence", default=str(ROOT / "data" / "mmp" / "chembl_mmp_transform_evidence.yaml"))
    parser.add_argument("--mapping-rules", default=str(ROOT / "data" / "rules" / "transform_mmp_mapping.yaml"))
    parser.add_argument("--append-existing", action="store_true", help="Merge fetched rows with the existing output file.")
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--limit-per-batch", type=int, default=200)
    parser.add_argument("--db-out", default=str(ROOT / "data" / "localmedchem.sqlite"))
    parser.add_argument("--write-db", action="store_true")
    args = parser.parse_args()

    if args.mapped_mmp_examples:
        mmp_rows = load_mmp_evidence(args.mmp_evidence)
        mmp_by_id = {row.get("transform_id"): row for row in mmp_rows}
        mapped_rows = map_mmp_to_transform_rules(mmp_rows, load_transform_mmp_mappings(args.mapping_rules))
        seen_ids = set()
        molecule_ids = []
        for mapping in mapped_rows:
            mmp_row = mmp_by_id.get(mapping.get("transform_id"))
            if not mmp_row:
                continue
            for molecule_id in [
                *(mmp_row.get("from_example_molecule_ids") or []),
                *(mmp_row.get("to_example_molecule_ids") or []),
                *(mmp_row.get("example_molecule_ids") or []),
            ]:
                if molecule_id and molecule_id not in seen_ids:
                    seen_ids.add(molecule_id)
                    molecule_ids.append(molecule_id)
        molecule_ids = molecule_ids[: args.max_molecules]
    elif args.molecule_ids:
        molecule_ids = [item.strip() for item in args.molecule_ids.replace(";", ",").split(",") if item.strip()]
    elif args.molecule_id_file:
        molecule_ids = [
            line.strip()
            for line in Path(args.molecule_id_file).read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
    else:
        raw_payload = json.loads(Path(args.raw).read_text(encoding="utf-8"))
        molecule_ids = [
            molecule.get("molecule_chembl_id")
            for molecule in raw_payload.get("molecules") or []
            if molecule.get("molecule_chembl_id")
        ][: args.max_molecules]

    activities = []
    urls = []
    for start in range(0, len(molecule_ids), args.batch_size):
        batch = molecule_ids[start : start + args.batch_size]
        raw_rows, url = fetch_batch(batch, limit=args.limit_per_batch)
        urls.append(url)
        for raw in raw_rows:
            if raw.get("standard_type") not in DEFAULT_TYPES:
                continue
            normalized = normalize_activity_row(raw)
            if normalized:
                activities.append(normalized)

    unique = {}
    if args.append_existing:
        for row in load_activity_evidence(args.out):
            unique[row["evidence_id"]] = row
    for row in activities:
        unique[row["evidence_id"]] = row
    activities = list(unique.values())

    metadata = {
        "raw": str(Path(args.raw).resolve()),
        "queried_molecule_count": len(molecule_ids),
        "activity_api_urls": urls[:10],
    }
    save_activity_evidence(activities, args.out, metadata=metadata)
    report = save_activity_report(activities, args.report_out)
    report["metadata"] = metadata
    Path(args.report_out).write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    if args.write_db:
        conn = initialize_database(args.db_out)
        try:
            insert_chembl_activity_evidence(conn, activities)
        finally:
            conn.close()

    print(json.dumps({key: value for key, value in report.items() if key != "issues"}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
