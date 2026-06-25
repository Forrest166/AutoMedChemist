from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from localmedchem.candidate_structure_interpretation import build_candidate_structure_interpretation


DEFAULT_JSON = Path("data/projects/demo/candidate_component_structure_locator.json")
DEFAULT_CSV = Path("data/projects/demo/candidate_component_structure_locator.csv")
DEFAULT_MD = Path("docs/candidate_component_structure_locator.md")
BLOCKED_SCOPES = ["procurement", "supplier_purchase", "real_experiment_feedback_auto_import"]


def _read_json(path: str | Path) -> dict:
    source = Path(path)
    if not source.exists():
        return {}
    try:
        payload = json.loads(source.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _safe_id(value: object) -> str:
    text = str(value or "").strip()
    return "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in text) or "component"


def _component_key(candidate_id: str, component_id: object, component_label: object) -> tuple[str, str, str]:
    return (
        str(candidate_id or "").strip(),
        str(component_id or "").strip().lower(),
        str(component_label or "").strip().lower(),
    )


def _split_ids(value: object) -> list[str]:
    return [part.strip() for part in str(value or "").replace(";", ",").split(",") if part.strip()]


def _locator_status(row: dict, structure_path: object) -> str:
    if row.get("site_highlight_label") and (row.get("structure_highlight_detail") or row.get("locator_detail")):
        return "linked_highlight"
    if structure_path and row.get("locator_detail"):
        return "linked_structure"
    if row.get("locator_detail"):
        return "metadata_route"
    return "needs_drilldown"


def build_candidate_component_structure_locator(*, root: str | Path = ".", project_name: str = "demo") -> dict[str, Any]:
    root_path = Path(root)
    project_dir = root_path / "data" / "projects" / project_name
    interpretation = _read_json(project_dir / "candidate_structure_interpretation.json")
    if not interpretation.get("rows") and not interpretation.get("locator_rows"):
        interpretation = build_candidate_structure_interpretation(root=root_path, project_name=project_name)
    drilldown = _read_json(project_dir / "candidate_explanation_drilldown.json")
    visual = _read_json(project_dir / "candidate_visual_compare.json")

    interpretation_by_id = {
        str(row.get("candidate_id") or ""): dict(row)
        for row in interpretation.get("rows") or []
        if row.get("candidate_id")
    }
    visual_by_id = {
        str(row.get("candidate_id") or ""): dict(row)
        for row in visual.get("rows") or []
        if row.get("candidate_id")
    }
    drilldown_by_key: dict[tuple[str, str, str], dict] = {}
    for row in drilldown.get("rows") or []:
        candidate_id = str(row.get("candidate_id") or "").strip()
        if not candidate_id:
            continue
        item = dict(row)
        drilldown_by_key[_component_key(candidate_id, item.get("component_id"), item.get("component_label"))] = item
        drilldown_by_key[_component_key(candidate_id, item.get("component_label"), item.get("component_id"))] = item

    rows: list[dict[str, Any]] = []
    for index, locator in enumerate(interpretation.get("locator_rows") or [], start=1):
        candidate_id = str(locator.get("candidate_id") or "").strip()
        if not candidate_id:
            continue
        component_id = locator.get("component_id") or locator.get("component_label") or f"component_{index}"
        component_label = locator.get("component_label") or component_id
        drilldown_row = drilldown_by_key.get(_component_key(candidate_id, component_id, component_label), {})
        interpretation_row = interpretation_by_id.get(candidate_id, {})
        visual_row = visual_by_id.get(candidate_id, {})
        merged = {**visual_row, **interpretation_row, **dict(locator), **drilldown_row}
        structure_path = (
            merged.get("structure_image_path")
            or merged.get("image_path")
            or interpretation_row.get("structure_image_path")
            or visual_row.get("image_path")
            or ""
        )
        component_target = merged.get("target_view") or "candidate_structure_panel"
        route_filter = merged.get("target_filter") or f"candidate_id={candidate_id};component_id={component_id}"
        locator_detail = (
            merged.get("right_panel_detail")
            or merged.get("locator_detail")
            or merged.get("summary")
            or merged.get("next_action")
            or merged.get("structure_highlight_detail")
            or ""
        )
        out_row = {
            "locator_id": f"CSL-{_safe_id(candidate_id)}-{_safe_id(component_id)}-{index:03d}",
            "candidate_id": candidate_id,
            "component_id": component_id,
            "component_label": component_label,
            "component_score": merged.get("component_score") or "",
            "component_status": merged.get("component_status") or "",
            "target_view": component_target,
            "target_filter": route_filter,
            "target_artifact": merged.get("target_artifact") or str(project_dir / "candidate_explanation_drilldown.json"),
            "structure_image_path": str(structure_path or ""),
            "before_after_supported": bool(interpretation_row.get("before_after_supported", True)),
            "component_to_structure_linked": True,
            "site_class": merged.get("site_class") or interpretation_row.get("site_class") or "",
            "site_highlight_label": merged.get("site_highlight_label") or "",
            "structure_highlight_detail": merged.get("structure_highlight_detail") or "",
            "highlight_atom_count": merged.get("highlight_atom_count") or "",
            "substitution_change_summary": merged.get("substitution_change_summary") or "",
            "locator_detail": locator_detail,
            "matched_candidate_ids": ";".join(_split_ids(merged.get("matched_candidate_ids") or candidate_id)),
            "locator_status": _locator_status({**merged, "locator_detail": locator_detail}, structure_path),
            "next_action": "Click this component in the native workbench to focus the candidate 2D before/after panel and explain the same score source.",
            "scope_note": "Local candidate explanation and structure inspection only.",
        }
        rows.append(out_row)

    status_counts = Counter(str(row.get("locator_status") or "unknown") for row in rows)
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if rows else "empty",
        "mode": "candidate_component_structure_locator",
        "project_name": project_name,
        "row_count": len(rows),
        "candidate_count": len({row.get("candidate_id") for row in rows}),
        "linked_component_count": sum(1 for row in rows if str(row.get("locator_status")) in {"linked_highlight", "linked_structure"}),
        "metadata_route_count": status_counts.get("metadata_route", 0),
        "needs_drilldown_count": status_counts.get("needs_drilldown", 0),
        "status_counts": dict(status_counts.most_common()),
        "rows": rows,
        "blocked_scopes": BLOCKED_SCOPES,
        "scope_note": "Local design/review structure explanation only; external operational workflows are out of scope.",
    }


def render_candidate_component_structure_locator_markdown(report: dict) -> str:
    lines = [
        "# Candidate Component Structure Locator",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Rows: `{report.get('row_count')}`",
        f"- Linked components: `{report.get('linked_component_count')}`",
        "",
        "| Candidate | Component | Status | Highlight | Structure | Detail |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in report.get("rows") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("candidate_id") or ""),
                    str(row.get("component_label") or row.get("component_id") or ""),
                    str(row.get("locator_status") or ""),
                    str(row.get("site_highlight_label") or "").replace("|", "/"),
                    str(Path(str(row.get("structure_image_path") or "")).name),
                    str(row.get("locator_detail") or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_candidate_component_structure_locator(
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
        "locator_id",
        "candidate_id",
        "component_id",
        "component_label",
        "component_score",
        "component_status",
        "target_view",
        "target_filter",
        "target_artifact",
        "structure_image_path",
        "before_after_supported",
        "component_to_structure_linked",
        "site_class",
        "site_highlight_label",
        "structure_highlight_detail",
        "highlight_atom_count",
        "substitution_change_summary",
        "locator_detail",
        "locator_status",
        "next_action",
        "scope_note",
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
        md_file.write_text(render_candidate_component_structure_locator_markdown(report), encoding="utf-8")
