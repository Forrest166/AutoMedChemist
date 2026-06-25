from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.project_evidence_pack import build_project_evidence_pack, write_project_evidence_pack  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a project-focused medchem evidence pack without procurement/vendor expansion.")
    parser.add_argument("--db-path", default=str(ROOT / "data" / "localmedchem.sqlite"))
    parser.add_argument("--project-name", default="demo_learning")
    parser.add_argument("--output", default=str(ROOT / "data" / "projects" / "demo" / "project_evidence_pack.json"))
    parser.add_argument("--summary-csv", default=str(ROOT / "data" / "projects" / "demo" / "project_evidence_pack_summary.csv"))
    parser.add_argument("--max-public-signals", type=int, default=40)
    parser.add_argument("--max-residual-rows", type=int, default=20)
    args = parser.parse_args()

    report = build_project_evidence_pack(
        root=ROOT,
        db_path=args.db_path,
        project_name=args.project_name or None,
        max_public_signals=args.max_public_signals,
        max_residual_rows=args.max_residual_rows,
    )
    write_project_evidence_pack(report, args.output, summary_csv_path=args.summary_csv)
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "project_name": report.get("project_name"),
                "outcome_count": report.get("outcome_count"),
                "context_count": len(report.get("context_summary") or []),
                "top_public_signal_count": report.get("top_public_signal_count"),
                "evidence_gap_count": len(report.get("evidence_gaps") or []),
                "output": str(Path(args.output).resolve()),
                "summary_csv": str(Path(args.summary_csv).resolve()),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
