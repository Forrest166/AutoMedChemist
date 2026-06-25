from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.medchem_discussion_handoff import build_medchem_discussion_handoff, write_medchem_discussion_handoff  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a local medchem discussion handoff from candidate evidence and decision QA.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo")
    parser.add_argument("--max-rows", type=int, default=80)
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--csv-out", default=None)
    parser.add_argument("--markdown-out", default=str(ROOT / "docs/medchem_discussion_handoff.md"))
    args = parser.parse_args()
    report = build_medchem_discussion_handoff(root=args.root, project_name=args.project_name, max_rows=args.max_rows)
    json_out = args.json_out or str(ROOT / "data" / "projects" / args.project_name / "medchem_discussion_handoff.json")
    csv_out = args.csv_out or str(ROOT / "data" / "projects" / args.project_name / "medchem_discussion_handoff.csv")
    write_medchem_discussion_handoff(report, json_path=json_out, csv_path=csv_out, markdown_path=args.markdown_out)
    print(json.dumps({"status": report.get("status"), "row_count": report.get("row_count"), "json_out": str(Path(json_out).resolve())}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
