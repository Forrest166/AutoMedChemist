from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_CANDIDATE_EXPLANATION_DRILLDOWN_JSON = Path("data/projects/demo/candidate_explanation_drilldown.json")
DEFAULT_CANDIDATE_EXPLANATION_DRILLDOWN_CSV = Path("data/projects/demo/candidate_explanation_drilldown.csv")
DEFAULT_CANDIDATE_EXPLANATION_DRILLDOWN_MD = Path("docs/candidate_explanation_drilldown.md")
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


def _by_candidate(report: dict, *, keys: tuple[str, ...] = ("candidate_id", "candidate_key", "source_id")) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    for row in report.get("rows") or []:
        if not isinstance(row, dict):
            continue
        for key in keys:
            candidate_id = str(row.get(key) or "").strip()
            if candidate_id:
                rows[candidate_id] = dict(row)
                break
    return rows


def _group_remediation(report: dict) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in report.get("rows") or []:
        if not isinstance(row, dict):
            continue
        candidate_id = str(row.get("candidate_id") or row.get("source_id") or "").strip()
        if not candidate_id:
            target_filter = str(row.get("target_filter") or "")
            for part in target_filter.split(";"):
                key, _, value = part.partition("=")
                if key.strip() == "candidate_id":
                    candidate_id = value.strip()
                    break
        if candidate_id:
            grouped[candidate_id].append(dict(row))
    return grouped


def _component_status(component_id: str, score: object, panel_row: dict, linked_row: dict, remediation_rows: list[dict]) -> str:
    try:
        value = float(score)
    except (TypeError, ValueError):
        value = 0.0
    if component_id == "remediation":
        open_count = int(float(panel_row.get("open_remediation_count") or 0))
        return "attention" if open_count > 0 else "ready"
    if component_id == "decision_qa":
        bucket = str(panel_row.get("qa_bucket") or linked_row.get("qa_bucket") or "").lower()
        return "ready" if bucket in {"clear", "ready", "evidence_supported"} else "attention"
    if component_id == "baseline":
        status = str(panel_row.get("baseline_lineage_status") or linked_row.get("lineage_status") or "").lower()
        return "ready" if status in {"", "unchanged", "stable", "current", "clear"} else "attention"
    if component_id == "evidence":
        return "ready" if value >= 60 and (panel_row.get("evidence_summary") or linked_row) else "attention"
    return "ready" if value >= 70 else "watch"


def _short(value: object, limit: int = 140) -> str:
    text = str(value or "").replace("\n", " ").strip()
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _task_ids(rows: list[dict]) -> str:
    ids: list[str] = []
    for row in rows:
        task_id = str(row.get("task_id") or "").strip()
        if task_id and task_id not in ids:
            ids.append(task_id)
    return ";".join(ids)


def _component_rows(
    *,
    project_dir: Path,
    panel_row: dict,
    drawer_row: dict,
    qa_row: dict,
    lineage_row: dict,
    remediation_rows: list[dict],
    visual_row: dict,
    board_row: dict,
) -> list[dict[str, Any]]:
    candidate_id = str(panel_row.get("candidate_id") or "").strip()
    task_ids = _task_ids(remediation_rows) or str(panel_row.get("remediation_task_ids") or "")
    structure_image_path = visual_row.get("image_path") or board_row.get("image_path") or str(project_dir / "candidate_visual_compare" / f"{candidate_id}.png")
    site_class = panel_row.get("site_class") or board_row.get("site_class") or drawer_row.get("site_class") or ""
    highlight_legend = board_row.get("highlight_legend") or visual_row.get("highlight_legend") or f"Use visual compare image to inspect {site_class or 'selected'} site context."
    highlight_atom_count = board_row.get("highlight_atom_count") or visual_row.get("highlight_atom_count") or ""
    components = [
        {
            "component_id": "score",
            "component_label": "Score",
            "component_score": panel_row.get("score_component", ""),
            "target_view": "candidate_table",
            "target_artifact": project_dir / "candidate_explanation_panel.json",
            "target_filter": f"candidate_id={candidate_id}",
            "summary": f"Rank={panel_row.get('rank') or '-'}; score={panel_row.get('score') or '-'}; vector={panel_row.get('explanation_score_vector') or '-'}",
            "next_action": "Review score contribution beside evidence, QA, baseline, and remediation components.",
            "linked_row_key": candidate_id,
        },
        {
            "component_id": "evidence",
            "component_label": "Evidence",
            "component_score": panel_row.get("evidence_component", ""),
            "target_view": "evidence_drawer",
            "target_artifact": project_dir / "candidate_evidence_drawer.json",
            "target_filter": f"candidate_id={candidate_id}",
            "summary": panel_row.get("evidence_summary") or drawer_row.get("evidence_context_summary") or drawer_row.get("drawer_summary") or "No drawer evidence summary.",
            "next_action": drawer_row.get("next_action") or "Open the evidence drawer for MMP/SAR support and limitations.",
            "linked_row_key": candidate_id,
        },
        {
            "component_id": "decision_qa",
            "component_label": "Decision QA",
            "component_score": panel_row.get("qa_component", ""),
            "target_view": "decision_qa",
            "target_artifact": project_dir / "candidate_decision_qa.json",
            "target_filter": f"candidate_id={candidate_id};qa_bucket={panel_row.get('qa_bucket') or qa_row.get('qa_bucket') or ''}",
            "summary": qa_row.get("qa_reason") or panel_row.get("qa_reason") or f"QA bucket={panel_row.get('qa_bucket') or '-'}",
            "next_action": qa_row.get("next_action") or "Resolve non-clear QA rows before discussion handoff.",
            "linked_row_key": candidate_id,
        },
        {
            "component_id": "baseline",
            "component_label": "Baseline",
            "component_score": panel_row.get("baseline_component", ""),
            "target_view": "baseline_lineage",
            "target_artifact": project_dir / "baseline_lineage_compare.json",
            "target_filter": f"candidate_id={candidate_id};lineage_status={panel_row.get('baseline_lineage_status') or lineage_row.get('lineage_status') or ''}",
            "summary": lineage_row.get("rationale") or f"Status={panel_row.get('baseline_lineage_status') or '-'}; fields={panel_row.get('baseline_changed_fields') or '-'}",
            "next_action": lineage_row.get("next_action") or "Open baseline lineage before pinning or rolling back a local baseline.",
            "linked_row_key": candidate_id,
        },
        {
            "component_id": "remediation",
            "component_label": "Remediation",
            "component_score": panel_row.get("remediation_component", ""),
            "target_view": "remediation",
            "target_artifact": project_dir / "candidate_remediation_queue.json",
            "target_filter": f"candidate_id={candidate_id};task_ids={task_ids}",
            "summary": f"Open tasks={panel_row.get('open_remediation_count') or 0}; task_ids={task_ids or 'none'}",
            "next_action": panel_row.get("next_action") or (remediation_rows[0].get("next_action") if remediation_rows else "No remediation stop-list item."),
            "linked_row_key": task_ids or candidate_id,
        },
    ]
    rows: list[dict[str, Any]] = []
    for component in components:
        component_id = str(component["component_id"])
        linked_row = {
            "score": panel_row,
            "evidence": drawer_row,
            "decision_qa": qa_row,
            "baseline": lineage_row,
            "remediation": remediation_rows[0] if remediation_rows else {},
        }.get(component_id, {})
        rows.append(
            {
                "candidate_id": candidate_id,
                "component_id": component_id,
                "component_label": component["component_label"],
                "component_score": component["component_score"],
                "component_status": _component_status(component_id, component["component_score"], panel_row, linked_row, remediation_rows),
                "target_view": component["target_view"],
                "target_artifact": str(component["target_artifact"]),
                "target_filter": component["target_filter"],
                "linked_row_key": component["linked_row_key"],
                "summary": _short(component["summary"]),
                "next_action": _short(component["next_action"]),
                "structure_image_path": str(structure_image_path or ""),
                "site_class": site_class,
                "site_highlight_label": f"{site_class or 'site'} / {component['component_label']}",
                "highlight_atom_count": highlight_atom_count,
                "highlight_legend": _short(highlight_legend),
                "evidence_anchor": _short(drawer_row.get("drawer_summary") or drawer_row.get("evidence_context_summary") or board_row.get("evidence_strength") or ""),
                "right_panel_detail": _short(
                    f"{component['component_label']}: {component['summary']} | highlight={highlight_legend} | evidence={drawer_row.get('drawer_summary') or board_row.get('evidence_strength') or ''}",
                    260,
                ),
                "export_scope": "local_candidate_explanation_drilldown",
                "procurement_allowed": False,
                "feedback_import_allowed": False,
            }
        )
    return rows


def build_candidate_explanation_drilldown(
    *,
    root: str | Path = ".",
    project_name: str = "demo",
) -> dict[str, Any]:
    root_path = Path(root)
    project_dir = root_path / "data" / "projects" / project_name
    panel = _read_json(project_dir / "candidate_explanation_panel.json")
    drawer_by_id = _by_candidate(_read_json(project_dir / "candidate_evidence_drawer.json"))
    qa_by_id = _by_candidate(_read_json(project_dir / "candidate_decision_qa.json"))
    lineage_by_id = _by_candidate(_read_json(project_dir / "baseline_lineage_compare.json"))
    visual_by_id = _by_candidate(_read_json(project_dir / "candidate_visual_compare.json"))
    board_by_id = _by_candidate(_read_json(project_dir / "candidate_review_board.json"))
    remediation = _read_json(project_dir / "candidate_remediation_queue.json") or _read_json(project_dir / "review_remediation_queue.json")
    remediation_by_id = _group_remediation(remediation)

    rows: list[dict[str, Any]] = []
    for panel_row in panel.get("rows") or []:
        if not isinstance(panel_row, dict):
            continue
        candidate_id = str(panel_row.get("candidate_id") or "").strip()
        if not candidate_id:
            continue
        rows.extend(
            _component_rows(
                project_dir=project_dir,
                panel_row=dict(panel_row),
                drawer_row=drawer_by_id.get(candidate_id, {}),
                qa_row=qa_by_id.get(candidate_id, {}),
                lineage_row=lineage_by_id.get(candidate_id, {}),
                remediation_rows=remediation_by_id.get(candidate_id, []),
                visual_row=visual_by_id.get(candidate_id, {}),
                board_row=board_by_id.get(candidate_id, {}),
            )
        )

    status_counts = Counter(str(row.get("component_status") or "unknown") for row in rows)
    component_counts = Counter(str(row.get("component_id") or "unknown") for row in rows)
    attention_count = sum(1 for row in rows if row.get("component_status") in {"attention", "watch"})
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if rows else "missing_panel",
        "mode": "candidate_explanation_drilldown",
        "project_name": project_name,
        "candidate_count": len({row.get("candidate_id") for row in rows}),
        "row_count": len(rows),
        "attention_count": attention_count,
        "status_counts": dict(status_counts.most_common()),
        "component_counts": dict(component_counts.most_common()),
        "rows": rows,
        "recommended_next_actions": [
            "Use target_view and target_filter to route a selected component into evidence, QA, baseline, or remediation context.",
            "Treat attention components as local review stop-list signals only.",
        ],
        "blocked_scopes": BLOCKED_SCOPES,
    }


def render_candidate_explanation_drilldown_markdown(report: dict) -> str:
    lines = [
        "# Candidate Explanation Drilldown",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Candidates / rows: `{report.get('candidate_count')}` / `{report.get('row_count')}`",
        f"- Attention components: `{report.get('attention_count')}`",
        "",
        "| Candidate | Component | Score | Status | Target | Filter | Summary | Next Action |",
        "| --- | --- | ---: | --- | --- | --- | --- | --- |",
    ]
    for row in (report.get("rows") or [])[:240]:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("candidate_id") or ""),
                    str(row.get("component_label") or row.get("component_id") or ""),
                    str(row.get("component_score") or ""),
                    str(row.get("component_status") or ""),
                    str(row.get("target_view") or ""),
                    str(row.get("target_filter") or "").replace("|", "/"),
                    str(row.get("summary") or "").replace("|", "/"),
                    str(row.get("next_action") or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_candidate_explanation_drilldown(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_CANDIDATE_EXPLANATION_DRILLDOWN_JSON,
    csv_path: str | Path | None = DEFAULT_CANDIDATE_EXPLANATION_DRILLDOWN_CSV,
    markdown_path: str | Path | None = DEFAULT_CANDIDATE_EXPLANATION_DRILLDOWN_MD,
) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    fields = [
        "candidate_id",
        "component_id",
        "component_label",
        "component_score",
        "component_status",
        "target_view",
        "target_artifact",
        "target_filter",
        "linked_row_key",
        "summary",
        "next_action",
        "structure_image_path",
        "site_class",
        "site_highlight_label",
        "highlight_atom_count",
        "highlight_legend",
        "evidence_anchor",
        "right_panel_detail",
        "export_scope",
        "procurement_allowed",
        "feedback_import_allowed",
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
        md_file.write_text(render_candidate_explanation_drilldown_markdown(report), encoding="utf-8")
