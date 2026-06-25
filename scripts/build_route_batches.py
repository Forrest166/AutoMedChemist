from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.batch_design import load_candidate_csv, write_route_batch_exports  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Group candidate exports into route-aware chemistry batches.")
    parser.add_argument("--candidates-csv", default=str(ROOT / "data" / "projects" / "demo" / "candidates.csv"))
    parser.add_argument("--out-dir", default=str(ROOT / "data" / "projects" / "demo" / "route_batches"))
    args = parser.parse_args()

    rows = load_candidate_csv(args.candidates_csv)
    report = write_route_batch_exports(rows, args.out_dir)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
