from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_CANDIDATE_DECISION_JSON = Path("data/projects/demo/candidate_decision_packet.json")
DEFAULT_CANDIDATE_DECISION_CSV = Path("data/projects/demo/candidate_decision_packet.csv")
DEFAULT_CANDIDATE_DECISION_EXPORT_CSV = Path("data/projects/demo/candidate_decision_export.csv")
DEFAULT_CANDIDATE_DECISION_MD = Path("docs/candidate_decision_packet.md")

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


def _float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _by_candidate(report: dict) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    for row in report.get("rows") or []:
        candidate_id = str(row.get("candidate_id") or "").strip()
        if candidate_id:
            rows[candidate_id] = dict(row)
    return rows


def _contains_any(value: object, options: set[str]) -> bool:
    text = str(value or "").strip().lower()
    return any(option in text for option in options)


def _baseline_movement(row: dict) -> str:
    status = str(row.get("status") or "").strip().lower()
    score_delta = _float(row.get("score_delta"), 0.0)
    rank_delta = _float(row.get("rank_delta"), 0.0)
    changed_fields = str(row.get("changed_fields") or "")
    if status in {"added", "removed"}:
        return status
    if abs(score_delta) >= 5:
        return "large_score_movement"
    if abs(rank_delta) >= 5:
        return "large_rank_movement"
    if changed_fields:
        return "changed_fields"
    if status == "changed":
        return "changed"
    return "stable"


def _decision_for_row(row: dict, board: dict, baseline: dict) -> tuple[str, int, str, str]:
    score = _float(row.get("score") or board.get("score"), 0.0)
    local_status = str(board.get("local_review_status") or row.get("board_status") or "").strip().lower()
    reviewer_decision = str(board.get("reviewer_decision") or row.get("reviewer_decision") or "").strip().lower()
    risk = str(board.get("risk_bucket") or row.get("risk_bucket") or "").strip().lower()
    review_bucket = str(board.get("review_bucket") or row.get("review_bucket") or "").strip().lower()
    review_status = str(board.get("review_status") or row.get("review_status") or "").strip().lower()
    movement = _baseline_movement(baseline)
    evidence_depth = _float(row.get("evidence_depth_score"), 0.0)
    reasons: list[str] = []

    if _contains_any(local_status, {"blocked", "reject"}) or _contains_any(reviewer_decision, {"blocked", "reject"}):
        reasons.append("local reviewer blocked or rejected the candidate")
        return "reject", 92, "; ".join(reasons), "Keep out of the local candidate priority list until manually reopened."
    if risk in {"blocked_context", "low_risk_score"} or score < 55:
        reasons.append(f"risk={risk or '-'} score={score:g}")
        return "reject", 82, "; ".join(reasons), "Do not advance locally; inspect risk note before considering a new rule."
    if _contains_any(local_status, {"deferred"}) or _contains_any(reviewer_decision, {"defer"}):
        reasons.append("local reviewer deferred the row")
        return "defer", 80, "; ".join(reasons), "Leave in the deferred queue with the reviewer note attached."
    if risk == "contradiction":
        reasons.append("contradictory public/SAR evidence is present")
        return "watch", 78, "; ".join(reasons), "Review contradiction context and require a human decision before priority movement."
    if movement in {"large_score_movement", "large_rank_movement", "added", "removed"}:
        reasons.append(f"baseline movement={movement}")
        return "watch", 74, "; ".join(reasons), "Inspect baseline diff before pinning or changing local candidate priority."
    if local_status in {"pending_review", "unreviewed", "needs_follow_up"} or review_status == "pending_review":
        reasons.append(f"local_status={local_status or '-'} review_status={review_status or '-'}")
        return "needs_measurement", 70, "; ".join(reasons), "Collect or review exact endpoint/context evidence before accepting."
    if "site_class" in review_bucket or "governance" in review_bucket:
        reasons.append(f"review_bucket={review_bucket}")
        return "needs_measurement", 68, "; ".join(reasons), "Route through site-class governance before accepting."
    if local_status in {"reviewed", "evidence_supported"} or reviewer_decision in {"reviewed", "evidence_supported", "accept", "accepted"}:
        if score >= 80 and risk in {"", "clear", "pending_review"}:
            reasons.append(f"reviewed with score={score:g} evidence_depth={evidence_depth:g}")
            return "accept", 86, "; ".join(reasons), "Accept for local design prioritization only; external operational workflows remain blocked."
        reasons.append(f"reviewed but score/risk needs watching score={score:g} risk={risk or '-'}")
        return "watch", 72, "; ".join(reasons), "Keep visible in local review until score/risk context improves."
    if score >= 80 and evidence_depth >= 2:
        reasons.append(f"high score with evidence_depth={evidence_depth:g}")
        return "watch", 66, "; ".join(reasons), "Human review should confirm the evidence before accepting."
    reasons.append("insufficient local review signal")
    return "defer", 60, "; ".join(reasons), "Keep deferred until review board status or evidence depth improves."


def _evidence_limitations(row: dict, board: dict, baseline: dict) -> str:
    limitations: list[str] = []
    if _float(row.get("evidence_depth_score"), 0.0) < 2:
        limitations.append("limited linked evidence depth")
    if str(board.get("risk_bucket") or row.get("risk_bucket") or "") not in {"", "clear"}:
        limitations.append(f"risk bucket={board.get('risk_bucket') or row.get('risk_bucket')}")
    if _baseline_movement(baseline) not in {"stable", "changed", "changed_fields"}:
        limitations.append(f"baseline movement={_baseline_movement(baseline)}")
    if str(board.get("local_review_status") or row.get("board_status") or "") in {"pending_review", "unreviewed", "needs_follow_up"}:
        limitations.append("local review not fully closed")
    return "; ".join(limitations) or "no material local limitation captured"


def _discussion_summary(row: dict, local_decision: str, rationale: str, limitations: str) -> str:
    candidate_id = str(row.get("candidate_id") or "").strip()
    site = str(row.get("site_class") or "").strip() or "unspecified site"
    score = str(row.get("score") or "").strip() or "-"
    return f"{candidate_id}: {local_decision} at {site}, score={score}. Rationale: {rationale}. Evidence limitations: {limitations}."


def build_candidate_decision_packet(
    *,
    root: str | Path = ".",
    project_name: str = "demo",
    drilldown_path: str | Path | None = None,
    board_path: str | Path | None = None,
    baseline_path: str | Path | None = None,
    visual_path: str | Path | None = None,
    max_rows: int = 160,
) -> dict[str, Any]:
    root_path = Path(root)
    project_dir = Path("data/projects") / project_name
    drilldown = _read_json(_resolve(root_path, drilldown_path or project_dir / "candidate_drilldown_packet.json"))
    board_report = _read_json(_resolve(root_path, board_path or project_dir / "candidate_review_board.json"))
    baseline_report = _read_json(_resolve(root_path, baseline_path or project_dir / "candidate_baseline_compare.json"))
    visual_report = _read_json(_resolve(root_path, visual_path or project_dir / "candidate_visual_compare.json"))
    board_by_id = _by_candidate(board_report)
    baseline_by_id = _by_candidate(baseline_report)
    visual_by_id = _by_candidate(visual_report)
    source_rows = list(drilldown.get("rows") or [])
    if not source_rows:
        source_rows = list(board_report.get("rows") or [])
    rows = []
    for idx, row in enumerate(source_rows[: max(1, int(max_rows))], start=1):
        candidate_id = str(row.get("candidate_id") or "").strip()
        board = board_by_id.get(candidate_id, {})
        baseline = baseline_by_id.get(candidate_id, {})
        visual = visual_by_id.get(candidate_id, {})
        merged = {**visual, **row}
        local_decision, confidence, rationale, next_action = _decision_for_row(merged, board, baseline)
        limitations = _evidence_limitations(merged, board, baseline)
        thumbnail_paths = ";".join(
            str(value or "")
            for value in [
                merged.get("image_path"),
                merged.get("mmp_thumbnail_paths"),
                merged.get("sar_thumbnail_paths"),
            ]
            if str(value or "").strip()
        )
        rows.append(
            {
                "decision_id": f"{project_name}:{candidate_id or idx}",
                "candidate_id": candidate_id,
                "rank": merged.get("rank", ""),
                "score": merged.get("score", ""),
                "smiles": merged.get("smiles", ""),
                "site_class": merged.get("site_class", ""),
                "local_decision": local_decision,
                "decision_confidence": confidence,
                "decision_rationale": rationale,
                "evidence_limitations": limitations,
                "discussion_summary": _discussion_summary(merged, local_decision, rationale, limitations),
                "next_action": next_action,
                "board_status": board.get("local_review_status") or merged.get("board_status", ""),
                "reviewer_decision": board.get("reviewer_decision") or merged.get("reviewer_decision", ""),
                "review_bucket": board.get("review_bucket") or merged.get("review_bucket", ""),
                "risk_bucket": board.get("risk_bucket") or merged.get("risk_bucket", ""),
                "evidence_depth_score": merged.get("evidence_depth_score", ""),
                "mmp_example_count": merged.get("mmp_example_count", ""),
                "sar_example_count": merged.get("sar_example_count", ""),
                "mmp_thumbnail_paths": merged.get("mmp_thumbnail_paths", ""),
                "sar_thumbnail_paths": merged.get("sar_thumbnail_paths", ""),
                "evidence_context_summary": merged.get("evidence_context_summary", ""),
                "baseline_status": baseline.get("status", ""),
                "baseline_movement": _baseline_movement(baseline),
                "score_delta": baseline.get("score_delta", merged.get("score_delta", "")),
                "rank_delta": baseline.get("rank_delta", merged.get("rank_delta", "")),
                "changed_fields": baseline.get("changed_fields", merged.get("changed_fields", "")),
                "image_path": merged.get("image_path", ""),
                "thumbnail_paths": thumbnail_paths,
                "visual_grid_path": merged.get("visual_grid_path", visual_report.get("grid_image_path", "")),
                "export_scope": "local_decision_support",
                "procurement_allowed": False,
                "feedback_import_allowed": False,
            }
        )
    decision_counts = Counter(str(row.get("local_decision") or "") for row in rows)
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if rows else "missing_candidates",
        "mode": "local_candidate_decision_packet",
        "project_name": project_name,
        "decision_count": len(rows),
        "decision_counts": dict(decision_counts.most_common()),
        "accept_count": decision_counts.get("accept", 0),
        "defer_count": decision_counts.get("defer", 0),
        "reject_count": decision_counts.get("reject", 0),
        "watch_count": decision_counts.get("watch", 0),
        "needs_measurement_count": decision_counts.get("needs_measurement", 0),
        "linked_drilldown_rows": len(drilldown.get("rows") or []),
        "linked_board_rows": len(board_by_id),
        "linked_baseline_rows": len(baseline_by_id),
        "linked_visual_rows": len(visual_by_id),
        "rows": rows,
        "export_schema": {
            "format": "candidate_decision_export_csv",
            "scope": "local_decision_support",
            "procurement_allowed": False,
            "feedback_import_allowed": False,
        },
        "recommended_next_actions": [
            "Use accept/defer/reject/watch/needs_measurement as local design-priority labels only.",
            "Open candidate drill-down and baseline diff rows before accepting large score or rank movement.",
            "Keep external operational workflows outside this export path.",
        ],
        "blocked_scopes": BLOCKED_SCOPES,
    }


def render_candidate_decision_packet_markdown(report: dict) -> str:
    lines = [
        "# Candidate Decision Packet",
        "",
        f"- Created at: `{report.get('created_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Decisions: `{report.get('decision_count')}`",
        f"- Counts: `{report.get('decision_counts')}`",
        "",
        "| ID | Decision | Confidence | Score | Risk | Baseline | Evidence Depth | Next Action |",
        "| --- | --- | ---: | ---: | --- | --- | ---: | --- |",
    ]
    for row in (report.get("rows") or [])[:120]:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("candidate_id") or ""),
                    str(row.get("local_decision") or ""),
                    str(row.get("decision_confidence") or ""),
                    str(row.get("score") or ""),
                    str(row.get("risk_bucket") or ""),
                    str(row.get("baseline_movement") or ""),
                    str(row.get("evidence_depth_score") or ""),
                    str(row.get("next_action") or "").replace("|", "/"),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
        "This packet is local decision support only. It does not authorize external operational workflows.",
            "",
        ]
    )
    return "\n".join(lines)


def write_candidate_decision_packet(
    report: dict,
    *,
    json_path: str | Path = DEFAULT_CANDIDATE_DECISION_JSON,
    csv_path: str | Path | None = DEFAULT_CANDIDATE_DECISION_CSV,
    markdown_path: str | Path | None = DEFAULT_CANDIDATE_DECISION_MD,
    export_csv_path: str | Path | None = DEFAULT_CANDIDATE_DECISION_EXPORT_CSV,
) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    fields = [
        "decision_id",
        "candidate_id",
        "rank",
        "score",
        "smiles",
        "site_class",
        "local_decision",
        "decision_confidence",
        "decision_rationale",
        "evidence_limitations",
        "discussion_summary",
        "next_action",
        "board_status",
        "reviewer_decision",
        "review_bucket",
        "risk_bucket",
        "evidence_depth_score",
        "mmp_example_count",
        "sar_example_count",
        "mmp_thumbnail_paths",
        "sar_thumbnail_paths",
        "evidence_context_summary",
        "baseline_status",
        "baseline_movement",
        "score_delta",
        "rank_delta",
        "changed_fields",
        "image_path",
        "thumbnail_paths",
        "visual_grid_path",
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
    if export_csv_path:
        export_file = Path(export_csv_path)
        export_file.parent.mkdir(parents=True, exist_ok=True)
        export_fields = [
            "decision_id",
            "candidate_id",
            "local_decision",
            "decision_confidence",
            "smiles",
            "site_class",
            "score",
            "decision_rationale",
            "evidence_limitations",
            "discussion_summary",
            "next_action",
            "thumbnail_paths",
            "export_scope",
            "procurement_allowed",
            "feedback_import_allowed",
            "blocked_scopes",
            "packet_created_at",
        ]
        with export_file.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=export_fields)
            writer.writeheader()
            for row in report.get("rows") or []:
                writer.writerow(
                    {
                        "decision_id": row.get("decision_id", ""),
                        "candidate_id": row.get("candidate_id", ""),
                        "local_decision": row.get("local_decision", ""),
                        "decision_confidence": row.get("decision_confidence", ""),
                        "smiles": row.get("smiles", ""),
                        "site_class": row.get("site_class", ""),
                        "score": row.get("score", ""),
                        "decision_rationale": row.get("decision_rationale", ""),
                        "evidence_limitations": row.get("evidence_limitations", ""),
                        "discussion_summary": row.get("discussion_summary", ""),
                        "next_action": row.get("next_action", ""),
                        "thumbnail_paths": row.get("thumbnail_paths", ""),
                        "export_scope": "local_decision_support",
                        "procurement_allowed": False,
                        "feedback_import_allowed": False,
                        "blocked_scopes": ";".join(BLOCKED_SCOPES),
                        "packet_created_at": report.get("created_at", ""),
                    }
                )
    if markdown_path:
        md_file = Path(markdown_path)
        md_file.parent.mkdir(parents=True, exist_ok=True)
        md_file.write_text(render_candidate_decision_packet_markdown(report), encoding="utf-8")
