from __future__ import annotations

import csv
import io
import tempfile
from pathlib import Path

from rdkit import Chem


def rows_to_csv_text(rows: list[dict]) -> str:
    if not rows:
        return ""
    handle = io.StringIO()
    fieldnames = list(rows[0].keys())
    for row in rows[1:]:
        for key in row.keys():
            if key not in fieldnames:
                fieldnames.append(key)
    writer = csv.DictWriter(handle, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return handle.getvalue()


def rows_to_sdf_text(rows: list[dict]) -> str:
    with tempfile.NamedTemporaryFile("w+", suffix=".sdf", delete=False, encoding="utf-8") as handle:
        temp_path = Path(handle.name)
    try:
        export_sdf(rows, temp_path)
        return temp_path.read_text(encoding="utf-8")
    finally:
        temp_path.unlink(missing_ok=True)


def export_csv(rows: list[dict], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    path.write_text(rows_to_csv_text(rows), encoding="utf-8")


def export_sdf(rows: list[dict], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = Chem.SDWriter(str(path))
    try:
        for row in rows:
            mol = Chem.MolFromSmiles(row["smiles"])
            if mol is None:
                continue
            for key, value in row.items():
                mol.SetProp(str(key), "" if value is None else str(value))
            writer.write(mol)
    finally:
        writer.close()
