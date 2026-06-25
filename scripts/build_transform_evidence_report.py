from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.transform_evidence import (  # noqa: E402
    build_transform_evidence_report,
    write_transform_evidence_markdown,
    write_transform_evidence_report,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build transform evidence report from priors and project feedback.")
    parser.add_argument("--db", default=str(ROOT / "data" / "localmedchem.sqlite"))
    parser.add_argument("--priors", default=str(ROOT / "data" / "rules" / "transform_priors.yaml"))
    parser.add_argument("--mmp-evidence", default=str(ROOT / "data" / "mmp" / "chembl_mmp_transform_evidence.yaml"))
    parser.add_argument("--project-name", default=None)
    parser.add_argument("--json-out", default=str(ROOT / "data" / "substituents" / "transform_evidence_report.json"))
    parser.add_argument("--md-out", default=str(ROOT / "data" / "substituents" / "transform_evidence_report.md"))
    args = parser.parse_args()

    report = build_transform_evidence_report(
        priors_path=args.priors,
        mmp_evidence_path=args.mmp_evidence,
        db_path=args.db,
        project_name=args.project_name,
    )
    write_transform_evidence_report(report, args.json_out)
    write_transform_evidence_markdown(report, args.md_out)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
