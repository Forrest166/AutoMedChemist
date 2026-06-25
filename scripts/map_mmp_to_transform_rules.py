from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.database import initialize_database, insert_transform_mmp_mappings  # noqa: E402
from localmedchem.mmp import load_mmp_evidence  # noqa: E402
from localmedchem.transform_mmp_mapping import (  # noqa: E402
    load_transform_mmp_mappings,
    map_mmp_to_transform_rules,
    validate_transform_mmp_mappings,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Map mined MMP variable transforms onto named functional transform rules.")
    parser.add_argument("--mmp-evidence", default=str(ROOT / "data" / "mmp" / "chembl_mmp_transform_evidence.yaml"))
    parser.add_argument("--mapping-rules", default=str(ROOT / "data" / "rules" / "transform_mmp_mapping.yaml"))
    parser.add_argument("--report-out", default=str(ROOT / "data" / "substituents" / "transform_mmp_mapping_report.json"))
    parser.add_argument("--db-out", default=str(ROOT / "data" / "localmedchem.sqlite"))
    parser.add_argument("--write-db", action="store_true")
    args = parser.parse_args()

    rows = map_mmp_to_transform_rules(
        load_mmp_evidence(args.mmp_evidence),
        load_transform_mmp_mappings(args.mapping_rules),
    )
    report = validate_transform_mmp_mappings(rows)
    report["mappings"] = rows
    Path(args.report_out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report_out).write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    if args.write_db:
        conn = initialize_database(args.db_out)
        try:
            insert_transform_mmp_mappings(conn, rows)
        finally:
            conn.close()

    print(json.dumps({key: value for key, value in report.items() if key != "issues"}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

