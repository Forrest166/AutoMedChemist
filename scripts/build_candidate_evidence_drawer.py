from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.candidate_evidence_drawer import build_candidate_evidence_drawer, write_candidate_evidence_drawer  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build native candidate evidence drawer rows.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo")
    parser.add_argument("--candidates-csv", default=None)
    parser.add_argument("--max-rows", type=int, default=160)
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--csv-out", default=None)
    parser.add_argument("--markdown-out", default=str(ROOT / "docs/candidate_evidence_drawer.md"))
    args = parser.parse_args()
    report = build_candidate_evidence_drawer(root=args.root, project_name=args.project_name, candidates_csv=args.candidates_csv, max_rows=args.max_rows)
    json_out = args.json_out or str(ROOT / "data" / "projects" / args.project_name / "candidate_evidence_drawer.json")
    csv_out = args.csv_out or str(ROOT / "data" / "projects" / args.project_name / "candidate_evidence_drawer.csv")
    write_candidate_evidence_drawer(report, json_path=json_out, csv_path=csv_out, markdown_path=args.markdown_out)
    print(json.dumps({"status": report.get("status"), "row_count": report.get("row_count"), "json_out": str(Path(json_out).resolve())}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
