from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml
from rdkit import Chem
from rdkit.Chem import BRICS

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from localmedchem.database import initialize_database, insert_candidate_substituents, insert_raw_source_records  # noqa: E402
from localmedchem.ingestion import candidate_id_for, infer_classes, infer_connection_type, infer_direction_tags, infer_property_tags, infer_risk  # noqa: E402
from localmedchem.staging import raw_records_from_payloads  # noqa: E402


CHEMBL_MOLECULE_URL = "https://www.ebi.ac.uk/chembl/api/data/molecule.json"


def phase_filter_params(source_filter: str, max_phase: int | None) -> dict:
    if max_phase is not None:
        return {"max_phase": max_phase}
    if source_filter == "approved":
        return {"max_phase": 4}
    if source_filter == "clinical":
        return {"max_phase__gte": 1}
    if source_filter == "preclinical":
        return {"max_phase": 0}
    return {}


def parse_molecule_filters(values: list[str]) -> dict:
    params = {}
    for item in values:
        if "=" not in item:
            raise ValueError(f"Expected --molecule-filter KEY=VALUE, got {item!r}")
        key, value = item.split("=", 1)
        params[key.strip()] = value.strip()
    return params


def fetch_chembl_molecules(
    limit: int,
    source_filter: str = "approved",
    max_phase: int | None = None,
    page_size: int = 100,
    offset: int = 0,
    molecule_filters: dict | None = None,
    timeout: float = 30.0,
) -> tuple[list[dict], list[dict], dict]:
    base_params = {
        "only": "molecule_chembl_id,pref_name,molecule_structures,molecule_properties,max_phase",
        **phase_filter_params(source_filter, max_phase),
        **(molecule_filters or {}),
    }
    molecules: list[dict] = []
    pages: list[dict] = []
    current_offset = offset
    headers = {"User-Agent": "AutoMedChemist/0.2"}

    while len(molecules) < limit:
        page_limit = min(page_size, limit - len(molecules))
        params = {**base_params, "limit": page_limit, "offset": current_offset}
        response = requests.get(CHEMBL_MOLECULE_URL, params=params, timeout=timeout, headers=headers)
        response.raise_for_status()
        payload = response.json()
        page_molecules = list(payload.get("molecules") or [])
        molecules.extend(page_molecules)
        pages.append(
            {
                "status_code": response.status_code,
                "source_url": response.url,
                "offset": current_offset,
                "limit": page_limit,
                "molecule_count": len(page_molecules),
            }
        )
        if len(page_molecules) < page_limit:
            break
        current_offset += page_limit

    return molecules, pages, base_params


def normalize_brics_fragment(fragment_smiles: str) -> str | None:
    mol = Chem.MolFromSmiles(fragment_smiles)
    if mol is None:
        return None
    dummy_atoms = [atom for atom in mol.GetAtoms() if atom.GetAtomicNum() == 0]
    if len(dummy_atoms) != 1:
        return None
    dummy_atoms[0].SetIsotope(0)
    dummy_atoms[0].SetAtomMapNum(1)
    try:
        Chem.SanitizeMol(mol)
    except Exception:
        return None
    return Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True)


def extract_fragments(
    molecules: list[dict],
    min_heavy_atoms: int = 2,
    max_heavy_atoms: int = 18,
    min_frequency: int = 1,
) -> list[dict]:
    counts: Counter[str] = Counter()
    examples: dict[str, set[str]] = defaultdict(set)
    names: dict[str, str] = {}

    for molecule in molecules:
        structures = molecule.get("molecule_structures") or {}
        smiles = structures.get("canonical_smiles")
        if not smiles:
            continue
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            continue
        try:
            fragments = BRICS.BRICSDecompose(mol, keepNonLeafNodes=False)
        except Exception:
            continue
        for fragment in fragments:
            normalized = normalize_brics_fragment(fragment)
            if not normalized:
                continue
            frag_mol = Chem.MolFromSmiles(normalized)
            if frag_mol is None:
                continue
            heavy_atoms = sum(1 for atom in frag_mol.GetAtoms() if atom.GetAtomicNum() > 1)
            if heavy_atoms < min_heavy_atoms or heavy_atoms > max_heavy_atoms:
                continue
            counts[normalized] += 1
            examples[normalized].add(molecule.get("molecule_chembl_id") or "")
            names.setdefault(normalized, f"ChEMBL fragment {normalized}")

    candidates = []
    for smiles, count in counts.most_common():
        if count < min_frequency:
            continue
        connection_type = infer_connection_type(smiles)
        classes = infer_classes(names[smiles], smiles, connection_type)
        candidate = {
            "candidate_id": candidate_id_for(Chem.MolToSmiles(Chem.MolFromSmiles(smiles), canonical=True), "chembl_fragment"),
            "name": names[smiles],
            "short_name": smiles,
            "smiles": smiles,
            "source_type": "chembl_fragment",
            "source_name": "ChEMBL",
            "source_record_id": ",".join(sorted(item for item in examples[smiles] if item)[:5]),
            "pubchem_query": names[smiles],
            "reference": "https://www.ebi.ac.uk/chembl/api/data/molecule",
            "class": classes,
            "direction_tags": infer_direction_tags(smiles, classes),
            "property_tags": infer_property_tags(smiles, classes),
            "risk": infer_risk(names[smiles], smiles, classes),
            "priority": {
                "mvp": True,
                "common_medchem": count >= 2,
                "default_rank": max(45, 115 - min(count, 40)),
            },
            "candidate_status": "staged",
            "review_tier": "needs_medchem_review",
            "chembl_frequency": count,
            "example_molecule_chembl_ids": sorted(item for item in examples[smiles] if item)[:10],
        }
        candidates.append(candidate)
    return candidates


def save_candidate_source(candidates: list[dict], output: Path, version: str = "chembl-0.1") -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "source_name": "ChEMBL",
        "version": version,
        "description": "BRICS one-attachment fragments mined from ChEMBL molecule records.",
        "candidates": candidates,
    }
    output.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=False), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch ChEMBL molecules and mine one-attachment BRICS fragments into staging candidates.")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--source-filter", choices=["approved", "clinical", "preclinical", "all"], default="approved")
    parser.add_argument("--max-phase", type=int, default=None)
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--molecule-filter", action="append", default=[], help="Additional ChEMBL API filter as KEY=VALUE.")
    parser.add_argument("--min-frequency", type=int, default=1)
    parser.add_argument("--min-heavy-atoms", type=int, default=2)
    parser.add_argument("--max-heavy-atoms", type=int, default=18)
    parser.add_argument("--max-candidates", type=int, default=80)
    parser.add_argument("--raw-out", default=str(ROOT / "data" / "raw" / "chembl_molecule_records.json"))
    parser.add_argument("--candidates-out", default=str(ROOT / "data" / "sources" / "chembl_fragment_candidates.yaml"))
    parser.add_argument("--db-out", default=str(ROOT / "data" / "localmedchem.sqlite"))
    parser.add_argument("--write-db", action="store_true")
    args = parser.parse_args()

    molecule_filters = parse_molecule_filters(args.molecule_filter)
    molecules, pages, query_params = fetch_chembl_molecules(
        limit=args.limit,
        source_filter=args.source_filter,
        max_phase=args.max_phase,
        page_size=args.page_size,
        offset=args.offset,
        molecule_filters=molecule_filters,
    )
    candidates = extract_fragments(
        molecules,
        min_heavy_atoms=args.min_heavy_atoms,
        max_heavy_atoms=args.max_heavy_atoms,
        min_frequency=args.min_frequency,
    )[: args.max_candidates]

    raw_path = Path(args.raw_out)
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_payload = {
        "source_name": "ChEMBL",
        "source_url": pages[0]["source_url"] if pages else CHEMBL_MOLECULE_URL,
        "status_code": pages[-1]["status_code"] if pages else None,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "query_params": query_params,
        "pages": pages,
        "molecule_count": len(molecules),
        "molecules": molecules,
    }
    raw_path.write_text(json.dumps(raw_payload, indent=2, sort_keys=True), encoding="utf-8")
    version_phase = args.max_phase if args.max_phase is not None else args.source_filter
    save_candidate_source(candidates, Path(args.candidates_out), version=f"chembl-{version_phase}-minfreq-{args.min_frequency}")

    if args.write_db:
        conn = initialize_database(args.db_out)
        try:
            insert_raw_source_records(
                conn,
                raw_records_from_payloads(
                    "ChEMBL",
                    molecules,
                    raw_payload["source_url"],
                    raw_payload["status_code"],
                ),
            )
            insert_candidate_substituents(conn, candidates)
        finally:
            conn.close()

    print(json.dumps({"molecule_count": len(molecules), "candidate_count": len(candidates), "raw_out": str(raw_path.resolve()), "candidates_out": str(Path(args.candidates_out).resolve())}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
