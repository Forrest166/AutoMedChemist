from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.rgroup_feed_onboarding import (  # noqa: E402
    promote_rgroup_feed_drop_from_staging,
    write_rgroup_feed_drop_promotion_report,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Promote a validated staged R-group feed drop into governed feeds.")
    parser.add_argument("--staging-gate", default=str(ROOT / "data/substituents/rgroup_next_feed_drop_staging_gate.json"))
    parser.add_argument("--staging-report", default=str(ROOT / "data/substituents/rgroup_next_feed_drop_staging.json"))
    parser.add_argument("--staging-dir", default=str(ROOT / "data/replacements/feed_drops/next_rgroup_feed_drop"))
    parser.add_argument("--feed-dir", default=str(ROOT / "data/replacements/feeds"))
    parser.add_argument("--manifest", default=str(ROOT / "data/replacements/feed_source_manifest.yaml"))
    parser.add_argument("--json-out", default=str(ROOT / "data/substituents/rgroup_next_feed_drop_promotion.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data/substituents/rgroup_next_feed_drop_promotion.csv"))
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--fail-if-not-promoted", action="store_true")
    args = parser.parse_args()

    report = promote_rgroup_feed_drop_from_staging(
        staging_gate_path=args.staging_gate,
        staging_report_path=args.staging_report,
        staging_dir=args.staging_dir,
        feed_dir=args.feed_dir,
        manifest_path=args.manifest,
        overwrite=args.overwrite,
        dry_run=args.dry_run,
    )
    write_rgroup_feed_drop_promotion_report(report, json_path=args.json_out, csv_path=args.csv_out)
    print(json.dumps(report, indent=2, sort_keys=True))
    if args.fail_if_not_promoted and report.get("status") not in {"promoted", "dry_run_ready"}:
        raise SystemExit(1)
    if report.get("status") == "blocked":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
