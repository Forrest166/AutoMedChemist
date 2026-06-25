from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.promotion_freeze_package import build_profile_promotion_freeze_package  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a profile promotion freeze package.")
    parser.add_argument("--project-name", default="demo_learning")
    parser.add_argument("--freeze-id", default="")
    parser.add_argument("--output-root", default=str(ROOT / "data" / "projects" / "promotion_freezes"))
    parser.add_argument("--no-copy", action="store_true")
    args = parser.parse_args()
    manifest = build_profile_promotion_freeze_package(
        root=ROOT,
        project_name=args.project_name,
        freeze_id=args.freeze_id or None,
        output_root=args.output_root,
        copy_assets=not args.no_copy,
    )
    print(json.dumps({key: manifest.get(key) for key in ["freeze_id", "manifest_path", "present_asset_count", "missing_asset_count"]}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
