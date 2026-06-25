from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.database import initialize_database, insert_mmp_transform_evidence  # noqa: E402
from localmedchem.mmp import build_mmp_transform_evidence, save_mmp_evidence, validate_mmp_evidence  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Mine single-cut MMP transform evidence from ChEMBL molecule records.")
    parser.add_argument("--raw", default=str(ROOT / "data" / "raw" / "chembl_molecule_records.json"))
    parser.add_argument("--out", default=str(ROOT / "data" / "mmp" / "chembl_mmp_transform_evidence.yaml"))
    parser.add_argument("--report-out", default=str(ROOT / "data" / "substituents" / "mmp_evidence_quality_report.json"))
    parser.add_argument("--min-pair-count", type=int, default=2)
    parser.add_argument("--max-transforms", type=int, default=300)
    parser.add_argument("--db-out", default=str(ROOT / "data" / "localmedchem.sqlite"))
    parser.add_argument("--write-db", action="store_true")
    args = parser.parse_args()

    raw_payload = json.loads(Path(args.raw).read_text(encoding="utf-8"))
    molecules = list(raw_payload.get("molecules") or [])
    print(f"Building MMP evidence from {len(molecules)} molecules...", flush=True)
    rows = build_mmp_transform_evidence(
        molecules,
        min_pair_count=args.min_pair_count,
        max_transforms=args.max_transforms,
    )
    print(f"Built {len(rows)} MMP transforms.", flush=True)
    metadata = {
        "raw": str(Path(args.raw).resolve()),
        "source_molecule_count": len(molecules),
        "min_pair_count": args.min_pair_count,
        "max_transforms": args.max_transforms,
    }
    save_mmp_evidence(rows, args.out, metadata=metadata)
    report = validate_mmp_evidence(rows)
    report["metadata"] = metadata
    Path(args.report_out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report_out).write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    if args.write_db:
        conn = initialize_database(args.db_out)
        try:
            insert_mmp_transform_evidence(conn, rows)
        finally:
            conn.close()

    print(json.dumps({key: value for key, value in report.items() if key != "issues"}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
