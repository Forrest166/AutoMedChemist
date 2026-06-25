from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.activity import auto_mmp_activity_summaries, load_activity_evidence, save_transform_activity_report, transform_activity_summaries  # noqa: E402
from localmedchem.database import initialize_database, insert_transform_activity_summaries  # noqa: E402
from localmedchem.mmp import load_mmp_evidence  # noqa: E402
from localmedchem.transform_mmp_mapping import load_transform_mmp_mappings, map_mmp_to_transform_rules  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Join transform MMP mappings with ChEMBL activity evidence.")
    parser.add_argument("--mmp-evidence", default=str(ROOT / "data" / "mmp" / "chembl_mmp_transform_evidence.yaml"))
    parser.add_argument("--mapping-rules", default=str(ROOT / "data" / "rules" / "transform_mmp_mapping.yaml"))
    parser.add_argument("--chembl-activity", default=str(ROOT / "data" / "activity" / "chembl_activity_evidence.yaml"))
    parser.add_argument("--output", default=str(ROOT / "data" / "substituents" / "transform_activity_report.json"))
    parser.add_argument("--include-auto-mmp", action="store_true", help="Also summarize all MMP transforms with side-specific example activity.")
    parser.add_argument("--max-auto-transforms", type=int, default=250)
    parser.add_argument("--db-out", default=str(ROOT / "data" / "localmedchem.sqlite"))
    parser.add_argument("--write-db", action="store_true")
    args = parser.parse_args()

    mmp_rows = load_mmp_evidence(args.mmp_evidence)
    mapping_rows = map_mmp_to_transform_rules(mmp_rows, load_transform_mmp_mappings(args.mapping_rules))
    activity_rows = load_activity_evidence(args.chembl_activity)
    summaries = transform_activity_summaries(
        mmp_rows=mmp_rows,
        mapping_rows=mapping_rows,
        activity_rows=activity_rows,
    )
    auto_summaries = (
        auto_mmp_activity_summaries(
            mmp_rows=mmp_rows,
            activity_rows=activity_rows,
            max_transforms=args.max_auto_transforms,
        )
        if args.include_auto_mmp
        else []
    )
    report = save_transform_activity_report(summaries, args.output, auto_rows=auto_summaries)
    if args.write_db:
        conn = initialize_database(args.db_out)
        try:
            insert_transform_activity_summaries(conn, [*summaries, *auto_summaries])
        finally:
            conn.close()
    print(json.dumps({key: value for key, value in report.items() if key not in {"summaries", "auto_summaries", "aggregates"}}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
