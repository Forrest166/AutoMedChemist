from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.iteration_package import build_next_design_iteration_package  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Package the next-design iteration with report snapshots and a manifest.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project-name", default="demo_learning")
    parser.add_argument("--package-id", default="")
    parser.add_argument("--output-root", default=str(ROOT / "data" / "projects" / "iterations"))
    parser.add_argument("--no-copy-assets", action="store_true")
    args = parser.parse_args()

    manifest = build_next_design_iteration_package(
        root=args.root,
        project_name=args.project_name or None,
        package_id=args.package_id or None,
        output_root=args.output_root,
        copy_assets=not args.no_copy_assets,
    )
    print(
        json.dumps(
            {
                "iteration_id": manifest.get("iteration_id"),
                "manifest_path": manifest.get("manifest_path"),
                "package_dir": manifest.get("package_dir"),
                "present_asset_count": manifest.get("present_asset_count"),
                "missing_asset_count": manifest.get("missing_asset_count"),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
