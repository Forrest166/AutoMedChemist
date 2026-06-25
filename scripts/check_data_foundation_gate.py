from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.data_foundation import build_data_foundation_report, evaluate_data_foundation_gate  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Check the LocalMedChem data-foundation CI gate.")
    parser.add_argument("--db", default=str(ROOT / "data" / "localmedchem.sqlite"))
    parser.add_argument("--report", default=str(ROOT / "data" / "substituents" / "data_foundation_report.json"))
    parser.add_argument("--gate-out", default=str(ROOT / "data" / "substituents" / "data_foundation_gate.json"))
    parser.add_argument("--strict-warnings", action="store_true", help="Fail CI on warnings as well as errors.")
    parser.add_argument("--min-ring-system-count", type=int, default=20000)
    args = parser.parse_args()

    report_path = Path(args.report)
    if report_path.exists():
        report = json.loads(report_path.read_text(encoding="utf-8"))
    else:
        report = build_data_foundation_report(ROOT, db_path=args.db, include_checksums=False)
    gate = evaluate_data_foundation_gate(report, min_ring_system_count=args.min_ring_system_count)
    out_path = Path(args.gate_out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(gate, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(gate, indent=2, sort_keys=True))
    if gate.get("status") == "error" or (args.strict_warnings and gate.get("status") == "warning"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
