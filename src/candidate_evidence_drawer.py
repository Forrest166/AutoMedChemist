from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_EVIDENCE_DRAWER_JSON = Path("data/projects/demo/candidate_evidence_drawer.json")
DEFAULT_EVIDENCE_DRAWER_CSV = Path("data/projects/demo/candidate_evidence_drawer.csv")
DEFAULT_EVIDENCE_DRAWER_MD = Path("docs/candidate_evidence_drawer.md")
BLOCKED_SCOPES = ["procurement", "supplier_purchase", "real_experiment_feedback_auto_import"]


def _resolve(root: Path, path: str | Path) -> Path:
    item = Path(path)
    return item if item.is_absolute() else root / item


def _read_json(path: str | Path) -> dict:
    source = Path(path)
    if not source.exists():
        return {}
    try:
        payload = json.loads(source.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_csv_rows(path: str | Path) -> list[dict[str, str]]:
    source = Path(path)
    if not source.exists():
        return []
    with source.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _by_candidate(report: dict) -> dict[str, dict]:
    rows = {}
    for row in report.get("rows") or []:
        candidate_id = str(row.get("candidate_id") or "").strip()
        if candidate_id:
            rows[candidate_id] = dict(row)
    return rows


def _join_unique(values: list[object], limit: int = 6) -> str:
    out: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in out:
            out.append(text)
    return " | ".join(out[:limit])


def build_candidate_evidence_drawer(
    *,
    root: str | Path = ".",
    project_name: str = "demo",
    candidates_csv: str | Path | None = None,
    max_rows: int = 160,
) -> dict[str, Any]:
    root_path = Path(root)
    project_dir = Path("data/projects") / project_name
    candidates = _read_csv_rows(_resolve(root_path, candidates_csv or project_dir / "candidates.csv"))
    visual = _read_json(root_path / project_dir / "candidate_visual_compare.json")
    review = _read_json(root_path / project_dir / "candidate_review_packet.json")
    board = _read_json(root_path / project_dir / "candidate_review_board.json")
    drilldown = _read_json(root_path / project_dir / "candidate_drilldown_packet.json")
    baseline = _read_json(root_path / project_dir / "candidate_baseline_compare.json")
    decision = _read_json(root_path / project_dir / "candidate_decision_packet.json")
    visual_by_id = _by_candidate(visual)
    review_by_id = _by_candidate(review)
    board_by_id = _by_candidate(board)
    drill_by_id = _by_candidate(drilldown)
    baseline_by_id = _by_candidate(baseline)
    decision_by_id = _by_candidate(decision)
    rows = []
    selected = sorted(candidates, key=lambda row: (_float(row.get("rank"), 999999), -_float(row.get("score"))))
    for source in selected[: max(1, int(max_rows))]:
        candidate_id = str(source.get("candidate_id") or "").strip()
        visual_row = visual_by_id.get(candidate_id, {})
        review_row = review_by_id.get(candidate_id, {})
        board_row = board_by_id.get(candidate_id, {})
        drill_row = drill_by_id.get(candidate_id, {})
        baseline_row = baseline_by_id.get(candidate_id, {})
        decision_row = decision_by_id.get(candidate_id, {})
        evidence_depth = visual_row.get("evidence_depth_score") or drill_row.get("evidence_depth_score") or ""
        drawer_summary = _join_unique(
            [
                f"decision={decision_row.get('local_decision')}" if decision_row.get("local_decision") else "",
                f"score={source.get('score')}" if source.get("score") else "",
                f"review={board_row.get('local_review_status') or drill_row.get('board_status')}" if board_row or drill_row else "",
                f"baseline={decision_row.get('baseline_movement') or baseline_row.get('status')}" if decision_row or baseline_row else "",
                visual_row.get("evidence_context_summary") or drill_row.get("evidence_context_summary"),
                source.get("why_review") or drill_row.get("why_review"),
            ]
        )
        rows.append(
            {
                "candidate_id": candidate_id,
                "rank": source.get("rank", ""),
                "score": source.get("score", ""),
                "smiles": source.get("smiles", ""),
                "site_class": source.get("site_class") or source.get("site_type") or drill_row.get("site_class", ""),
                "local_decision": decision_row.get("local_decision", ""),
                "decision_confidence": decision_row.get("decision_confidence", ""),
                "decision_rationale": decision_row.get("decision_rationale", ""),
                "next_action": decision_row.get("next_action") or board_row.get("proposed_review_action") or "",
                "review_bucket": review_row.get("review_bucket") or board_row.get("review_bucket") or drill_row.get("review_bucket", ""),
                "review_status": review_row.get("review_status") or board_row.get("review_status") or "",
                "board_status": board_row.get("local_review_status") or drill_row.get("board_status", ""),
                "reviewer_decision": board_row.get("reviewer_decision") or drill_row.get("reviewer_decision", ""),
                "risk_bucket": board_row.get("risk_bucket") or decision_row.get("risk_bucket") or "",
                "baseline_status": baseline_row.get("status") or decision_row.get("baseline_status", ""),
                "baseline_movement": decision_row.get("baseline_movement", ""),
                "score_delta": baseline_row.get("score_delta") or decision_row.get("score_delta", ""),
                "rank_delta": baseline_row.get("rank_delta") or decision_row.get("rank_delta", ""),
                "changed_fields": baseline_row.get("changed_fields") or decision_row.get("changed_fields", ""),
                "evidence_depth_score": evidence_depth,
                "evidence_context_summary": visual_row.get("evidence_context_summary") or drill_row.get("evidence_context_summary", ""),
                "mmp_example_count": visual_row.get("mmp_example_count") or drill_row.get("mmp_example_count", ""),
                "sar_example_count": visual_row.get("sar_example_count") or drill_row.get("sar_example_count", ""),
                "image_path": visual_row.get("image_path") or drill_row.get("image_path", ""),
                "visual_grid_path": drill_row.get("visual_grid_path") or visual.get("grid_image_path", ""),
                "mmp_thumbnail_paths": visual_row.get("mmp_thumbnail_paths") or drill_row.get("mmp_thumbnail_paths", ""),
                "sar_thumbnail_paths": visual_row.get("sar_thumbnail_paths") or drill_row.get("sar_thumbnail_paths", ""),
                "drawer_summary": drawer_summary,
                "drawer_sections": "structure;evidence;review;baseline;decision",
                "export_scope": "local_evidence_review",
                "procurement_allowed": False,
                "feedback_import_allowed": False,
            }
        )
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if rows else "missing_candidates",
        "mode": "native_candidate_evidence_drawer",
        "project_name": project_name,
        "row_count": len(rows),
        "linked_visual_rows": len(visual_by_id),
        "linked_review_rows": len(review_by_id),
        "linked_board_rows": len(board_by_id),
        "linked_baseline_rows": len(baseline_by_id),
        "linked_decision_rows": len(decision_by_id),
        "rows": rows,
        "recommended_next_actions": [
            "Use the drawer row as the native single-candidate evidence panel.",
            "Review structure, evidence, review, baseline, and decision sections together before changing local priority.",
        ],
        "blocked_scopes": BLOCKED_SCOPES,
    }


def render_candidate_evidence_drawer_markdown(report: dict) -> str:
    lines = [
        "# Candidate Evidence Drawer",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Rows: `{report.get('row_count')}`",
        "",
        "| ID | Decision | Score | Review | Baseline | Depth | Image | Summary |",
        "| --- | --- | ---: | --- | --- | ---: | --- | --- |",
    ]
    for row in (report.get("rows") or [])[:120]:
        image = f"[image]({row.get('image_path')})" if row.get("image_path") else ""
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("candidate_id") or ""),
                    str(row.get("local_decision") or ""),
                    str(row.get("score") or ""),
                    str(row.get("board_status") or row.get("review_status") or ""),
                    str(row.get("baseline_movement") or row.get("baseline_status") or ""),
                    str(row.get("evidence_depth_score") or ""),
                    image,
                    str(row.get("drawer_summary") or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_candidate_evidence_drawer(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_EVIDENCE_DRAWER_JSON,
    csv_path: str | Path | None = DEFAULT_EVIDENCE_DRAWER_CSV,
    markdown_path: str | Path | None = DEFAULT_EVIDENCE_DRAWER_MD,
) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    fields = [
        "candidate_id",
        "rank",
        "score",
        "smiles",
        "site_class",
        "local_decision",
        "decision_confidence",
        "decision_rationale",
        "next_action",
        "review_bucket",
        "review_status",
        "board_status",
        "reviewer_decision",
        "risk_bucket",
        "baseline_status",
        "baseline_movement",
        "score_delta",
        "rank_delta",
        "changed_fields",
        "evidence_depth_score",
        "evidence_context_summary",
        "mmp_example_count",
        "sar_example_count",
        "image_path",
        "visual_grid_path",
        "mmp_thumbnail_paths",
        "sar_thumbnail_paths",
        "drawer_summary",
        "drawer_sections",
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
        md_file.write_text(render_candidate_evidence_drawer_markdown(report), encoding="utf-8")
