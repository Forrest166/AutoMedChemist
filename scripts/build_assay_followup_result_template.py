from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.assay_followup_results import build_assay_followup_result_template  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a blank follow-up assay result template from assay triage.")
    parser.add_argument("--triage", default=str(ROOT / "data" / "projects" / "demo" / "assay_event_triage_report.json"))
    parser.add_argument("--output", default=str(ROOT / "data" / "projects" / "demo" / "assay_followup_results_template.csv"))
    args = parser.parse_args()
    report = build_assay_followup_result_template(triage_report_path=args.triage, output_path=args.output)
    print(json.dumps({key: report.get(key) for key in ["status", "template_row_count", "source_triage_event_count", "template_path"]}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
