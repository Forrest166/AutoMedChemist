from __future__ import annotations

from dataclasses import asdict, dataclass

from rdkit import Chem
from rdkit.Chem import Crippen, Descriptors, Lipinski, QED, rdMolDescriptors


class ChemistryError(ValueError):
    """Raised when a molecule cannot be parsed or standardized."""


@dataclass(frozen=True)
class DescriptorSet:
    smiles: str
    mw: float
    exact_mw: float
    clogp: float
    tpsa: float
    hbd: int
    hba: int
    rotatable_bonds: int
    heavy_atom_count: int
    ring_count: int
    aromatic_ring_count: int
    formal_charge: int
    fsp3: float
    qed: float | None

    def to_dict(self) -> dict:
        return asdict(self)


def mol_from_smiles(smiles: str) -> Chem.Mol:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ChemistryError(f"Invalid SMILES: {smiles}")
    return mol


def standardize_molecule(smiles: str) -> Chem.Mol:
    mol = mol_from_smiles(smiles)
    try:
        from rdkit.Chem.MolStandardize import rdMolStandardize

        mol = rdMolStandardize.Cleanup(mol)
        mol = rdMolStandardize.FragmentParent(mol)
        mol = rdMolStandardize.Uncharger().uncharge(mol)
    except Exception:
        # RDKit builds differ slightly; basic sanitization is still useful.
        pass
    Chem.SanitizeMol(mol)
    return mol


def canonical_smiles(mol: Chem.Mol) -> str:
    return Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True)


def canonicalize_smiles(smiles: str) -> str:
    return canonical_smiles(mol_from_smiles(smiles))


def formal_charge(mol: Chem.Mol) -> int:
    return int(sum(atom.GetFormalCharge() for atom in mol.GetAtoms()))


def calculate_descriptors(mol: Chem.Mol) -> DescriptorSet:
    smiles = canonical_smiles(mol)
    try:
        qed = float(QED.qed(mol))
    except Exception:
        qed = None
    return DescriptorSet(
        smiles=smiles,
        mw=round(float(Descriptors.MolWt(mol)), 4),
        exact_mw=round(float(Descriptors.ExactMolWt(mol)), 4),
        clogp=round(float(Crippen.MolLogP(mol)), 4),
        tpsa=round(float(rdMolDescriptors.CalcTPSA(mol)), 4),
        hbd=int(Lipinski.NumHDonors(mol)),
        hba=int(Lipinski.NumHAcceptors(mol)),
        rotatable_bonds=int(Lipinski.NumRotatableBonds(mol)),
        heavy_atom_count=int(mol.GetNumHeavyAtoms()),
        ring_count=int(rdMolDescriptors.CalcNumRings(mol)),
        aromatic_ring_count=int(rdMolDescriptors.CalcNumAromaticRings(mol)),
        formal_charge=formal_charge(mol),
        fsp3=round(float(rdMolDescriptors.CalcFractionCSP3(mol)), 4),
        qed=round(qed, 4) if qed is not None else None,
    )


def count_attachment_points(mol: Chem.Mol) -> int:
    return sum(1 for atom in mol.GetAtoms() if atom.GetAtomicNum() == 0)


def get_single_attachment(mol: Chem.Mol) -> tuple[int, int]:
    dummy_atoms = [atom for atom in mol.GetAtoms() if atom.GetAtomicNum() == 0]
    if len(dummy_atoms) != 1:
        raise ChemistryError(f"Expected exactly one attachment point, found {len(dummy_atoms)}")
    dummy = dummy_atoms[0]
    neighbors = list(dummy.GetNeighbors())
    if len(neighbors) != 1:
        raise ChemistryError("Attachment dummy must have exactly one neighbor")
    return dummy.GetIdx(), neighbors[0].GetIdx()


def calculate_substituent_descriptors(smiles: str) -> dict:
    mol = mol_from_smiles(smiles)
    desc = calculate_descriptors(mol).to_dict()
    desc["fragment_mw"] = desc.pop("mw")
    desc["attachment_count"] = count_attachment_points(mol)
    desc["heavy_atom_count"] = sum(1 for atom in mol.GetAtoms() if atom.GetAtomicNum() > 1)
    return desc

