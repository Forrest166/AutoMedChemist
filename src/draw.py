from __future__ import annotations

from rdkit import Chem
from rdkit.Chem import rdDepictor
from rdkit.Chem.Draw import rdMolDraw2D


def mol_to_svg(
    mol: Chem.Mol,
    width: int = 420,
    height: int = 280,
    highlight_atoms: list[int] | None = None,
) -> str:
    draw_mol = Chem.Mol(mol)
    rdDepictor.Compute2DCoords(draw_mol)
    drawer = rdMolDraw2D.MolDraw2DSVG(width, height)
    options = drawer.drawOptions()
    options.clearBackground = False
    drawer.DrawMolecule(draw_mol, highlightAtoms=highlight_atoms or [])
    drawer.FinishDrawing()
    return drawer.GetDrawingText().replace("svg:", "")


def smiles_to_svg(smiles: str | None, *, width: int = 240, height: int = 160) -> str | None:
    if not smiles:
        return None
    mol = Chem.MolFromSmiles(str(smiles))
    if mol is None:
        return None
    try:
        return mol_to_svg(mol, width=width, height=height)
    except Exception:
        return None
