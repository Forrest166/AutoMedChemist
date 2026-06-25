from __future__ import annotations

from dataclasses import asdict, dataclass, replace

from rdkit import Chem


HALOGENS = {9: "F", 17: "Cl", 35: "Br", 53: "I"}


@dataclass(frozen=True)
class ModificationSite:
    site_id: str
    site_type: str
    atom_idx: int
    label: str
    description: str
    leaving_atom_idx: int | None = None
    leaving_atom_symbol: str | None = None
    recommended_direction_tags: tuple[str, ...] = ()
    compatible_connection_types: tuple[str, ...] = ()
    operation_type: str = "rgroup_enumeration"
    enumeration_ready: bool = True
    support_note: str = ""

    def to_dict(self) -> dict:
        data = asdict(self)
        data["recommended_direction_tags"] = list(self.recommended_direction_tags)
        data["compatible_connection_types"] = list(self.compatible_connection_types)
        return data


SITE_CONNECTION_TYPES = {
    "aromatic_CH": (
        "single_atom_substitution",
        "carbon_attachment",
        "heteroatom_attachment",
        "aryl_attachment",
        "heteroaryl_attachment",
        "ring_attachment",
    ),
    "aromatic_halide": (
        "single_atom_substitution",
        "carbon_attachment",
        "heteroatom_attachment",
        "aryl_attachment",
        "heteroaryl_attachment",
        "ring_attachment",
    ),
    "basic_amine": ("functional_group_replacement", "tail_attachment"),
    "ester_region": ("functional_group_replacement",),
    "amide_region": ("functional_group_replacement",),
    "sulfonamide_region": ("functional_group_replacement",),
    "acid_region": ("functional_group_replacement",),
    "heteroaryl_nitrogen": ("functional_group_replacement", "heteroaryl_attachment"),
    "charged_group": ("functional_group_replacement",),
    "methoxy_position": ("heteroatom_attachment", "functional_group_replacement"),
    "alkyl_terminal": (
        "single_atom_substitution",
        "carbon_attachment",
        "heteroatom_attachment",
        "ring_attachment",
    ),
    "linker_region": ("scaffold_replacement", "linker_replacement"),
    "ring_system": ("scaffold_replacement", "ring_replacement"),
}

SITE_OPERATION = {
    "aromatic_CH": ("rgroup_enumeration", True, "Supported by single-bond local R-group enumeration."),
    "aromatic_halide": ("rgroup_enumeration", True, "Supported by leaving-atom replacement enumeration."),
    "alkyl_terminal": ("rgroup_enumeration", True, "Supported as terminal-tail extension or scan."),
    "methoxy_position": ("soft_spot_rule", False, "Detected for metabolic soft-spot review; rule-based replacement follows next."),
    "ester_region": ("functional_group_replacement", False, "Detected for ester replacement rules; generic R-group enumeration is disabled."),
    "amide_region": ("functional_group_replacement", False, "Detected for amide bioisostere rules; generic R-group enumeration is disabled."),
    "sulfonamide_region": ("functional_group_replacement", False, "Detected for sulfonamide bioisostere or polarity review; generic R-group enumeration is disabled."),
    "acid_region": ("functional_group_replacement", False, "Detected for acid bioisostere rules; generic R-group enumeration is disabled."),
    "heteroaryl_nitrogen": ("heteroaryl_liability_review", False, "Detected for heteroaryl nitrogen liability and polarity review; generic R-group enumeration is disabled."),
    "charged_group": ("charged_group_review", False, "Detected for ionization-state boundary review; generic R-group enumeration is disabled."),
    "basic_amine": ("functional_group_replacement", False, "Detected for basicity/solubility review; dedicated amine rules follow next."),
    "linker_region": ("linker_replacement", False, "Detected for two-attachment linker replacement rules."),
    "ring_system": ("scaffold_replacement", False, "Detected for ring/scaffold replacement rules."),
}


def _is_aromatic_carbon(atom: Chem.Atom) -> bool:
    return atom.GetAtomicNum() == 6 and atom.GetIsAromatic()


def _is_amide_or_sulfonamide_nitrogen(atom: Chem.Atom) -> bool:
    if atom.GetAtomicNum() != 7:
        return False
    for nbr in atom.GetNeighbors():
        if nbr.GetAtomicNum() == 6:
            for bond in nbr.GetBonds():
                other = bond.GetOtherAtom(nbr)
                if other.GetAtomicNum() == 8 and bond.GetBondType() == Chem.BondType.DOUBLE:
                    return True
        if nbr.GetAtomicNum() == 16:
            double_o = 0
            for bond in nbr.GetBonds():
                other = bond.GetOtherAtom(nbr)
                if other.GetAtomicNum() == 8 and bond.GetBondType() == Chem.BondType.DOUBLE:
                    double_o += 1
            if double_o >= 1:
                return True
    return False


def _is_terminal_tail_carbon(atom: Chem.Atom) -> bool:
    if atom.GetAtomicNum() != 6 or atom.GetIsAromatic() or atom.IsInRing():
        return False
    heavy_neighbors = [nbr for nbr in atom.GetNeighbors() if nbr.GetAtomicNum() > 1]
    if len(heavy_neighbors) != 1 or atom.GetTotalNumHs() == 0:
        return False
    neighbor = heavy_neighbors[0]
    return neighbor.GetAtomicNum() in {6, 7}


def _is_two_attachment_linker_atom(atom: Chem.Atom) -> bool:
    if atom.GetAtomicNum() not in {6, 7, 8, 16} or atom.IsInRing():
        return False
    heavy_neighbors = [nbr for nbr in atom.GetNeighbors() if nbr.GetAtomicNum() > 1]
    if len(heavy_neighbors) != 2:
        return False
    bonds = [atom.GetOwningMol().GetBondBetweenAtoms(atom.GetIdx(), nbr.GetIdx()) for nbr in heavy_neighbors]
    if any(bond is None or bond.GetBondType() != Chem.BondType.SINGLE for bond in bonds):
        return False
    if atom.GetAtomicNum() == 6:
        if atom.GetHybridization() != Chem.HybridizationType.SP3:
            return False
        if atom.GetTotalNumHs() > 2:
            return False
    return True


def _is_heteroaryl_nitrogen(atom: Chem.Atom) -> bool:
    return atom.GetAtomicNum() == 7 and atom.GetIsAromatic()


def detect_modification_sites(mol: Chem.Mol) -> list[ModificationSite]:
    sites: list[ModificationSite] = []
    seen: set[tuple[str, int, int | None]] = set()

    def add_site(site_type: str, atom_idx: int, description: str, leaving_atom_idx: int | None = None) -> None:
        key = (site_type, atom_idx, leaving_atom_idx)
        if key in seen:
            return
        seen.add(key)
        site_no = len(sites) + 1
        leaving_symbol = None
        if leaving_atom_idx is not None:
            leaving_symbol = mol.GetAtomWithIdx(leaving_atom_idx).GetSymbol()
        direction_tags = {
            "aromatic_CH": ("small_scan", "increase_polarity", "electronics_scan", "metabolism_blocking"),
            "aromatic_halide": ("small_scan", "increase_polarity", "heteroaryl_scan", "electronics_scan"),
            "methoxy_position": ("metabolism_blocking", "reduce_lipophilicity"),
            "ester_region": ("improve_metabolic_stability", "reduce_hydrolysis"),
            "amide_region": ("amide_bioisostere_scan", "reduce_hydrolysis", "improve_metabolic_stability"),
            "sulfonamide_region": ("sulfonamide_bioisostere_scan", "reduce_polar_liability", "improve_permeability"),
            "acid_region": ("acid_bioisostere_scan", "improve_metabolic_stability", "increase_polarity"),
            "basic_amine": ("improve_solubility", "reduce_basicity"),
            "heteroaryl_nitrogen": ("heteroaryl_liability_scan", "electronics_scan", "polarity_tuning"),
            "charged_group": ("ionization_state_review", "reduce_charge", "permeability_review"),
            "alkyl_terminal": ("increase_polarity", "metabolism_blocking", "increase_size", "small_scan"),
            "linker_region": ("linker_replacement", "increase_polarity", "metabolism_blocking", "reduce_lipophilicity"),
            "ring_system": ("ring_contraction", "ring_expansion", "increase_polarity", "increase_3d_character"),
        }.get(site_type, ())
        operation_type, enumeration_ready, support_note = SITE_OPERATION.get(
            site_type, ("review_only", False, "Detected for review.")
        )
        sites.append(
            ModificationSite(
                site_id=f"R{site_no}",
                site_type=site_type,
                atom_idx=atom_idx,
                label=f"R{site_no} {site_type} atom {atom_idx}",
                description=description,
                leaving_atom_idx=leaving_atom_idx,
                leaving_atom_symbol=leaving_symbol,
                recommended_direction_tags=direction_tags,
                compatible_connection_types=SITE_CONNECTION_TYPES.get(site_type, ()),
                operation_type=operation_type,
                enumeration_ready=enumeration_ready,
                support_note=support_note,
            )
        )

    for atom in mol.GetAtoms():
        if _is_aromatic_carbon(atom) and atom.GetTotalNumHs() > 0:
            add_site("aromatic_CH", atom.GetIdx(), "Aromatic C-H suitable for local R-group scan.")

        if _is_aromatic_carbon(atom):
            for nbr in atom.GetNeighbors():
                if nbr.GetAtomicNum() in HALOGENS:
                    add_site(
                        "aromatic_halide",
                        atom.GetIdx(),
                        f"Aromatic {HALOGENS[nbr.GetAtomicNum()]} suitable for replacement scan.",
                        leaving_atom_idx=nbr.GetIdx(),
                    )

        if (
            atom.GetAtomicNum() == 7
            and atom.GetDegree() <= 3
            and not atom.GetIsAromatic()
            and atom.GetFormalCharge() == 0
            and not _is_amide_or_sulfonamide_nitrogen(atom)
        ):
            add_site("basic_amine", atom.GetIdx(), "Aliphatic amine region for basicity or solubility tuning.")

        if _is_terminal_tail_carbon(atom):
            add_site("alkyl_terminal", atom.GetIdx(), "Terminal aliphatic tail carbon suitable for local tail scan.")

        if _is_two_attachment_linker_atom(atom):
            add_site("linker_region", atom.GetIdx(), "Two-attachment linker atom suitable for linker replacement.")

        if _is_heteroaryl_nitrogen(atom):
            add_site("heteroaryl_nitrogen", atom.GetIdx(), "Heteroaryl nitrogen suitable for liability, polarity, or electronics review.")

        if atom.GetFormalCharge() != 0:
            add_site("charged_group", atom.GetIdx(), "Charged atom suitable for ionization-state boundary review.")

    methoxy = Chem.MolFromSmarts("[c:1][O:2][CH3:3]")
    for match in mol.GetSubstructMatches(methoxy):
        add_site("methoxy_position", match[1], "Aryl methoxy group; possible metabolic soft spot.")

    ester = Chem.MolFromSmarts("[CX3:1](=O)[OX2:2][#6:3]")
    for match in mol.GetSubstructMatches(ester):
        add_site("ester_region", match[0], "Ester region suitable for functional-group replacement.")

    acid = Chem.MolFromSmarts("[CX3:1](=O)[OX2H1,O-:2]")
    for match in mol.GetSubstructMatches(acid):
        add_site("acid_region", match[0], "Carboxylic acid region suitable for acid bioisostere replacement.")

    amide = Chem.MolFromSmarts("[CX3:1](=O)[NX3:2]")
    for match in mol.GetSubstructMatches(amide):
        add_site("amide_region", match[0], "Amide region suitable for amide bioisostere replacement.")

    sulfonamide = Chem.MolFromSmarts("[SX4:1](=[O:2])(=[O:3])[NX3:4]")
    for match in mol.GetSubstructMatches(sulfonamide):
        add_site("sulfonamide_region", match[0], "Sulfonamide region suitable for sulfonamide bioisostere or polarity review.")

    for ring in mol.GetRingInfo().AtomRings():
        if ring:
            add_site("ring_system", ring[0], "Ring system suitable for scaffold/ring replacement review.")

    priority = {
        "aromatic_CH": 0,
        "aromatic_halide": 1,
        "alkyl_terminal": 2,
        "methoxy_position": 3,
        "ester_region": 4,
        "amide_region": 5,
        "sulfonamide_region": 6,
        "acid_region": 7,
        "basic_amine": 8,
        "heteroaryl_nitrogen": 9,
        "charged_group": 10,
        "linker_region": 11,
        "ring_system": 12,
    }
    ordered = sorted(sites, key=lambda item: (priority.get(item.site_type, 99), item.atom_idx, item.leaving_atom_idx or -1))
    return [
        replace(site, site_id=f"R{idx}", label=f"R{idx} {site.site_type} atom {site.atom_idx}")
        for idx, site in enumerate(ordered, start=1)
    ]
