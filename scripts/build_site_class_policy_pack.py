from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.site_class_guidance import build_site_class_policy_pack, write_site_class_policy_pack  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build candidate-facing non-experimental site-class policy guidance.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--json-out", default=str(ROOT / "data" / "projects" / "demo" / "site_class_policy_pack.json"))
    parser.add_argument("--csv-out", default=str(ROOT / "data" / "projects" / "demo" / "site_class_policy_pack.csv"))
    args = parser.parse_args()
    report = build_site_class_policy_pack(root=args.root)
    write_site_class_policy_pack(report, json_path=args.json_out, csv_path=args.csv_out)
    print(json.dumps(report, indent=2, sort_keys=True))
    if report.get("status") != "ready":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
