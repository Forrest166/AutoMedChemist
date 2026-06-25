from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.release_bundle import write_latest_release_checksum_report, write_release_bundle_checksum  # noqa: E402


def _latest_release_bundle(releases_dir: Path) -> Path:
    bundles = sorted(releases_dir.glob("localmedchem_release_*.zip"), key=lambda path: path.stat().st_mtime)
    if not bundles:
        raise FileNotFoundError(f"No release bundles found in {releases_dir}")
    return bundles[-1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Write a SHA-256 sidecar checksum for a LocalMedChem release bundle.")
    parser.add_argument("--bundle", default=None)
    parser.add_argument("--out", default=None)
    parser.add_argument("--json-out", default=str(ROOT / "data" / "releases" / "latest_release_checksum.json"))
    args = parser.parse_args()

    bundle = Path(args.bundle) if args.bundle else _latest_release_bundle(ROOT / "data" / "releases")
    if args.out:
        report = write_release_bundle_checksum(bundle, args.out)
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    else:
        report = write_latest_release_checksum_report(bundle, args.json_out)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
