from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.evidence_confidence import build_endpoint_family_residual_model, write_endpoint_family_residual_model  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build endpoint-family residual model from evidence confidence report.")
    parser.add_argument("--report", default=str(ROOT / "data" / "substituents" / "evidence_confidence_report.json"))
    parser.add_argument("--json-out", default=str(ROOT / "data" / "substituents" / "endpoint_family_residual_model.json"))
    args = parser.parse_args()

    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    model = build_endpoint_family_residual_model(report)
    write_endpoint_family_residual_model(model, args.json_out)
    print(json.dumps(model, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
