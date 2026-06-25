from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.iteration_package import (  # noqa: E402
    build_latest_iteration_comparison,
    compare_next_design_iterations,
    load_iteration_manifest,
    write_iteration_comparison_report,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare next-design iteration manifests.")
    parser.add_argument("--base", default="")
    parser.add_argument("--head", default="")
    parser.add_argument("--iteration-root", default=str(ROOT / "data" / "projects" / "iterations"))
    parser.add_argument("--output", default=str(ROOT / "data" / "projects" / "demo" / "iteration_comparison_report.json"))
    args = parser.parse_args()

    if args.base and args.head:
        report = compare_next_design_iterations(load_iteration_manifest(args.base), load_iteration_manifest(args.head))
        report["status"] = "compared"
    else:
        report = build_latest_iteration_comparison(output_root=args.iteration_root)
    write_iteration_comparison_report(report, args.output)
    print(
        json.dumps(
            {
                "output": str(Path(args.output).resolve()),
                "status": report.get("status"),
                "base_iteration_id": report.get("base_iteration_id"),
                "head_iteration_id": report.get("head_iteration_id"),
                "changed_asset_count": report.get("changed_asset_count", 0),
                "metric_deltas": report.get("metric_deltas") or {},
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
