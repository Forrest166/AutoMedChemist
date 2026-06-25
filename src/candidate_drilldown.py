from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_CANDIDATE_DRILLDOWN_JSON = Path("data/projects/demo/candidate_drilldown_packet.json")
DEFAULT_CANDIDATE_DRILLDOWN_CSV = Path("data/projects/demo/candidate_drilldown_packet.csv")
DEFAULT_CANDIDATE_DRILLDOWN_MD = Path("docs/candidate_drilldown_packet.md")


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


def _by_candidate(report: dict) -> dict[str, dict]:
    rows = {}
    for row in report.get("rows") or []:
        candidate_id = str(row.get("candidate_id") or "").strip()
        if candidate_id:
            rows[candidate_id] = dict(row)
    return rows


def _evidence_snippet(candidate: dict, review: dict, visual: dict, governance: dict, board: dict) -> str:
    parts = []
    for value in [
        candidate.get("candidate_explanation_summary"),
        candidate.get("why_recommended"),
        review.get("evidence_strength"),
        visual.get("candidate_explanation_summary"),
        visual.get("evidence_context_summary"),
        governance.get("changed_fields"),
        board.get("reviewer_decision") or board.get("local_review_status"),
    ]:
        text = str(value or "").strip()
        if text and text not in parts:
            parts.append(text)
    return " | ".join(parts[:5])


def build_candidate_drilldown_packet(
    *,
    root: str | Path = ".",
    project_name: str = "demo",
    candidates_csv: str | Path | None = None,
    visual_path: str | Path | None = None,
    review_path: str | Path | None = None,
    governance_path: str | Path | None = None,
    board_path: str | Path | None = None,
    max_rows: int = 120,
) -> dict[str, Any]:
    root_path = Path(root)
    project_dir = Path("data/projects") / project_name
    candidates_file = _resolve(root_path, candidates_csv or project_dir / "candidates.csv")
    visual = _read_json(_resolve(root_path, visual_path or project_dir / "candidate_visual_compare.json"))
    review = _read_json(_resolve(root_path, review_path or project_dir / "candidate_review_packet.json"))
    governance = _read_json(_resolve(root_path, governance_path or project_dir / "local_governance_diff_report.json"))
    board = _read_json(_resolve(root_path, board_path or project_dir / "candidate_review_board.json"))
    candidates = _read_csv_rows(candidates_file)
    visual_by_id = _by_candidate(visual)
    review_by_id = _by_candidate(review)
    board_by_id = _by_candidate(board)
    governance_by_id = _by_candidate(governance)
    rows = []
    for candidate in sorted(candidates, key=lambda row: (_float(row.get("rank"), 999999), -_float(row.get("score"))))[: max(1, int(max_rows))]:
        candidate_id = str(candidate.get("candidate_id") or "").strip()
        visual_row = visual_by_id.get(candidate_id, {})
        review_row = review_by_id.get(candidate_id, {})
        governance_row = governance_by_id.get(candidate_id, {})
        board_row = board_by_id.get(candidate_id, {})
        rows.append(
            {
                "candidate_id": candidate_id,
                "rank": candidate.get("rank"),
                "score": candidate.get("score"),
                "smiles": candidate.get("smiles"),
                "site_class": candidate.get("site_class") or candidate.get("site_type"),
                "direction": candidate.get("direction"),
                "image_path": visual_row.get("image_path", ""),
                "visual_grid_path": visual.get("grid_image_path", ""),
                "review_bucket": review_row.get("review_bucket", ""),
                "review_status": review_row.get("review_status", ""),
                "board_status": board_row.get("board_status") or board_row.get("local_review_status", ""),
                "reviewer_decision": board_row.get("reviewer_decision") or board_row.get("local_review_status", ""),
                "governance_status": governance_row.get("status", ""),
                "score_delta": governance_row.get("score_delta", ""),
                "rank_delta": governance_row.get("rank_delta", ""),
                "changed_fields": governance_row.get("changed_fields", ""),
                "evidence_depth_score": visual_row.get("evidence_depth_score", ""),
                "evidence_context_summary": visual_row.get("evidence_context_summary", ""),
                "mmp_example_count": visual_row.get("mmp_example_count", ""),
                "sar_example_count": visual_row.get("sar_example_count", ""),
                "mmp_thumbnail_paths": visual_row.get("mmp_thumbnail_paths", ""),
                "sar_thumbnail_paths": visual_row.get("sar_thumbnail_paths", ""),
                "evidence_snippet": _evidence_snippet(candidate, review_row, visual_row, governance_row, board_row),
                "why_review": candidate.get("why_review") or review_row.get("why_review", ""),
                "why_recommended": candidate.get("why_recommended") or review_row.get("why_recommended", ""),
            }
        )
    status = "ready" if rows else "missing_candidates"
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "mode": "non_experimental_candidate_drilldown_packet",
        "project_name": project_name,
        "row_count": len(rows),
        "linked_visual_rows": len(visual_by_id),
        "linked_review_rows": len(review_by_id),
        "linked_governance_rows": len(governance_by_id),
        "linked_board_rows": len(board_by_id),
        "candidates_csv": str(candidates_file),
        "rows": rows,
        "recommended_next_actions": [
            "Open image_path and evidence snippets while reviewing candidate board decisions.",
            "Use governance deltas to spot score/rank movement before accepting local policy changes.",
            "Keep this packet as local decision support only.",
        ],
        "blocked_scopes": ["procurement", "supplier_purchase", "real_experiment_feedback_auto_import"],
    }


def render_candidate_drilldown_markdown(report: dict) -> str:
    lines = [
        "# Candidate Drilldown Packet",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Rows: `{report.get('row_count')}`",
        "",
        "| ID | Score | Site | Review | Board | Governance | Depth | Image | Evidence |",
        "| --- | ---: | --- | --- | --- | --- | ---: | --- | --- |",
    ]
    for row in (report.get("rows") or [])[:80]:
        image = f"[image]({row.get('image_path')})" if row.get("image_path") else ""
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("candidate_id") or ""),
                    str(row.get("score") or ""),
                    str(row.get("site_class") or ""),
                    str(row.get("review_bucket") or ""),
                    str(row.get("board_status") or ""),
                    str(row.get("governance_status") or ""),
                    str(row.get("evidence_depth_score") or ""),
                    image,
                    str(row.get("evidence_snippet") or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_candidate_drilldown_packet(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_CANDIDATE_DRILLDOWN_JSON,
    csv_path: str | Path | None = DEFAULT_CANDIDATE_DRILLDOWN_CSV,
    markdown_path: str | Path | None = DEFAULT_CANDIDATE_DRILLDOWN_MD,
) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if csv_path:
        fields = [
            "candidate_id",
            "rank",
            "score",
            "smiles",
            "site_class",
            "direction",
            "image_path",
            "visual_grid_path",
            "review_bucket",
            "review_status",
            "board_status",
            "reviewer_decision",
            "governance_status",
            "score_delta",
            "rank_delta",
            "changed_fields",
            "evidence_depth_score",
            "evidence_context_summary",
            "mmp_example_count",
            "sar_example_count",
            "mmp_thumbnail_paths",
            "sar_thumbnail_paths",
            "evidence_snippet",
            "why_review",
            "why_recommended",
        ]
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
        md_file.write_text(render_candidate_drilldown_markdown(report), encoding="utf-8")
