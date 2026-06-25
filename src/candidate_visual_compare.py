from __future__ import annotations

import ast
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rdkit import Chem
from rdkit.Chem import Draw, rdDepictor, rdFMCS


DEFAULT_VISUAL_COMPARE_JSON = Path("data/projects/demo/candidate_visual_compare.json")
DEFAULT_VISUAL_COMPARE_CSV = Path("data/projects/demo/candidate_visual_compare.csv")
DEFAULT_VISUAL_COMPARE_MD = Path("docs/candidate_visual_compare.md")
DEFAULT_VISUAL_ASSET_DIR = Path("data/projects/demo/candidate_visual_compare")


def _resolve(root: Path, path: str | Path) -> Path:
    item = Path(path)
    return item if item.is_absolute() else root / item


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_name(value: object, fallback: str) -> str:
    raw = str(value or fallback)
    safe = "".join(ch if ch.isalnum() or ch in {"_", "-", "."} else "_" for ch in raw)
    return safe.strip("_") or fallback


def _first_text(row: dict, *keys: str) -> str:
    for key in keys:
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


def _property_delta_summary(row: dict) -> str:
    parts = []
    for label, key in [("dMW", "delta_mw"), ("dClogP", "delta_clogp"), ("dTPSA", "delta_tpsa")]:
        value = str(row.get(key) or "").strip()
        if value:
            parts.append(f"{label}={value}")
    return "; ".join(parts)


def _site_highlight_label(row: dict) -> str:
    site_class = _first_text(row, "site_class", "site_type")
    site_type = _first_text(row, "site_type", "site_id")
    replacement = _first_text(row, "replacement_label", "substituent_name", "substituent_smiles")
    parts = [part for part in [site_class, site_type, replacement] if part]
    return " | ".join(parts) or "site not annotated"


def _substitution_change_summary(row: dict) -> str:
    parts = []
    replacement = _first_text(row, "replacement_label", "substituent_name")
    if replacement:
        parts.append(f"replacement={replacement}")
    substituent = _first_text(row, "substituent_smiles")
    if substituent:
        parts.append(f"substituent={substituent}")
    replacement_class = _first_text(row, "replacement_class")
    if replacement_class:
        parts.append(f"class={replacement_class}")
    rule = _first_text(row, "functional_rule_id", "rule_id")
    if rule:
        parts.append(f"rule={rule}")
    direction = _first_text(row, "direction")
    if direction:
        parts.append(f"direction={direction}")
    delta = _property_delta_summary(row)
    if delta:
        parts.append(delta)
    return "; ".join(parts) or "substitution change not annotated"


def _structure_highlight_detail(row: dict, highlight_count: int, alignment_status: str) -> str:
    evidence_bits = [
        _first_text(row, "mmp_contradiction_flags", "evidence_conflict_flags"),
        _first_text(row, "site_class_governance_action"),
        _first_text(row, "endpoint_gate_decision"),
    ]
    evidence = "; ".join(bit for bit in evidence_bits if bit) or "no extra evidence flags"
    return (
        f"{_site_highlight_label(row)}; {_substitution_change_summary(row)}; "
        f"highlight_atoms={highlight_count}; alignment={alignment_status or 'unavailable'}; {evidence}"
    )


def _parse_literal_list(value: object, limit: int = 3) -> list[dict[str, Any]]:
    if not value:
        return []
    if isinstance(value, list):
        data = value
    else:
        try:
            data = ast.literal_eval(str(value))
        except Exception:
            return []
    if not isinstance(data, list):
        return []
    parsed = []
    for item in data[:limit]:
        if isinstance(item, dict):
            parsed.append(dict(item))
    return parsed


def _selected_rows(rows: list[dict[str, str]], candidate_ids: list[str] | None, max_candidates: int) -> list[dict[str, str]]:
    if candidate_ids:
        wanted = {str(item) for item in candidate_ids}
        selected = [row for row in rows if str(row.get("candidate_id") or "") in wanted]
    else:
        selected = sorted(rows, key=lambda row: (_float(row.get("rank"), 10_000), -_float(row.get("score"))))
    return selected[: max(1, int(max_candidates))]


def _evidence_examples(row: dict) -> dict[str, list[dict[str, Any]]]:
    mmp_examples = []
    for item in _parse_literal_list(row.get("mmp_top_examples"), limit=3):
        mmp_examples.append(
            {
                "transform_id": item.get("transform_id"),
                "match_type": item.get("match_type"),
                "pair_count": item.get("pair_count"),
                "mean_delta_clogp": item.get("mean_delta_clogp"),
                "mean_delta_tpsa": item.get("mean_delta_tpsa"),
                "example_molecule_ids": item.get("example_molecule_ids"),
                "source_smiles": item.get("source_smiles"),
                "target_smiles": item.get("target_smiles"),
                "endpoint_family": item.get("endpoint_family"),
                "assay_context": item.get("assay_context"),
                "source_confidence": item.get("source_confidence"),
                "contradiction_status": item.get("contradiction_status"),
            }
        )
    sar_examples = []
    for item in _parse_literal_list(row.get("sar_neighbor_examples"), limit=3):
        sar_examples.append(
            {
                "neighbor_id": item.get("neighbor_id"),
                "source_smiles": item.get("source_smiles"),
                "target_smiles": item.get("target_smiles"),
                "edge_weight": item.get("edge_weight"),
                "layer": item.get("layer"),
                "source_name": item.get("source_name"),
                "endpoint_family": item.get("endpoint_family"),
                "assay_context": item.get("assay_context"),
                "source_confidence": item.get("source_confidence"),
                "contradiction_status": item.get("contradiction_status"),
            }
        )
    return {"mmp_examples": mmp_examples, "sar_examples": sar_examples}


def _render_pair_thumbnail(
    *,
    source_smiles: object,
    target_smiles: object,
    output_dir: Path,
    filename: str,
    width: int,
    height: int,
) -> str:
    source = Chem.MolFromSmiles(str(source_smiles or ""))
    target = Chem.MolFromSmiles(str(target_smiles or ""))
    if source is None or target is None:
        return ""
    for mol in [source, target]:
        try:
            rdDepictor.Compute2DCoords(mol)
        except Exception:
            pass
    output_dir.mkdir(parents=True, exist_ok=True)
    image = Draw.MolsToGridImage(
        [source, target],
        molsPerRow=2,
        subImgSize=(max(120, int(width // 2)), max(120, int(height))),
        legends=["source", "candidate"],
    )
    out = output_dir / filename
    image.save(out)
    return str(out.resolve())


def _render_evidence_thumbnails(
    *,
    row: dict,
    examples: dict[str, list[dict[str, Any]]],
    output_dir: Path,
    width: int,
    height: int,
) -> dict[str, list[str]]:
    candidate_id = _safe_name(row.get("candidate_id"), "candidate")
    thumb_dir = output_dir / "evidence_examples" / candidate_id
    paths: dict[str, list[str]] = {"mmp_thumbnail_paths": [], "sar_thumbnail_paths": []}
    for idx, item in enumerate(examples.get("mmp_examples") or [], start=1):
        path = _render_pair_thumbnail(
            source_smiles=item.get("source_smiles"),
            target_smiles=item.get("target_smiles") or row.get("smiles"),
            output_dir=thumb_dir,
            filename=f"mmp_{idx}.png",
            width=width,
            height=height,
        )
        if path:
            paths["mmp_thumbnail_paths"].append(path)
    for idx, item in enumerate(examples.get("sar_examples") or [], start=1):
        path = _render_pair_thumbnail(
            source_smiles=item.get("source_smiles"),
            target_smiles=item.get("target_smiles") or row.get("smiles"),
            output_dir=thumb_dir,
            filename=f"sar_{idx}.png",
            width=width,
            height=height,
        )
        if path:
            paths["sar_thumbnail_paths"].append(path)
    return paths


def _evidence_depth_score(row: dict, examples: dict[str, list[dict[str, Any]]], thumbnails: dict[str, list[str]]) -> int:
    score = 0
    score += min(3, int(_float(row.get("mmp_precedent_count"), 0) > 0) + len(examples.get("mmp_examples") or []))
    score += min(3, int(_float(row.get("sar_neighborhood_count"), 0) > 0) + len(examples.get("sar_examples") or []))
    score += min(2, len(thumbnails.get("mmp_thumbnail_paths") or []) + len(thumbnails.get("sar_thumbnail_paths") or []))
    if row.get("candidate_explanation_summary") or row.get("why_recommended"):
        score += 1
    if row.get("mmp_contradiction_flags"):
        score -= 1
    return max(0, score)


def _evidence_context_summary(row: dict, examples: dict[str, list[dict[str, Any]]]) -> str:
    values = []
    for key in ["target_family", "endpoint_family", "assay_context", "mmp_contradiction_flags"]:
        value = str(row.get(key) or "").strip()
        if value and value not in values:
            values.append(value)
    for item in [*(examples.get("mmp_examples") or []), *(examples.get("sar_examples") or [])]:
        for key in ["endpoint_family", "assay_context", "source_confidence", "contradiction_status"]:
            value = str(item.get(key) or "").strip()
            if value and value not in values:
                values.append(value)
    return "; ".join(values[:6])


def _alignment_context(rows: list[dict[str, str]]) -> dict[str, Any]:
    mols = []
    for row in rows:
        mol = Chem.MolFromSmiles(str(row.get("smiles") or ""))
        if mol is not None:
            mols.append(mol)
    if len(mols) < 2:
        return {"status": "single_molecule", "scaffold_smarts": "", "scaffold_atom_count": 0}
    try:
        mcs = rdFMCS.FindMCS(
            mols,
            timeout=5,
            ringMatchesRingOnly=True,
            completeRingsOnly=True,
            matchValences=False,
        )
    except Exception:
        return {"status": "mcs_failed", "scaffold_smarts": "", "scaffold_atom_count": 0}
    if not mcs.smartsString or mcs.numAtoms <= 1:
        return {"status": "no_common_scaffold", "scaffold_smarts": "", "scaffold_atom_count": 0}
    scaffold = Chem.MolFromSmarts(mcs.smartsString)
    if scaffold is None:
        return {"status": "invalid_scaffold", "scaffold_smarts": mcs.smartsString, "scaffold_atom_count": mcs.numAtoms}
    reference = Chem.Mol(mols[0])
    try:
        rdDepictor.Compute2DCoords(reference)
    except Exception:
        pass
    ref_match = reference.GetSubstructMatch(scaffold)
    return {
        "status": "aligned_to_mcs_scaffold",
        "scaffold_smarts": mcs.smartsString,
        "scaffold_atom_count": int(mcs.numAtoms),
        "reference_mol": reference,
        "reference_match": tuple(ref_match),
        "scaffold_mol": scaffold,
    }


def _aligned_mol_and_highlights(smiles: str, context: dict[str, Any]) -> tuple[Any | None, list[int], str]:
    mol = Chem.MolFromSmiles(str(smiles or ""))
    if mol is None:
        return None, [], "invalid_smiles"
    mol = Chem.Mol(mol)
    try:
        rdDepictor.Compute2DCoords(mol)
    except Exception:
        pass
    scaffold = context.get("scaffold_mol")
    reference = context.get("reference_mol")
    reference_match = tuple(context.get("reference_match") or ())
    if scaffold is None or not reference_match:
        return mol, [], str(context.get("status") or "unaligned")
    match = tuple(mol.GetSubstructMatch(scaffold))
    if not match:
        return mol, [], "no_scaffold_match"
    atom_map = list(zip(match, reference_match))
    try:
        rdDepictor.GenerateDepictionMatching2DStructure(mol, reference, atomMap=atom_map, acceptFailure=True)
    except TypeError:
        try:
            rdDepictor.GenerateDepictionMatching2DStructure(mol, reference, atomMap=atom_map)
        except Exception:
            pass
    except Exception:
        pass
    highlights = sorted(set(range(mol.GetNumAtoms())) - set(match))
    return mol, highlights, "aligned_to_mcs_scaffold"


def _render_candidate_image(row: dict, output_dir: Path, width: int, height: int, context: dict[str, Any]) -> str:
    smiles = str(row.get("smiles") or "")
    mol, highlights, _alignment_status = _aligned_mol_and_highlights(smiles, context)
    if mol is None:
        return ""
    output_dir.mkdir(parents=True, exist_ok=True)
    candidate_id = _safe_name(row.get("candidate_id"), "candidate")
    out = output_dir / f"{candidate_id}.png"
    image = Draw.MolToImage(mol, size=(int(width), int(height)), kekulize=True, highlightAtoms=highlights)
    image.save(out)
    return str(out.resolve())


def _render_grid(rows: list[dict], output_dir: Path, width: int, height: int, context: dict[str, Any]) -> str:
    mols = []
    legends = []
    highlight_lists = []
    for row in rows:
        mol, highlights, _alignment_status = _aligned_mol_and_highlights(str(row.get("smiles") or ""), context)
        if mol is None:
            continue
        mols.append(mol)
        highlight_lists.append(highlights)
        legends.append(f"{row.get('candidate_id') or '-'} | score {row.get('score') or '-'}")
    if not mols:
        return ""
    output_dir.mkdir(parents=True, exist_ok=True)
    grid = Draw.MolsToGridImage(
        mols,
        molsPerRow=min(4, max(1, len(mols))),
        subImgSize=(int(width), int(height)),
        legends=legends,
        highlightAtomLists=highlight_lists,
    )
    out = output_dir / "candidate_visual_grid.png"
    grid.save(out)
    return str(out.resolve())


def build_candidate_visual_compare(
    *,
    root: str | Path = ".",
    project_name: str = "demo",
    candidates_csv: str | Path | None = None,
    output_dir: str | Path | None = None,
    candidate_ids: list[str] | None = None,
    max_candidates: int = 8,
    image_width: int = 520,
    image_height: int = 360,
) -> dict[str, Any]:
    root_path = Path(root)
    csv_path = _resolve(root_path, candidates_csv or Path("data/projects") / project_name / "candidates.csv")
    asset_dir = _resolve(root_path, output_dir or Path("data/projects") / project_name / "candidate_visual_compare")
    source_rows = _read_csv_rows(csv_path)
    selected = _selected_rows(source_rows, candidate_ids, max_candidates=max_candidates)
    if not selected:
        return {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "missing_candidates",
            "project_name": project_name,
            "candidates_csv": str(csv_path),
            "candidate_count": 0,
            "rows": [],
            "grid_image_path": "",
            "recommended_next_actions": ["Generate candidates before building a visual comparison packet."],
            "blocked_scopes": ["procurement", "supplier_purchase", "real_experiment_feedback_auto_import"],
        }
    top_score = max(_float(row.get("score")) for row in selected)
    alignment = _alignment_context(selected)
    rows = []
    for row in selected:
        examples = _evidence_examples(row)
        thumbnails = _render_evidence_thumbnails(
            row=row,
            examples=examples,
            output_dir=asset_dir,
            width=max(260, image_width // 2),
            height=max(170, image_height // 2),
        )
        mol, highlight_atoms, alignment_status = _aligned_mol_and_highlights(str(row.get("smiles") or ""), alignment)
        image_path = _render_candidate_image(row, asset_dir, image_width, image_height, alignment)
        scaffold_atom_count = int(alignment.get("scaffold_atom_count") or 0)
        highlight_count = len(highlight_atoms)
        mmp_thumbnail_paths = thumbnails["mmp_thumbnail_paths"]
        sar_thumbnail_paths = thumbnails["sar_thumbnail_paths"]
        rows.append(
            {
                "candidate_id": row.get("candidate_id"),
                "rank": row.get("rank"),
                "score": row.get("score"),
                "score_delta_vs_top": round(_float(row.get("score")) - top_score, 4),
                "smiles": row.get("smiles"),
                "site_class": row.get("site_class") or row.get("site_type"),
                "enumeration_type": row.get("enumeration_type"),
                "replacement_label": row.get("replacement_label"),
                "substituent_name": row.get("substituent_name"),
                "substituent_smiles": row.get("substituent_smiles"),
                "replacement_class": row.get("replacement_class"),
                "functional_rule_id": row.get("functional_rule_id") or row.get("rule_id"),
                "delta_mw": row.get("delta_mw"),
                "delta_clogp": row.get("delta_clogp"),
                "delta_tpsa": row.get("delta_tpsa"),
                "similarity": row.get("similarity"),
                "mmp_precedent_strength": row.get("mmp_precedent_strength"),
                "mmp_precedent_count": row.get("mmp_precedent_count"),
                "sar_neighborhood_strength": row.get("sar_neighborhood_strength"),
                "sar_neighborhood_count": row.get("sar_neighborhood_count"),
                "candidate_explanation_summary": row.get("candidate_explanation_summary"),
                "why_recommended": row.get("why_recommended"),
                "why_review": row.get("why_review"),
                "mmp_examples": examples["mmp_examples"],
                "sar_examples": examples["sar_examples"],
                "mmp_example_count": len(examples["mmp_examples"]),
                "sar_example_count": len(examples["sar_examples"]),
                "mmp_thumbnail_paths": ";".join(mmp_thumbnail_paths),
                "sar_thumbnail_paths": ";".join(sar_thumbnail_paths),
                "evidence_depth_score": _evidence_depth_score(row, examples, thumbnails),
                "evidence_context_summary": _evidence_context_summary(row, examples),
                "alignment_status": alignment_status,
                "scaffold_smarts": alignment.get("scaffold_smarts") or "",
                "scaffold_atom_count": scaffold_atom_count,
                "highlight_atom_indices": highlight_atoms,
                "highlight_atom_count": highlight_count,
                "highlight_legend": (
                    f"{highlight_count} non-scaffold atoms highlighted against MCS core"
                    if mol is not None and scaffold_atom_count
                    else "alignment highlight unavailable"
                ),
                "highlight_color_legend": "Yellow atoms mark candidate-only/non-scaffold atoms against the aligned MCS core.",
                "site_highlight_label": _site_highlight_label(row),
                "substitution_change_summary": _substitution_change_summary(row),
                "structure_highlight_detail": _structure_highlight_detail(row, highlight_count, alignment_status),
                "site_change_token": "|".join(
                    part
                    for part in [
                        _first_text(row, "site_class", "site_type"),
                        _first_text(row, "replacement_label"),
                        _first_text(row, "substituent_smiles"),
                    ]
                    if part
                ),
                "image_path": image_path,
            }
        )
    grid_path = _render_grid(rows, asset_dir, image_width, image_height, alignment)
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready",
        "alignment_status": alignment.get("status"),
        "scaffold_smarts": alignment.get("scaffold_smarts") or "",
        "scaffold_atom_count": alignment.get("scaffold_atom_count") or 0,
        "project_name": project_name,
        "candidates_csv": str(csv_path),
        "asset_dir": str(asset_dir.resolve()),
        "candidate_count": len(rows),
        "grid_image_path": grid_path,
        "rows": rows,
        "recommended_next_actions": [
            "Use the aligned/highlighted grid image for first-pass visual triage of scaffold-conserved and edited atoms.",
            "Open candidate-specific images when reviewing MMP/SAR examples, property deltas, and highlighted non-scaffold regions.",
            "Keep this packet as local decision support; external operational workflows remain blocked.",
        ],
        "blocked_scopes": ["procurement", "supplier_purchase", "real_experiment_feedback_auto_import"],
    }


def render_candidate_visual_compare_markdown(report: dict) -> str:
    lines = [
        "# Candidate Visual Compare",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Project: `{report.get('project_name')}`",
        f"- Candidate count: `{report.get('candidate_count')}`",
        f"- Alignment: `{report.get('alignment_status')}`",
        f"- Scaffold atoms: `{report.get('scaffold_atom_count')}`",
        "",
    ]
    if report.get("grid_image_path"):
        lines.extend([f"![Candidate grid]({report.get('grid_image_path')})", ""])
    lines.extend(
        [
            "| ID | Score | Site class | dMW | dClogP | dTPSA | Highlight | Evidence | Depth | Thumbnails | Review |",
            "| --- | --- | --- | ---: | ---: | ---: | ---: | --- | ---: | ---: | --- |",
        ]
    )
    for row in report.get("rows") or []:
        evidence = f"MMP {row.get('mmp_precedent_strength') or '-'} / SAR {row.get('sar_neighborhood_strength') or '-'}"
        thumbnail_count = len([item for item in str(row.get("mmp_thumbnail_paths") or "").split(";") if item]) + len(
            [item for item in str(row.get("sar_thumbnail_paths") or "").split(";") if item]
        )
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("candidate_id") or ""),
                    str(row.get("score") or ""),
                    str(row.get("site_class") or ""),
                    str(row.get("delta_mw") or ""),
                    str(row.get("delta_clogp") or ""),
                    str(row.get("delta_tpsa") or ""),
                    str(row.get("highlight_atom_count") or ""),
                    evidence,
                    str(row.get("evidence_depth_score") or ""),
                    str(thumbnail_count),
                    str(row.get("structure_highlight_detail") or row.get("why_review") or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_candidate_visual_compare(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_VISUAL_COMPARE_JSON,
    csv_path: str | Path | None = DEFAULT_VISUAL_COMPARE_CSV,
    markdown_path: str | Path | None = DEFAULT_VISUAL_COMPARE_MD,
) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if csv_path:
        csv_file = Path(csv_path)
        csv_file.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = [
            "candidate_id",
            "rank",
            "score",
            "score_delta_vs_top",
            "smiles",
            "site_class",
            "enumeration_type",
            "replacement_label",
            "substituent_name",
            "substituent_smiles",
            "replacement_class",
            "functional_rule_id",
            "delta_mw",
            "delta_clogp",
            "delta_tpsa",
            "similarity",
            "mmp_precedent_strength",
            "mmp_precedent_count",
            "sar_neighborhood_strength",
            "sar_neighborhood_count",
            "candidate_explanation_summary",
            "why_recommended",
            "why_review",
            "mmp_example_count",
            "sar_example_count",
            "mmp_thumbnail_paths",
            "sar_thumbnail_paths",
            "evidence_depth_score",
            "evidence_context_summary",
            "alignment_status",
            "scaffold_atom_count",
            "highlight_atom_count",
            "highlight_legend",
            "highlight_color_legend",
            "site_highlight_label",
            "substitution_change_summary",
            "structure_highlight_detail",
            "site_change_token",
            "image_path",
        ]
        with csv_file.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in report.get("rows") or []:
                writer.writerow({field: row.get(field, "") for field in fieldnames})
    if markdown_path:
        md_file = Path(markdown_path)
        md_file.parent.mkdir(parents=True, exist_ok=True)
        md_file.write_text(render_candidate_visual_compare_markdown(report), encoding="utf-8")
