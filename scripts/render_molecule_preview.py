from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rdkit.Chem import Draw  # noqa: E402

from localmedchem.chemistry import standardize_molecule  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a high-resolution molecule preview PNG for the native UI.")
    parser.add_argument("--smiles", required=True)
    parser.add_argument("--output", default=str(ROOT / "data" / "projects" / "demo" / "native_molecule_preview.png"))
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=420)
    args = parser.parse_args()
    mol = standardize_molecule(args.smiles)
    image = Draw.MolToImage(mol, size=(args.width, args.height), kekulize=True)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)
    payload = {
        "status": "rendered",
        "output": str(output.resolve()),
        "width": args.width,
        "height": args.height,
        "smiles": args.smiles,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
