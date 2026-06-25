from __future__ import annotations

from dataclasses import asdict, dataclass, field

from rdkit import Chem

from .chemistry import ChemistryError, canonical_smiles, get_single_attachment, mol_from_smiles
from .sites import ModificationSite


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    smiles: str
    substituent_id: str
    substituent_name: str
    substituent_smiles: str
    site_id: str
    site_type: str
    replacement_label: str
    enumeration_type: str = "substituent_scan"
    functional_rule_id: str | None = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def _remove_leaving_atom(parent: Chem.Mol, site: ModificationSite) -> tuple[Chem.Mol, int]:
    if site.leaving_atom_idx is None:
        return Chem.Mol(parent), site.atom_idx

    rw = Chem.RWMol(parent)
    leaving_idx = site.leaving_atom_idx
    anchor_idx = site.atom_idx
    rw.RemoveAtom(leaving_idx)
    if leaving_idx < anchor_idx:
        anchor_idx -= 1
    mol = rw.GetMol()
    Chem.SanitizeMol(mol)
    return mol, anchor_idx


def attach_substituent(parent: Chem.Mol, site: ModificationSite, substituent_smiles: str) -> Chem.Mol:
    parent_no_leaving, anchor_idx = _remove_leaving_atom(parent, site)
    fragment = mol_from_smiles(substituent_smiles)
    dummy_idx, attach_idx = get_single_attachment(fragment)

    offset = parent_no_leaving.GetNumAtoms()
    combined = Chem.CombineMols(parent_no_leaving, fragment)
    rw = Chem.RWMol(combined)
    rw.AddBond(anchor_idx, offset + attach_idx, Chem.BondType.SINGLE)
    rw.RemoveAtom(offset + dummy_idx)
    candidate = rw.GetMol()
    Chem.SanitizeMol(candidate)
    return candidate


def enumerate_candidates(
    parent: Chem.Mol,
    site: ModificationSite,
    substituents: list[dict],
    max_candidates: int | None = None,
) -> tuple[list[Candidate], list[dict]]:
    candidates: list[Candidate] = []
    errors: list[dict] = []
    seen: set[str] = set()

    for record in substituents:
        try:
            mol = attach_substituent(parent, site, record["smiles"])
            smiles = canonical_smiles(mol)
            if smiles in seen:
                continue
            seen.add(smiles)
            replacement = "H"
            if site.leaving_atom_symbol:
                replacement = site.leaving_atom_symbol
            candidate_no = len(candidates) + 1
            candidates.append(
                Candidate(
                    candidate_id=f"C{candidate_no:04d}",
                    smiles=smiles,
                    substituent_id=record["substituent_id"],
                    substituent_name=record["name"],
                    substituent_smiles=record["smiles"],
                    site_id=site.site_id,
                    site_type=site.site_type,
                    replacement_label=f"{replacement}->{record.get('short_name') or record['name']}",
                )
            )
            if max_candidates is not None and len(candidates) >= max_candidates:
                break
        except Exception as exc:
            errors.append(
                {
                    "substituent_id": record.get("substituent_id"),
                    "name": record.get("name"),
                    "error": str(exc),
                }
            )

    if not candidates and errors:
        raise ChemistryError(f"No candidates could be generated; first error: {errors[0]}")
    return candidates, errors
