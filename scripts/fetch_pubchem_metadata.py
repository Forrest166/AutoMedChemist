from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import requests
from rdkit import Chem
from rdkit.Chem import Crippen, Descriptors, Lipinski, rdMolDescriptors

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.library import load_records  # noqa: E402


DEFAULT_SEEDS = [
    ROOT / "data" / "seeds" / "core_substituent_seed.yaml",
    ROOT / "data" / "seeds" / "pubchem_expansion_seed.yaml",
]


PROPERTIES = ",".join(
    [
        "CanonicalSMILES",
        "MolecularFormula",
        "MolecularWeight",
        "InChIKey",
        "IUPACName",
        "XLogP",
        "TPSA",
        "HBondDonorCount",
        "HBondAcceptorCount",
        "RotatableBondCount",
    ]
)


def parse_seed_paths(value: str) -> list[Path]:
    return [Path(part.strip()) for part in value.replace(";", ",").split(",") if part.strip()]


def local_fallback_properties(record: dict) -> dict:
    mol = Chem.MolFromSmiles(record["smiles"])
    if mol is None:
        return {}
    return {
        "CanonicalSMILES": Chem.MolToSmiles(mol, canonical=True),
        "MolecularFormula": rdMolDescriptors.CalcMolFormula(mol),
        "MolecularWeight": round(float(Descriptors.MolWt(mol)), 4),
        "InChIKey": None,
        "IUPACName": record.get("name"),
        "XLogP": round(float(Crippen.MolLogP(mol)), 4),
        "TPSA": round(float(rdMolDescriptors.CalcTPSA(mol)), 4),
        "HBondDonorCount": int(Lipinski.NumHDonors(mol)),
        "HBondAcceptorCount": int(Lipinski.NumHAcceptors(mol)),
        "RotatableBondCount": int(Lipinski.NumRotatableBonds(mol)),
    }


def fetch_one(query: str, record: dict, timeout: float = 20.0, retries: int = 2, allow_local_fallback: bool = True) -> dict:
    url = (
        "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/"
        f"{quote(query)}/property/{PROPERTIES}/JSON"
    )
    fetched_at = datetime.now(timezone.utc).isoformat()
    payload = {
        "query": query,
        "url": url,
        "status_code": None,
        "fetched_at": fetched_at,
    }
    for attempt in range(retries + 1):
        try:
            response = requests.get(url, timeout=timeout, headers={"User-Agent": "AutoMedChemist/0.1"})
            payload["status_code"] = response.status_code
            if response.ok:
                data = response.json()
                props = data.get("PropertyTable", {}).get("Properties", [])
                payload["properties"] = props[0] if props else {}
                payload["metadata_source"] = "PubChem PUG-REST"
                return payload
            payload["error"] = response.text[:500]
        except Exception as exc:
            payload["error"] = str(exc)
        if attempt < retries:
            time.sleep(1.5 * (attempt + 1))

    if allow_local_fallback:
        payload["properties"] = local_fallback_properties(record)
        payload["metadata_source"] = "RDKit local fallback"
        payload["fallback_reason"] = payload.get("error") or f"HTTP {payload.get('status_code')}"
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch public PubChem metadata for curated substituent seeds.")
    parser.add_argument("--seed", default=";".join(str(path) for path in DEFAULT_SEEDS))
    parser.add_argument("--output", default=str(ROOT / "data" / "raw" / "pubchem_substituent_metadata.json"))
    parser.add_argument("--sleep", type=float, default=0.12)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--no-local-fallback", action="store_true")
    args = parser.parse_args()

    seed_paths = [path for path in parse_seed_paths(args.seed) if path.exists()]
    records = load_records(seed_paths)
    if args.limit is not None:
        records = records[: args.limit]

    results = {}
    for idx, record in enumerate(records, start=1):
        source = record.get("source", {})
        query = str(source.get("pubchem_query") or record.get("name"))
        print(f"[{idx}/{len(records)}] PubChem query: {query}")
        results[record["substituent_id"]] = fetch_one(
            query,
            record,
            retries=args.retries,
            allow_local_fallback=not args.no_local_fallback,
        )
        time.sleep(args.sleep)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, indent=2, sort_keys=True), encoding="utf-8")
    ok = sum(1 for item in results.values() if item.get("properties"))
    print(f"Wrote {output} with {ok}/{len(results)} successful metadata hits.")


if __name__ == "__main__":
    main()
