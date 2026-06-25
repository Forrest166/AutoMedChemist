from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.chemistry import calculate_descriptors, standardize_molecule  # noqa: E402
from localmedchem.sites import detect_modification_sites  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Detect local modification sites for the native shell.")
    parser.add_argument("--smiles", required=True)
    args = parser.parse_args()
    mol = standardize_molecule(args.smiles)
    sites = [site.to_dict() for site in detect_modification_sites(mol)]
    print(
        json.dumps(
            {
                "status": "ready",
                "parent_smiles": args.smiles,
                "parent_properties": calculate_descriptors(mol).to_dict(),
                "site_count": len(sites),
                "sites": sites,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
