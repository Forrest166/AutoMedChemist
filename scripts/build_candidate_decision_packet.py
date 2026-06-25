from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.candidate_decisions import build_candidate_decision_packet, write_candidate_decision_packet  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a local candidate decision packet and decision-support export.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo")
    parser.add_argument("--drilldown-path", default=None)
    parser.add_argument("--board-path", default=None)
    parser.add_argument("--baseline-path", default=None)
    parser.add_argument("--visual-path", default=None)
    parser.add_argument("--max-rows", type=int, default=160)
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--csv-out", default=None)
    parser.add_argument("--export-csv-out", default=None)
    parser.add_argument("--markdown-out", default=str(ROOT / "docs/candidate_decision_packet.md"))
    args = parser.parse_args()
    report = build_candidate_decision_packet(
        root=args.root,
        project_name=args.project_name,
        drilldown_path=args.drilldown_path,
        board_path=args.board_path,
        baseline_path=args.baseline_path,
        visual_path=args.visual_path,
        max_rows=args.max_rows,
    )
    json_out = args.json_out or str(ROOT / "data" / "projects" / args.project_name / "candidate_decision_packet.json")
    csv_out = args.csv_out or str(ROOT / "data" / "projects" / args.project_name / "candidate_decision_packet.csv")
    export_csv_out = args.export_csv_out or str(ROOT / "data" / "projects" / args.project_name / "candidate_decision_export.csv")
    write_candidate_decision_packet(
        report,
        json_path=json_out,
        csv_path=csv_out,
        markdown_path=args.markdown_out,
        export_csv_path=export_csv_out,
    )
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "decision_count": report.get("decision_count"),
                "decision_counts": report.get("decision_counts"),
                "json_out": str(Path(json_out).resolve()),
                "export_csv_out": str(Path(export_csv_out).resolve()),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
