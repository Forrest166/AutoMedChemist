from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_JSON = Path("data/projects/demo/candidate_structure_interpretation.json")
DEFAULT_CSV = Path("data/projects/demo/candidate_structure_interpretation.csv")
DEFAULT_MD = Path("docs/candidate_structure_interpretation.md")


SCORE_COMPONENTS = [
    ("score", "Total score"),
    ("property_score", "Property"),
    ("risk_score", "Risk"),
    ("transform_prior_score", "Transform prior"),
    ("mmp_precedent_score", "MMP"),
    ("sar_neighborhood_score", "SAR"),
    ("multi_objective_score", "Multi-objective"),
    ("endpoint_gate_score", "Endpoint gate"),
]


def _read_json(path: str | Path) -> dict:
    source = Path(path)
    if not source.exists():
        return {}
    try:
        payload = json.loads(source.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_csv(path: str | Path) -> list[dict[str, str]]:
    source = Path(path)
    if not source.exists():
        return []
    with source.open(encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _component_text(row: dict) -> str:
    parts = []
    for key, label in SCORE_COMPONENTS:
        value = str(row.get(key) or "").strip()
        if value:
            parts.append(f"{label}={value}")
    return "; ".join(parts)


def build_candidate_structure_interpretation(*, root: str | Path = ".", project_name: str = "demo") -> dict[str, Any]:
    root_path = Path(root)
    project_dir = root_path / "data" / "projects" / project_name
    candidates = _read_csv(project_dir / "candidates.csv")
    visual = _read_json(project_dir / "candidate_visual_compare.json")
    drilldown = _read_json(project_dir / "candidate_explanation_drilldown.json")
    visual_by_id = {str(row.get("candidate_id") or ""): dict(row) for row in visual.get("rows") or []}
    component_by_id: dict[str, list[dict]] = defaultdict(list)
    for row in drilldown.get("rows") or []:
        component_by_id[str(row.get("candidate_id") or "")].append(dict(row))
    rows: list[dict[str, Any]] = []
    locator_rows: list[dict[str, Any]] = []
    for candidate in candidates:
        candidate_id = str(candidate.get("candidate_id") or "").strip()
        if not candidate_id:
            continue
        visual_row = visual_by_id.get(candidate_id, {})
        components = component_by_id.get(candidate_id, [])
        score_components = _component_text(candidate)
        locator_count = 0
        for component in components:
            locator_count += 1
            locator_rows.append(
                {
                    "candidate_id": candidate_id,
                    "component_id": component.get("component_id") or component.get("component_label") or "",
                    "component_label": component.get("component_label") or component.get("component_id") or "",
                    "component_score": component.get("component_score") or "",
                    "component_status": component.get("component_status") or "",
                    "site_highlight_label": component.get("site_highlight_label") or visual_row.get("site_highlight_label") or "",
                    "highlight_atom_count": component.get("highlight_atom_count") or visual_row.get("highlight_atom_count") or "",
                    "locator_detail": component.get("right_panel_detail") or component.get("summary") or component.get("next_action") or "",
                }
            )
        rows.append(
            {
                "candidate_id": candidate_id,
                "before_after_supported": True,
                "candidate_smiles": candidate.get("smiles") or "",
                "site_class": candidate.get("site_class") or visual_row.get("site_class") or "",
                "site_highlight_label": visual_row.get("site_highlight_label") or "",
                "substitution_change_summary": visual_row.get("substitution_change_summary") or candidate.get("replacement_label") or "",
                "structure_highlight_detail": visual_row.get("structure_highlight_detail") or "",
                "highlight_atom_count": visual_row.get("highlight_atom_count") or "",
                "score_component_summary": score_components,
                "score_component_locator_count": locator_count,
                "structure_image_path": visual_row.get("image_path") or visual_row.get("structure_image_path") or "",
                "next_action": "Click a score/evidence component in the native workbench to locate the same candidate 2D panel.",
            }
        )
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if rows else "empty",
        "mode": "candidate_structure_interpretation",
        "project_name": project_name,
        "row_count": len(rows),
        "candidate_count": len(rows),
        "score_component_locator_count": len(locator_rows),
        "rows": rows,
        "locator_rows": locator_rows,
        "blocked_scopes": ["procurement", "supplier_purchase", "real_experiment_feedback_auto_import"],
    }


def render_candidate_structure_interpretation_markdown(report: dict) -> str:
    lines = [
        "# Candidate Structure Interpretation",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Candidates: `{report.get('candidate_count')}`",
        f"- Component locators: `{report.get('score_component_locator_count')}`",
        "",
        "| Candidate | Site | Highlight | Change | Components | Locator Count |",
        "| --- | --- | --- | --- | --- | ---: |",
    ]
    for row in report.get("rows") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("candidate_id") or ""),
                    str(row.get("site_class") or ""),
                    str(row.get("site_highlight_label") or "").replace("|", "/"),
                    str(row.get("substitution_change_summary") or "").replace("|", "/"),
                    str(row.get("score_component_summary") or "").replace("|", "/"),
                    str(row.get("score_component_locator_count") or 0),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_candidate_structure_interpretation(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_JSON,
    csv_path: str | Path | None = DEFAULT_CSV,
    markdown_path: str | Path | None = DEFAULT_MD,
) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    fields = [
        "candidate_id",
        "before_after_supported",
        "candidate_smiles",
        "site_class",
        "site_highlight_label",
        "substitution_change_summary",
        "structure_highlight_detail",
        "highlight_atom_count",
        "score_component_summary",
        "score_component_locator_count",
        "structure_image_path",
        "next_action",
    ]
    if csv_path:
        csv_file = Path(csv_path)
        csv_file.parent.mkdir(parents=True, exist_ok=True)
        with csv_file.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for row in report.get("rows") or []:
                writer.writerow({field: row.get(field, "") for field in fields})
    if markdown_path:
        md_file = Path(markdown_path)
        md_file.parent.mkdir(parents=True, exist_ok=True)
        md_file.write_text(render_candidate_structure_interpretation_markdown(report), encoding="utf-8")
